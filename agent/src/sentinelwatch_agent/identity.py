"""Endpoint Identity Management for SentinelWatch Agent.

Provides stable, secure endpoint identity generation and persistence.
"""

import hashlib
import json
import os
import secrets
import platform
import base64
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from .crypto.certificates import generate_key_pair, private_key_to_pem
from .logging import get_logger

logger = get_logger(__name__)


class EndpointIdentity:
    """Stable endpoint identity that persists across agent restarts."""

    IDENTITY_FILE = "agent_identity.json"
    IDENTITY_VERSION = 1
    _SECRET_FIELDS = ("enrollment_token", "agent_token", "agent_refresh_token", "private_key_pem")

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.identity_file = self.data_dir / self.IDENTITY_FILE
        self._identity: Optional[dict] = None

    def load(self) -> Optional[dict]:
        """Load existing identity from disk."""
        if not self.identity_file.exists():
            return None

        try:
            with self.identity_file.open("r") as f:
                data = json.load(f)

            if data.get("version") != self.IDENTITY_VERSION:
                logger.warning("identity_version_mismatch", version=data.get("version"))
                raise RuntimeError("Agent identity format is unsupported; refusing to replace it")

            for field in self._SECRET_FIELDS:
                value = data.get(field)
                protected_value = data.get(f"{field}_protected")
                if protected_value:
                    data[field] = self._unprotect_secret(protected_value)
                elif value:
                    # Upgrade legacy plaintext identities on the next save.
                    data[field] = value

            self._identity = data
            logger.info("identity_loaded", agent_id=data.get("agent_id"))
            return data
        except RuntimeError:
            raise
        except Exception as e:
            logger.error("identity_load_failed", error=str(e))
            # Never treat an unreadable existing identity as a fresh install: doing so
            # could overwrite the only copy of an endpoint credential after an account change.
            raise RuntimeError("Existing agent identity could not be decrypted or read") from e

    def save(self, identity: dict) -> bool:
        """Save identity to disk atomically."""
        try:
            identity["version"] = self.IDENTITY_VERSION
            identity["updated_at"] = datetime.now(timezone.utc).isoformat()

            stored_identity = dict(identity)
            for field in self._SECRET_FIELDS:
                # A cleared secret must also remove its old protected ciphertext;
                # otherwise load() would resurrect a credential the caller removed.
                stored_identity.pop(f"{field}_protected", None)
                secret = stored_identity.pop(field, None)
                if secret:
                    stored_identity[f"{field}_protected"] = self._protect_secret(secret)

            # Write to temp file then rename (atomic on POSIX, best-effort on Windows)
            temp_file = self.identity_file.with_suffix(".tmp")
            self.data_dir.mkdir(parents=True, exist_ok=True)
            with temp_file.open("w") as f:
                json.dump(stored_identity, f, indent=2)

            temp_file.replace(self.identity_file)
            self._identity = identity
            logger.info("identity_saved", agent_id=identity.get("agent_id"))
            return True
        except Exception as e:
            logger.error("identity_save_failed", error=str(e))
            return False

    def generate_machine_fingerprint(self) -> dict:
        """Generate a stable machine fingerprint from hardware identifiers."""
        fingerprint = {
            "machine_guid": self._get_machine_guid(),
            "hostname": platform.node(),
            "platform": platform.platform(),
            "processor": platform.processor(),
            "architecture": platform.architecture()[0],
        }

        # Add BIOS/board info if available on Windows
        try:
            import wmi
            c = wmi.WMI()
            for board in c.Win32_BaseBoard():
                fingerprint["board_serial"] = board.SerialNumber.strip() if board.SerialNumber else ""
                fingerprint["board_manufacturer"] = board.Manufacturer.strip() if board.Manufacturer else ""
                break
        except Exception:
            pass

        return fingerprint

    def _get_machine_guid(self) -> str:
        """Get Windows machine GUID from registry."""
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
                0,
                winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
            )
            guid, _ = winreg.QueryValueEx(key, "MachineGuid")
            winreg.CloseKey(key)
            return guid
        except Exception:
            return "unknown"

    def compute_identity_hash(self, fingerprint: dict) -> str:
        """Compute a stable hash from machine fingerprint."""
        # Sort keys for consistent hashing
        canonical = json.dumps(fingerprint, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:32]

    def create_new_identity(self, enrollment_token: str = "") -> dict:
        """Create a new endpoint identity."""
        # Generate key pair for this identity
        private_key = generate_key_pair()
        private_key_pem = private_key_to_pem(private_key)

        # Generate machine fingerprint
        fingerprint = self.generate_machine_fingerprint()
        identity_hash = self.compute_identity_hash(fingerprint)

        # Create identity
        identity = {
            "version": self.IDENTITY_VERSION,
            "agent_id": "",  # Will be set after registration
            "identity_hash": identity_hash,
            "fingerprint": fingerprint,
            "private_key_pem": private_key_pem,
            "enrollment_token": enrollment_token,
            "enrollment_token_hash": self._hash_enrollment_token(enrollment_token) if enrollment_token else "",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "registration_count": 0,
            "last_registration": None,
        }

        return identity

    def get_or_create_identity(self, enrollment_token: str = "") -> dict:
        """Load existing identity or create new one."""
        identity = self.load()

        if identity is None:
            logger.info("creating_new_endpoint_identity")
            identity = self.create_new_identity(enrollment_token)
            self.save(identity)
        else:
            configured_hash = self._hash_enrollment_token(enrollment_token) if enrollment_token else ""
            stored_hash = identity.get("enrollment_token_hash") or (
                self._hash_enrollment_token(identity["enrollment_token"])
                if identity.get("enrollment_token") else ""
            )
            if configured_hash and configured_hash != stored_hash:
                # A newly configured enrollment token is an explicit operator-requested
                # re-enrollment. Discard the previous bearer credential before rotating.
                identity["enrollment_token"] = enrollment_token
                identity["enrollment_token_hash"] = configured_hash
                identity.pop("agent_token", None)
                identity.pop("agent_refresh_token", None)
                self.save(identity)

            # Validate fingerprint hasn't changed unexpectedly
            current_fingerprint = self.generate_machine_fingerprint()
            if identity["fingerprint"] != current_fingerprint:
                logger.warning(
                    "fingerprint_changed",
                    old_fingerprint=identity["fingerprint"],
                    new_fingerprint=current_fingerprint,
                )
                # Could trigger re-enrollment workflow here
                identity["fingerprint"] = current_fingerprint
                identity["identity_hash"] = self.compute_identity_hash(current_fingerprint)
                self.save(identity)

        return identity

    @staticmethod
    def _hash_enrollment_token(token: str) -> str:
        """Retain a non-reversible marker to recognize the consumed token on restart."""
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def update_after_registration(self, agent_id: str) -> bool:
        """Update identity after successful backend registration."""
        identity = self.load()
        if identity is None:
            return False

        identity["agent_id"] = agent_id
        identity["registration_count"] = identity.get("registration_count", 0) + 1
        identity["last_registration"] = datetime.now(timezone.utc).isoformat()
        return self.save(identity)

    def update_agent_token(self, agent_id: str, agent_token: str, agent_refresh_token: str = "") -> bool:
        """Persist the per-agent bearer credential using the Windows user DPAPI scope."""
        identity = self.load()
        if identity is None:
            return False
        identity["agent_id"] = agent_id
        # The enrollment token is single-use and must not remain a permanent
        # agent secret after unique endpoint credentials have been issued.
        identity.pop("enrollment_token", None)
        identity["agent_token"] = agent_token
        if agent_refresh_token:
            identity["agent_refresh_token"] = agent_refresh_token
        identity["registration_count"] = identity.get("registration_count", 0) + 1
        identity["last_registration"] = datetime.now(timezone.utc).isoformat()
        return self.save(identity)

    @staticmethod
    def _protect_secret(secret: str) -> str:
        if os.name != "nt":
            raise RuntimeError("Windows DPAPI is required to persist agent credentials")
        import win32crypt

        protected = win32crypt.CryptProtectData(secret.encode("utf-8"), "SentinelWatch agent identity")
        return "dpapi:" + base64.b64encode(protected).decode("ascii")

    @staticmethod
    def _unprotect_secret(value: str) -> str:
        if not value.startswith("dpapi:") or os.name != "nt":
            raise RuntimeError("Agent credential is protected for a different platform or format")
        import win32crypt

        protected = base64.b64decode(value.removeprefix("dpapi:"), validate=True)
        _, cleartext = win32crypt.CryptUnprotectData(protected, None, None, None, 0)
        return cleartext.decode("utf-8")

    def get_agent_id(self) -> Optional[str]:
        """Get stored agent ID."""
        identity = self.load()
        if identity:
            return identity.get("agent_id")
        return None

    def get_private_key_pem(self) -> Optional[str]:
        """Get stored private key for mTLS."""
        identity = self.load()
        if identity:
            return identity.get("private_key_pem")
        return None

    def needs_re_enrollment(self, backend_agent_id: Optional[str] = None) -> Tuple[bool, str]:
        """Check if re-enrollment is needed.

        Returns:
            (needs_re_enrollment, reason)
        """
        identity = self.load()
        if identity is None:
            return True, "no_identity"

        agent_id = identity.get("agent_id")
        if not agent_id:
            return True, "no_agent_id"

        if backend_agent_id and agent_id != backend_agent_id:
            return True, f"agent_id_mismatch: local={agent_id}, backend={backend_agent_id}"

        # Validate fingerprint still matches
        current_fingerprint = self.generate_machine_fingerprint()
        if identity["fingerprint"] != current_fingerprint:
            return True, "fingerprint_mismatch"

        return False, "valid"

    def reset_identity(self) -> bool:
        """Reset identity (for re-enrollment workflow)."""
        try:
            if self.identity_file.exists():
                # Sanitize timestamp for Windows filename (no colons)
                timestamp = datetime.now(timezone.utc).isoformat().replace(":", "-")
                backup = self.identity_file.with_suffix(f".bak.{timestamp}")
                self.identity_file.replace(backup)
                logger.info("identity_reset", backup=str(backup))
            self._identity = None
            return True
        except Exception as e:
            logger.error("identity_reset_failed", error=str(e))
            return False


def create_identity_manager(data_dir: str | Path) -> EndpointIdentity:
    """Factory function to create identity manager."""
    return EndpointIdentity(Path(data_dir))
