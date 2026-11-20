"""Tests for configuration signing and verification."""
import pytest

from sentinelwatch_backend.security.config_signing import sign_config, verify_signature


class TestConfigSigning:
    def test_sign_and_verify_round_trip(self):
        payload = {"collection_interval": 30, "batch_size": 100}
        secret = b"super-secret-key-32-bytes-long!!"
        sig = sign_config(payload, secret)
        assert isinstance(sig, str)
        assert len(sig) == 64  # hex SHA-256
        assert verify_signature(payload, sig, secret) is True

    def test_different_secret_fails_verification(self):
        payload = {"foo": "bar"}
        secret_a = b"key-a-exactly-thirty-two-b!!"
        secret_b = b"key-b-exactly-thirty-two-b!!"
        sig = sign_config(payload, secret_a)
        assert verify_signature(payload, sig, secret_b) is False

    def test_tampered_payload_fails_verification(self):
        payload = {"value": 1}
        secret = b"super-secret-key-32-bytes-long!!"
        sig = sign_config(payload, secret)
        payload["value"] = 2
        assert verify_signature(payload, sig, secret) is False

    def test_canonical_form_is_stable_across_dict_orderings(self):
        """Sorted keys ensure identical payloads produce identical signatures."""
        secret = b"super-secret-key-32-bytes-long!!"
        a = sign_config({"a": 1, "b": 2}, secret)
        b_sig = sign_config({"b": 2, "a": 1}, secret)
        assert a == b_sig

    def test_empty_secret_handled(self):
        """Graceful degradation — empty secret still produces a valid (but untrusted) signature."""
        sig = sign_config({}, b"")
        assert isinstance(sig, str)
        assert verify_signature({}, sig, b"") is True
