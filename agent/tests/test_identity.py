"""Tests for Endpoint Identity Management."""

import json
import base64
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from sentinelwatch_agent.identity import EndpointIdentity, create_identity_manager


class TestEndpointIdentity:
    """Tests for EndpointIdentity class."""

    @pytest.fixture
    def temp_data_dir(self):
        """Create a temporary directory for identity storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def identity_manager(self, temp_data_dir):
        """Create an EndpointIdentity instance with temp directory."""
        return EndpointIdentity(temp_data_dir)

    @pytest.fixture
    def mock_fingerprint(self):
        """Return a mock fingerprint for testing."""
        return {
            "machine_guid": "test-guid-12345",
            "hostname": "TEST-HOST",
            "platform": "Windows-10-10.0.19041-SP0",
            "processor": "Intel64 Family 6 Model 142 Stepping 10, GenuineIntel",
            "architecture": "64bit",
        }

    def test_create_new_identity(self, identity_manager):
        """Test creating a new identity."""
        identity = identity_manager.create_new_identity("test-token")

        assert identity["version"] == EndpointIdentity.IDENTITY_VERSION
        assert identity["agent_id"] == ""
        assert identity["enrollment_token"] == "test-token"
        assert "identity_hash" in identity
        assert "fingerprint" in identity
        assert "private_key_pem" in identity
        assert "created_at" in identity
        assert identity["registration_count"] == 0

    def test_save_and_load_identity(self, identity_manager):
        """Test saving and loading identity."""
        identity = identity_manager.create_new_identity("test-token")
        identity["agent_id"] = "test-agent-123"

        # Save
        assert identity_manager.save(identity)

        # Load
        loaded = identity_manager.load()
        assert loaded is not None
        assert loaded["agent_id"] == "test-agent-123"
        assert loaded["enrollment_token"] == "test-token"

    def test_refresh_token_is_protected_at_rest(self, identity_manager, monkeypatch):
        monkeypatch.setattr(
            EndpointIdentity,
            "_protect_secret",
            staticmethod(lambda value: "test-protected:" + base64.b64encode(value.encode()).decode()),
        )
        monkeypatch.setattr(
            EndpointIdentity,
            "_unprotect_secret",
            staticmethod(lambda value: base64.b64decode(value.removeprefix("test-protected:")).decode()),
        )
        identity = identity_manager.create_new_identity("enrollment-secret")
        identity["agent_id"] = "agent-a"
        identity["agent_token"] = "access-secret"
        identity["agent_refresh_token"] = "refresh-secret"

        assert identity_manager.save(identity)
        stored = identity_manager.identity_file.read_text(encoding="utf-8")
        assert '"agent_refresh_token": "refresh-secret"' not in stored
        assert "agent_refresh_token_protected" in stored

        loaded = identity_manager.load()
        assert loaded["agent_refresh_token"] == "refresh-secret"

    def test_successful_enrollment_clears_one_time_token_and_old_ciphertext(self, identity_manager, monkeypatch):
        monkeypatch.setattr(
            EndpointIdentity,
            "_protect_secret",
            staticmethod(lambda value: "test-protected:" + base64.b64encode(value.encode()).decode()),
        )
        monkeypatch.setattr(
            EndpointIdentity,
            "_unprotect_secret",
            staticmethod(lambda value: base64.b64decode(value.removeprefix("test-protected:")).decode()),
        )
        identity_manager.get_or_create_identity("one-time-enrollment-token")

        assert identity_manager.update_agent_token("agent-a", "access", "refresh")

        stored = identity_manager.identity_file.read_text(encoding="utf-8")
        assert "enrollment_token_protected" not in stored
        loaded = identity_manager.load()
        assert not loaded.get("enrollment_token")
        assert loaded["agent_token"] == "access"
        assert loaded["agent_refresh_token"] == "refresh"

        # The original config can still contain the consumed token after restart.
        # It must be recognized without restoring that secret or discarding credentials.
        restarted = identity_manager.get_or_create_identity("one-time-enrollment-token")
        assert not restarted.get("enrollment_token")
        assert restarted["agent_token"] == "access"
        assert restarted["agent_refresh_token"] == "refresh"

    def test_load_nonexistent_identity(self, identity_manager):
        """Test loading when no identity exists."""
        loaded = identity_manager.load()
        assert loaded is None

    def test_get_or_create_identity(self, identity_manager):
        """Test get_or_create_identity loads existing or creates new."""
        # First call should create
        identity1 = identity_manager.get_or_create_identity("token1")
        assert identity1["enrollment_token"] == "token1"

        # A different configured enrollment token explicitly requests re-enrollment.
        identity2 = identity_manager.get_or_create_identity("token2")
        assert identity2["enrollment_token"] == "token2"

    def test_update_after_registration(self, identity_manager):
        """Test updating identity after backend registration."""
        identity = identity_manager.create_new_identity("test-token")
        identity_manager.save(identity)

        # Update after registration
        assert identity_manager.update_after_registration("new-agent-id")

        # Verify update
        loaded = identity_manager.load()
        assert loaded["agent_id"] == "new-agent-id"
        assert loaded["registration_count"] == 1
        assert loaded["last_registration"] is not None

    def test_update_after_registration_no_identity(self, identity_manager):
        """Test update_after_registration when no identity exists."""
        result = identity_manager.update_after_registration("agent-id")
        assert result is False

    def test_get_agent_id(self, identity_manager):
        """Test getting agent ID."""
        assert identity_manager.get_agent_id() is None

        identity = identity_manager.create_new_identity("token")
        identity["agent_id"] = "test-agent"
        identity_manager.save(identity)

        assert identity_manager.get_agent_id() == "test-agent"

    def test_get_private_key_pem(self, identity_manager):
        """Test getting private key."""
        assert identity_manager.get_private_key_pem() is None

        identity = identity_manager.create_new_identity("token")
        identity_manager.save(identity)

        key = identity_manager.get_private_key_pem()
        assert key is not None
        assert "PRIVATE KEY" in key

    def test_needs_re_enrollment_no_identity(self, identity_manager):
        """Test needs_re_enrollment with no identity."""
        needs, reason = identity_manager.needs_re_enrollment()
        assert needs is True
        assert reason == "no_identity"

    def test_needs_re_enrollment_no_agent_id(self, identity_manager):
        """Test needs_re_enrollment with identity but no agent_id."""
        identity = identity_manager.create_new_identity("token")
        identity_manager.save(identity)

        needs, reason = identity_manager.needs_re_enrollment()
        assert needs is True
        assert reason == "no_agent_id"

    def test_needs_re_enrollment_agent_id_mismatch(self, identity_manager):
        """Test needs_re_enrollment with agent ID mismatch."""
        identity = identity_manager.create_new_identity("token")
        identity["agent_id"] = "local-agent-id"
        identity_manager.save(identity)

        needs, reason = identity_manager.needs_re_enrollment("backend-agent-id")
        assert needs is True
        assert "agent_id_mismatch" in reason

    def test_needs_re_enrollment_valid(self, identity_manager):
        """Test needs_re_enrollment with valid identity."""
        identity = identity_manager.create_new_identity("token")
        identity["agent_id"] = "matching-agent-id"
        identity_manager.save(identity)

        needs, reason = identity_manager.needs_re_enrollment("matching-agent-id")
        assert needs is False
        assert reason == "valid"

    @patch("sentinelwatch_agent.identity.EndpointIdentity.generate_machine_fingerprint")
    def test_needs_re_enrollment_fingerprint_mismatch(self, mock_fingerprint, identity_manager):
        """Test needs_re_enrollment with fingerprint mismatch."""
        mock_fingerprint.return_value = {"new": "fingerprint"}

        identity = identity_manager.create_new_identity("token")
        identity["agent_id"] = "matching-agent-id"
        identity["fingerprint"] = {"old": "fingerprint"}
        identity_manager.save(identity)

        needs, reason = identity_manager.needs_re_enrollment("matching-agent-id")
        assert needs is True
        assert reason == "fingerprint_mismatch"

    def test_reset_identity(self, identity_manager):
        """Test identity reset."""
        identity = identity_manager.create_new_identity("token")
        identity["agent_id"] = "test-agent"
        identity_manager.save(identity)

        # Reset
        assert identity_manager.reset_identity()

        # Should need re-enrollment now
        needs, reason = identity_manager.needs_re_enrollment()
        assert needs is True
        assert reason == "no_identity"

        # Old file should be backed up
        backup_files = list(identity_manager.data_dir.glob("*.bak.*"))
        assert len(backup_files) == 1

    @pytest.mark.skipif(os.name != "nt", reason="Credential protection uses Windows DPAPI")
    def test_agent_credential_survives_restart_without_plaintext_on_disk(self, identity_manager):
        identity_manager.get_or_create_identity("enrollment-secret-value")
        assert identity_manager.update_agent_token("agent-123", "agent-bearer-secret-value")

        saved_text = identity_manager.identity_file.read_text(encoding="utf-8")
        assert "enrollment-secret-value" not in saved_text
        assert "agent-bearer-secret-value" not in saved_text
        assert "PRIVATE KEY" not in saved_text

        restarted_manager = EndpointIdentity(identity_manager.data_dir)
        loaded = restarted_manager.load()
        assert loaded is not None
        assert loaded["agent_id"] == "agent-123"
        assert not loaded.get("enrollment_token")
        assert loaded["enrollment_token_hash"]
        assert loaded["agent_token"] == "agent-bearer-secret-value"
        assert "PRIVATE KEY" in loaded["private_key_pem"]

    @pytest.mark.skipif(os.name != "nt", reason="Credential protection uses Windows DPAPI")
    def test_new_enrollment_token_clears_previous_agent_credential(self, identity_manager):
        identity_manager.get_or_create_identity("old-enrollment-token")
        identity_manager.update_agent_token("agent-123", "old-agent-token")

        updated = identity_manager.get_or_create_identity("new-enrollment-token")
        assert updated["enrollment_token"] == "new-enrollment-token"
        assert "agent_token" not in updated

    def test_identity_hash_consistency(self, identity_manager):
        """Test that identity hash is consistent for same fingerprint."""
        fingerprint1 = {
            "machine_guid": "guid-123",
            "hostname": "HOST1",
            "platform": "Windows",
            "processor": "Intel",
            "architecture": "64bit",
        }

        fingerprint2 = {
            "machine_guid": "guid-123",
            "hostname": "HOST1",
            "platform": "Windows",
            "processor": "Intel",
            "architecture": "64bit",
        }

        hash1 = identity_manager.compute_identity_hash(fingerprint1)
        hash2 = identity_manager.compute_identity_hash(fingerprint2)

        assert hash1 == hash2
        assert len(hash1) == 32  # SHA256 truncated to 32 chars

    def test_identity_hash_different_for_different_fingerprint(self, identity_manager):
        """Test that identity hash differs for different fingerprints."""
        fingerprint1 = {"machine_guid": "guid-1", "hostname": "HOST1"}
        fingerprint2 = {"machine_guid": "guid-2", "hostname": "HOST2"}

        hash1 = identity_manager.compute_identity_hash(fingerprint1)
        hash2 = identity_manager.compute_identity_hash(fingerprint2)

        assert hash1 != hash2

    def test_create_identity_manager_factory(self, temp_data_dir):
        """Test factory function."""
        manager = create_identity_manager(temp_data_dir)
        assert isinstance(manager, EndpointIdentity)
        assert manager.data_dir == temp_data_dir

    @patch("sentinelwatch_agent.identity.platform.node")
    @patch("sentinelwatch_agent.identity.platform.platform")
    def test_fingerprint_generation(self, mock_platform, mock_node, identity_manager):
        """Test fingerprint generation includes required fields."""
        mock_node.return_value = "TEST-HOST"
        mock_platform.return_value = "Windows-10"

        fingerprint = identity_manager.generate_machine_fingerprint()

        assert "machine_guid" in fingerprint
        assert "hostname" in fingerprint
        assert "platform" in fingerprint
        assert "processor" in fingerprint
        assert "architecture" in fingerprint


class TestIdentityIntegration:
    """Integration tests for identity workflow."""

    @pytest.fixture
    def temp_data_dir(self):
        """Create a temporary directory for identity storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def identity_manager(self, temp_data_dir):
        """Create an EndpointIdentity instance with temp directory."""
        return EndpointIdentity(temp_data_dir)

    def test_full_enrollment_workflow(self, identity_manager):
        """Test complete enrollment workflow."""
        # 1. Fresh start - no identity
        assert identity_manager.load() is None

        # 2. Get or create identity (creates new)
        identity = identity_manager.get_or_create_identity("enrollment-token-123")
        assert identity["enrollment_token"] == "enrollment-token-123"
        assert identity["agent_id"] == ""

        # 3. Simulate backend registration
        identity_manager.update_after_registration("backend-agent-id-456")

        # 4. Verify identity updated
        loaded = identity_manager.load()
        assert loaded["agent_id"] == "backend-agent-id-456"
        assert loaded["registration_count"] == 1

        # 5. Agent restarts - load identity
        new_manager = EndpointIdentity(identity_manager.data_dir)
        loaded = new_manager.load()
        assert loaded["agent_id"] == "backend-agent-id-456"
        assert loaded["registration_count"] == 1

        # 6. Needs re-enrollment check
        needs, reason = new_manager.needs_re_enrollment("backend-agent-id-456")
        assert needs is False
        assert reason == "valid"

    def test_re_enrollment_workflow(self, identity_manager):
        """Test re-enrollment after VM copy."""
        # 1. Initial enrollment
        identity = identity_manager.get_or_create_identity("token-1")
        identity_manager.update_after_registration("agent-original")

        # 2. Simulate VM copy - fingerprint changes
        with patch.object(identity_manager, "generate_machine_fingerprint") as mock:
            mock.return_value = {"machine_guid": "new-guid", "hostname": "NEW-HOST"}

            # 3. Check needs re-enrollment
            needs, reason = identity_manager.needs_re_enrollment("agent-original")
            assert needs is True
            assert reason == "fingerprint_mismatch"

            # 4. Reset identity for re-enrollment
            identity_manager.reset_identity()

            # 5. New identity created with new fingerprint
            new_identity = identity_manager.get_or_create_identity("token-2")
            assert new_identity["fingerprint"] == {"machine_guid": "new-guid", "hostname": "NEW-HOST"}

            # 6. Re-enrollment with backend
            identity_manager.update_after_registration("agent-re-enrolled")

            # 7. Verify - after reset, registration_count starts fresh at 1
            loaded = identity_manager.load()
            assert loaded["agent_id"] == "agent-re-enrolled"
            assert loaded["registration_count"] == 1  # New identity, starts at 1

    def test_duplicate_identity_detection(self, identity_manager):
        """Test detection of duplicate/copied VM identities."""
        # 1. First agent registers
        identity1 = identity_manager.get_or_create_identity("token-1")
        identity1["agent_id"] = "agent-1"
        identity1["fingerprint"]["machine_guid"] = "guid-A"
        identity_manager.save(identity1)

        # 2. Second agent with different machine_guid tries to register
        # (This would be caught by backend, but agent can detect locally too)
        identity_manager.reset_identity()
        identity2 = identity_manager.get_or_create_identity("token-2")
        identity2["fingerprint"]["machine_guid"] = "guid-B"
        identity_manager.save(identity2)

        # Verify different machine GUIDs
        assert identity1["fingerprint"]["machine_guid"] != identity2["fingerprint"]["machine_guid"]

    def test_invalid_identity_rejected(self, identity_manager):
        """Test that corrupted identity files are preserved instead of overwritten."""
        # Write invalid JSON
        identity_manager.identity_file.write_text("not valid json")

        with pytest.raises(RuntimeError, match="could not be decrypted or read"):
            identity_manager.get_or_create_identity("token")
        assert identity_manager.identity_file.read_text(encoding="utf-8") == "not valid json"

    def test_version_mismatch_rejected(self, identity_manager):
        """Test that wrong version identities are rejected on load (not save, since save normalizes)."""
        identity = identity_manager.create_new_identity("token")
        identity_manager.save(identity)

        # Manually corrupt the file with wrong version
        with identity_manager.identity_file.open("r") as f:
            data = json.load(f)
        data["version"] = 999
        with identity_manager.identity_file.open("w") as f:
            json.dump(data, f)

        with pytest.raises(RuntimeError, match="unsupported"):
            identity_manager.load()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
