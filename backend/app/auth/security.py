"""Password hashing, JWT issuance/validation, and one-way token hashing."""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
from jose import JWTError, jwt

from app.config import get_settings

# ponytail: constants, not settings — promote to config when someone needs to tune them
ACCESS_TOKEN_MINUTES = 30
REFRESH_TOKEN_DAYS = 14
RESET_TOKEN_MINUTES = 60  # short-lived per Document 05 §5
VERIFY_TOKEN_HOURS = 24
INVITE_TOKEN_DAYS = 7

_ALGORITHM = "HS256"


MAX_PASSWORD_BYTES = 72  # bcrypt's own limit; >= 4.1 raises instead of truncating


def _bcrypt_bytes(password: str) -> bytes:
    # Schemas reject longer passwords with a 422, but login and any future caller
    # reach the hasher directly — truncate here so no path can raise a ValueError.
    return password.encode()[:MAX_PASSWORD_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_bcrypt_bytes(password), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(_bcrypt_bytes(password), password_hash.encode())


def new_raw_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(raw: str) -> str:
    # One-way (Document 05 §8) — compared against a client-presented raw token
    return hashlib.sha256(raw.encode()).hexdigest()


def create_access_token(user_id: uuid.UUID, role: str, team_id: uuid.UUID | None) -> str:
    claims = {
        "sub": str(user_id),
        "role": role,
        "team_id": str(team_id) if team_id else None,
        "exp": datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_MINUTES),
    }
    return jwt.encode(claims, get_settings().jwt_secret, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, get_settings().jwt_secret, algorithms=[_ALGORITHM])
    except JWTError:
        return None
