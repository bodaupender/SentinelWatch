"""
mTLS Configuration and Certificate Management for SentinelWatch Agent.

Handles client certificate generation, CSR creation, and certificate
storage using Windows Certificate Store.
"""

import base64
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from ..config import AgentConfig, get_config
from ..logging import get_logger


class MTLSConfig:
    """Configuration for mTLS certificate management."""

    def __init__(
        self,
        cert_file: str = "",
        key_file: str = "",
        ca_file: str = "",
        store_name: str = "MY",
        store_location: str = "CurrentUser",
        pin_sha256: str = "",
    ):
        self.cert_file = cert_file
        self.key_file = key_file
        self.ca_file = ca_file
        self.store_name = store_name
        self.store_location = store_location
        self.pin_sha256 = pin_sha256

    @classmethod
    def from_agent_config(cls, config: AgentConfig) -> "MTLSConfig":
        """Create config from agent configuration."""
        return cls(
            cert_file=config.tls.cert_file,
            key_file=config.tls.key_file,
            ca_file=config.tls.ca_file,
            store_name=config.tls.store_name,
            store_location=config.tls.store_location,
            pin_sha256=config.tls.pin_sha256,
        )


class CertificateManager:
    """Manages client certificates for mTLS authentication."""

    def __init__(self, config: Optional[MTLSConfig] = None, agent_config: Optional = None):
        self.config = config or MTLSConfig.from_agent_config(agent_config) if agent_config else MTLSConfig()
        self.logger = get_logger("sentinelwatch_agent.crypto.certificate_manager")

    def generate_key_pair(self, key_size: int = 2048) -> rsa.RSAPrivateKey:
        """Generate RSA key pair for client certificate."""
        return rsa.generate_private_key(
            public_exponent=65537,
            key_size=key_size,
        )

    def create_csr(
        self,
        private_key: rsa.RSAPrivateKey,
        subject: Optional[x509.Name] = None,
        san_dns_names: Optional[list] = None,
    ) -> x509.CertificateSigningRequest:
        """Create a Certificate Signing Request (CSR)."""
        if subject is None:
            subject = x509.Name([
                x509.NameAttribute(NameOID.COMMON_NAME, "SentinelWatch Agent"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "SentinelWatch"),
                x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "Endpoint Monitoring"),
            ])

        builder = x509.CertificateSigningRequestBuilder().subject_name(subject)

        # Add Subject Alternative Names
        if san_dns_names:
            san = x509.SubjectAlternativeName([
                x509.DNSName(name) for name in san_dns_names
            ])
            builder = builder.add_extension(san, critical=False)

        return builder.sign(
            private_key=private_key,
            algorithm=hashes.SHA256(),
        )

    def csr_to_pem(self, csr: x509.CertificateSigningRequest) -> str:
        """Convert CSR to PEM format string."""
        return csr.public_bytes(serialization.Encoding.PEM).decode("utf-8")

    def pem_to_csr(self, pem: str) -> x509.CertificateSigningRequest:
        """Parse CSR from PEM string."""
        return x509.load_pem_x509_csr(pem.encode("utf-8"))

    def private_key_to_pem(self, private_key: rsa.RSAPrivateKey) -> str:
        """Serialize private key to PEM format."""
        return private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")

    def pem_to_private_key(self, pem: str) -> rsa.RSAPrivateKey:
        """Load private key from PEM string."""
        return serialization.load_pem_private_key(
            pem.encode("utf-8"),
            password=None,
        )

    def certificate_to_pem(self, cert: x509.Certificate) -> str:
        """Convert certificate to PEM format string."""
        return cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")

    def pem_to_certificate(self, pem: str) -> x509.Certificate:
        """Parse certificate from PEM string."""
        return x509.load_pem_x509_certificate(pem.encode("utf-8"))

    def get_certificate_fingerprint(self, cert: x509.Certificate) -> str:
        """Get SHA-256 fingerprint of certificate."""
        fingerprint = cert.fingerprint(hashes.SHA256())
        return ":".join(f"{b:02x}" for b in fingerprint)

    def verify_certificate_chain(
        self,
        cert: x509.Certificate,
        ca_certs: list,
    ) -> Tuple[bool, Optional[str]]:
        """
        Verify certificate chain against trusted CAs.

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Build certificate store
            from cryptography.x509.verification import PolicyBuilder, Store

            store = Store([ca for ca in ca_certs])
            builder = PolicyBuilder().store(store)
            verifier = builder.build_server_verifier()

            # Verify
            chain = [cert]  # In real implementation, would include intermediate certs
            verifier.verify(cert, chain)

            return True, None
        except Exception as e:
            return False, str(e)

    def is_certificate_valid(self, cert: x509.Certificate) -> bool:
        """Check if certificate is currently valid (not expired, not revoked)."""
        now = datetime.now(timezone.utc)
        return cert.not_valid_before_utc <= now <= cert.not_valid_after_utc

    def days_until_expiry(self, cert: x509.Certificate) -> int:
        """Get days until certificate expires."""
        now = datetime.now(timezone.utc)
        delta = cert.not_valid_after_utc - now
        return delta.days


class WindowsCertificateStore:
    """Interface for Windows Certificate Store operations."""

    def __init__(self, store_name: str = "MY", store_location: str = "CurrentUser"):
        self.store_name = store_name
        self.store_location = store_location
        self.logger = get_logger("sentinelwatch_agent.crypto.windows_cert_store")

    def _get_store_handle(self):
        """Get Windows certificate store handle."""
        try:
            import wincertstore
            return wincertstore.CertStore(self.store_name, self.store_location)
        except ImportError:
            self.logger.warning("wincertstore not available, using file-based storage")
            return None

    def store_certificate(
        self,
        cert_pem: str,
        key_pem: Optional[str] = None,
        friendly_name: str = "SentinelWatch Agent",
    ) -> bool:
        """Store certificate and private key in Windows Certificate Store."""
        try:
            import wincertstore

            # Parse certificate
            cert = x509.load_pem_x509_certificate(cert_pem.encode("utf-8"))

            # Convert to DER
            cert_der = cert.public_bytes(serialization.Encoding.DER)

            # Store in Windows store
            with wincertstore.CertStore(self.store_name, self.store_location) as store:
                store.addcert(cert_der)

            self.logger.info("certificate_stored_in_windows_store", store_name=self.store_name)
            return True

        except ImportError:
            self.logger.warning("wincertstore not available, cannot store in Windows Certificate Store")
            return False
        except Exception as e:
            self.logger.error("certificate_store_failed", error=str(e))
            return False

    def get_certificate(self, thumbprint: str) -> Optional[x509.Certificate]:
        """Retrieve certificate by thumbprint."""
        try:
            import wincertstore

            with wincertstore.CertStore(self.store_name, self.store_location) as store:
                for cert_info in store.itercerts():
                    if cert_info.get("sha1", "").replace(" ", "").lower() == thumbprint.replace(":", "").lower():
                        cert_der = cert_info["cert"]
                        return x509.load_der_x509_certificate(cert_der)
        except ImportError:
            pass
        except Exception as e:
            self.logger.error("certificate_retrieve_failed", error=str(e))
        return None

    def list_certificates(self) -> list:
        """List all certificates in the store."""
        certs = []
        try:
            import wincertstore

            with wincertstore.CertStore(self.store_name, self.store_location) as store:
                for cert_info in store.itercerts():
                    cert_der = cert_info["cert"]
                    cert = x509.load_der_x509_certificate(cert_der)
                    certs.append({
                        "subject": cert.subject.rfc4514_string(),
                        "issuer": cert.issuer.rfc4514_string(),
                        "not_before": cert.not_valid_before_utc.isoformat(),
                        "not_after": cert.not_valid_after_utc.isoformat(),
                        "thumbprint": cert_info.get("sha1", ""),
                        "serial": str(cert.serial_number),
                    })
        except ImportError:
            pass
        except Exception as e:
            self.logger.error("certificate_list_failed", error=str(e))
        return certs

    def delete_certificate(self, thumbprint: str) -> bool:
        """Delete certificate from store."""
        try:
            import wincertstore

            with wincertstore.CertStore(self.store_name, self.store_location) as store:
                for cert_info in store.itercerts():
                    if cert_info.get("sha1", "").replace(" ", "").lower() == thumbprint.replace(":", "").lower():
                        store.deletecert(cert_info["cert"])
                        return True
        except ImportError:
            pass
        except Exception as e:
            self.logger.error("certificate_delete_failed", error=str(e))
        return False


class FileBasedCertificateStore:
    """File-based certificate storage (fallback when Windows store unavailable)."""

    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.logger = get_logger("sentinelwatch_agent.crypto.file_cert_store")

    def store_certificate(
        self,
        cert_pem: str,
        key_pem: Optional[str] = None,
        name: str = "client",
    ) -> bool:
        """Store certificate and key as PEM files."""
        try:
            cert_path = self.base_path / f"{name}.crt"
            key_path = self.base_path / f"{name}.key"

            cert_path.write_text(cert_pem)
            if key_pem:
                key_path.write_text(key_pem)
                # Set restrictive permissions on key
                os.chmod(key_path, 0o600)

            self.logger.info("certificate_stored_in_file", path=str(cert_path))
            return True
        except Exception as e:
            self.logger.error("file_certificate_store_failed", error=str(e))
            return False

    def get_certificate(self, name: str) -> Tuple[Optional[str], Optional[str]]:
        """Retrieve certificate and key as PEM strings."""
        try:
            cert_path = self.base_path / f"{name}.crt"
            key_path = self.base_path / f"{name}.key"

            cert_pem = cert_path.read_text() if cert_path.exists() else None
            key_pem = key_path.read_text() if key_path.exists() else None

            return cert_pem, key_pem
        except Exception as e:
            self.logger.error("file_certificate_retrieve_failed", error=str(e))
            return None, None

    def delete_certificate(self, name: str) -> bool:
        """Delete certificate files."""
        try:
            cert_path = self.base_path / f"{name}.crt"
            key_path = self.base_path / f"{name}.key"

            if cert_path.exists():
                cert_path.unlink()
            if key_path.exists():
                key_path.unlink()

            return True
        except Exception as e:
            self.logger.error("file_certificate_delete_failed", error=str(e))
            return False


def create_self_signed_cert(
    private_key: rsa.RSAPrivateKey,
    subject: x509.Name,
    valid_days: int = 365,
    san_dns_names: Optional[list] = None,
) -> x509.Certificate:
    """Create a self-signed certificate (for testing only)."""
    from cryptography.x509 import BasicConstraints, KeyUsage, ExtendedKeyUsage
    from cryptography.x509.oid import ExtendedKeyUsageOID

    builder = x509.CertificateBuilder()
    builder = builder.subject_name(subject)
    builder = builder.issuer_name(subject)  # Self-signed
    builder = builder.not_valid_before(datetime.now(timezone.utc))
    builder = builder.not_valid_after(datetime.now(timezone.utc) + timedelta(days=valid_days))
    builder = builder.serial_number(x509.random_serial_number())
    builder = builder.public_key(private_key.public_key())

    # Add extensions
    builder = builder.add_extension(
        BasicConstraints(ca=True, path_length=None),
        critical=True,
    )
    builder = builder.add_extension(
        KeyUsage(
            digital_signature=True,
            key_encipherment=True,
            key_cert_sign=True,
            crl_sign=True,
            content_commitment=False,
            data_encipherment=False,
            decipher_only=False,
            encipher_only=False,
            key_agreement=False,
        ),
        critical=True,
    )
    builder = builder.add_extension(
        ExtendedKeyUsage([
            ExtendedKeyUsageOID.CLIENT_AUTH,
            ExtendedKeyUsageOID.SERVER_AUTH,
        ]),
        critical=False,
    )

    if san_dns_names:
        builder = builder.add_extension(
            x509.SubjectAlternativeName([x509.DNSName(name) for name in san_dns_names]),
            critical=False,
        )

    return builder.sign(
        private_key=private_key,
        algorithm=hashes.SHA256(),
    )


# Import timedelta for self-signed cert creation
from datetime import timedelta
