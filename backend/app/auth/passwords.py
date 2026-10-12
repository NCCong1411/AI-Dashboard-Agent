"""Argon2id password hashing without logging plaintext values."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError


_HASHER = PasswordHasher()
_DUMMY_HASH = _HASHER.hash("timing-only-password-that-is-never-valid")


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("password must contain at least 12 characters")
    return _HASHER.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    candidate = password_hash or _DUMMY_HASH
    try:
        valid = _HASHER.verify(candidate, password)
    except (VerificationError, InvalidHashError):
        return False
    return bool(valid and password_hash is not None)
