"""Symmetric encryption for secrets-at-rest (BYOK AI provider keys). Uses
`cryptography.fernet.Fernet` — a well-established, audited primitive
(AES-128-CBC + HMAC-SHA256, authenticated encryption) — not a home-rolled
cipher. The only custom step is turning `AI_KEY_ENCRYPTION_SECRET` (an
arbitrary operator-chosen string, matching every other `*_SECRET` config
value in this project, e.g. `RAZORPAY_WEBHOOK_SECRET`) into the exact
32-byte urlsafe-base64 key format Fernet requires: SHA-256 the UTF-8 secret
(a standard hash-to-fixed-length-key pattern, not an invented algorithm),
then urlsafe-base64-encode the digest. `AI_KEY_ENCRYPTION_SECRET` itself is
never modified by this file, per explicit instruction.

SECURITY BOUNDARY: neither `encrypt_secret`/`decrypt_secret` nor `_get_fernet`
ever logs a plaintext or ciphertext value, or includes one in any exception
message — only exception *types*/short descriptions.

WRITTEN, NOT EXECUTED against the real host — see work_memory.md for what
WAS genuinely executed (this file's round-trip logic, in an isolated
sandbox).
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

settings = get_settings()


class EncryptionNotConfiguredError(Exception):
    """Raised when AI_KEY_ENCRYPTION_SECRET is unset, empty, or otherwise
    cannot produce a valid Fernet key. Callers MUST fail the operation
    cleanly (a 503-class API error) when this is raised — never catch it and
    fall back to storing/using the value unencrypted."""


class DecryptionError(Exception):
    """Raised when a stored value cannot be decrypted with the currently
    configured secret. This covers three real, distinguishable-only-by-
    context cases this module deliberately does NOT try to tell apart on its
    own: (a) AI_KEY_ENCRYPTION_SECRET was rotated/changed since the value was
    encrypted, (b) the ciphertext was corrupted/tampered with, or (c) — see
    ai/service.py's own handling — the stored value was never actually
    encrypted at all (a pre-fix plaintext row, if one existed). Callers must
    NEVER catch this and silently treat the raw stored value as if it were
    the plaintext secret — that would be exactly the bug this fix exists to
    close, just moved one layer up."""


def _get_fernet() -> Fernet:
    secret = settings.AI_KEY_ENCRYPTION_SECRET
    if not secret or not secret.strip():
        raise EncryptionNotConfiguredError(
            "AI_KEY_ENCRYPTION_SECRET is not configured; refusing to encrypt or decrypt."
        )
    key_bytes = hashlib.sha256(secret.encode("utf-8")).digest()
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    try:
        return Fernet(fernet_key)
    except Exception as e:  # noqa: BLE001 — Fernet's own constructor validation
        raise EncryptionNotConfiguredError(
            "AI_KEY_ENCRYPTION_SECRET did not produce a valid encryption key."
        ) from e


def encrypt_secret(plaintext: str) -> str:
    """Returns an opaque ciphertext string safe to persist. Raises
    EncryptionNotConfiguredError if encryption isn't configured — the value
    is never stored unencrypted in that case."""
    fernet = _get_fernet()
    return fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(ciphertext: str) -> str:
    """Raises EncryptionNotConfiguredError if encryption isn't configured, or
    DecryptionError if `ciphertext` cannot be decrypted with the currently
    configured secret (see DecryptionError's docstring for the 3 real causes
    this doesn't attempt to distinguish)."""
    fernet = _get_fernet()
    try:
        return fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken as e:
        raise DecryptionError(
            "Could not decrypt the stored value with the configured encryption secret."
        ) from e
