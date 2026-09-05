"""
Password hashing (Argon2id, OD-03) and CSRF token helpers (AD-14).
WRITTEN, NOT EXECUTED — argon2-cffi/redis have not actually run in this session.
"""
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import get_settings

settings = get_settings()

_hasher = PasswordHasher()  # Argon2id is argon2-cffi's default type


def hash_password(plain_password: str) -> str:
    return _hasher.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, plain_password)
    except VerifyMismatchError:
        return False


def validate_password_policy(plain_password: str) -> str | None:
    """Returns an error message if invalid, else None. OD-03: min length only,
    no forced composition rules."""
    if len(plain_password) < settings.PASSWORD_MIN_LENGTH:
        return f"Password must be at least {settings.PASSWORD_MIN_LENGTH} characters."
    return None


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def generate_session_token() -> str:
    return secrets.token_urlsafe(48)
