"""
Certificate and Key Management for SentinelWatch Agent.

Provides functions for key generation, CSR creation, and certificate handling.
"""

import base64
from datetime import datetime, timedelta, timezone
from typing import Optional, List

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID


def generate_key_pair(key_size: int = 2048) -> rsa.RSAPrivateKey:
    """Generate RSA key pair for client certificate."""
    return rsa.generate_private_key(
        public_exponent=65537,
        key_size=key_size,
    )


def create_csr(
    private_key: rsa.RSAPrivateKey,
    subject: Optional[x509.Name] = None,
    san_dns_names: Optional[List[str]] = None,
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


def csr_to_pem(csr: x509.CertificateSigningRequest) -> str:
    """Convert CSR to PEM format string."""
    return csr.public_bytes(serialization.Encoding.PEM).decode("utf-8")


def private_key_to_pem(private_key: rsa.RSAPrivateKey) -> str:
    """Serialize private key to PEM format."""
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")


def pem_to_private_key(pem: str) -> rsa.RSAPrivateKey:
    """Load private key from PEM string."""
    return serialization.load_pem_private_key(
        pem.encode("utf-8"),
        password=None,
    )


def certificate_to_pem(cert: x509.Certificate) -> str:
    """Convert certificate to PEM format string."""
    return cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")


def pem_to_certificate(pem: str) -> x509.Certificate:
    """Parse certificate from PEM string."""
    return x509.load_pem_x509_certificate(pem.encode("utf-8"))


def get_certificate_fingerprint(cert: x509.Certificate) -> str:
    """Get SHA-256 fingerprint of certificate."""
    fingerprint = cert.fingerprint(hashes.SHA256())
    return ":".join(f"{b:02x}" for b in fingerprint)


def is_certificate_valid(cert: x509.Certificate) -> bool:
    """Check if certificate is currently valid (not expired, not revoked)."""
    now = datetime.now(timezone.utc)
    return cert.not_valid_before_utc <= now <= cert.not_valid_after_utc


def days_until_expiry(cert: x509.Certificate) -> int:
    """Get days until certificate expires."""
    now = datetime.now(timezone.utc)
    delta = cert.not_valid_after_utc - now
    return delta.days


def create_self_signed_cert(
    private_key: rsa.RSAPrivateKey,
    subject: x509.Name,
    valid_days: int = 365,
    san_dns_names: Optional[List[str]] = None,
) -> x509.Certificate:
    """Create a self-signed certificate (for testing only)."""
    from cryptography.x509 import BasicConstraints, KeyUsage, ExtendedKeyUsage

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


# Import datetime and timezone for the module
from datetime import datetime, timezone
