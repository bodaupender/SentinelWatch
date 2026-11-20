"""
JWT Token handling for SentinelWatch Backend.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from pydantic import BaseModel

from jose import jwt, JWTError

from ..config import get_config


class TokenData(BaseModel):
    """Decoded token data."""
    sub: str
    role: str
    exp: int
    iat: int
    type: str = "access"


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    """Create a JWT access token."""
    config = get_config()
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=config.auth.access_token_expire_minutes))
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc), "type": to_encode.get("type", "access")})
    encoded_jwt = jwt.encode(to_encode, config.auth.jwt_secret, algorithm=config.auth.jwt_algorithm)
    return encoded_jwt


def create_refresh_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    """Create a JWT refresh token."""
    config = get_config()
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(days=config.auth.refresh_token_expire_days))
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc), "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, config.auth.jwt_secret, algorithm=config.auth.jwt_algorithm)
    return encoded_jwt


def decode_token(token: str) -> Dict[str, Any]:
    """Decode and validate a JWT token."""
    config = get_config()
    try:
        payload = jwt.decode(token, config.auth.jwt_secret, algorithms=[config.auth.jwt_algorithm])
        return payload
    except JWTError:
        raise ValueError("Invalid token")


def verify_token(token: str) -> bool:
    """Verify if a token is valid."""
    try:
        decode_token(token)
        return True
    except ValueError:
        return False
