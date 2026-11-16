"""Field-level encryption (Fernet / MultiFernet) and HMAC blind indexes.

Key rotation: put the NEW key first in ``FIELD_ENCRYPTION_KEYS`` and keep the old keys after it.
Everything still decrypts. Then run ``manage.py rotate_encryption_keys`` to re-encrypt every row with the
new key, and finally drop the old key from the environment.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)

DECRYPTION_FAILED = "[unreadable: encryption key missing]"


@lru_cache(maxsize=1)
def _multifernet(keys: tuple[str, ...]) -> MultiFernet:
    if not keys:
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEYS must contain at least one Fernet key.")
    try:
        return MultiFernet([Fernet(k.encode()) for k in keys])
    except (ValueError, TypeError) as exc:  # pragma: no cover - configuration error path
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEYS contains an invalid Fernet key.") from exc


def get_fernet() -> MultiFernet:
    return _multifernet(tuple(k.strip() for k in settings.FIELD_ENCRYPTION_KEYS if k.strip()))


def encrypt_str(value: str) -> str:
    return get_fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_str(token: str) -> str:
    try:
        return get_fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeEncodeError):
        logger.error("Field decryption failed; check FIELD_ENCRYPTION_KEYS.")
        return DECRYPTION_FAILED


def rotate_token(token: str) -> str:
    """Re-encrypt an existing token with the primary (first) key."""
    return get_fernet().rotate(token.encode("ascii")).decode("ascii")


def is_encrypted_token(value: str) -> bool:
    try:
        get_fernet().extract_timestamp(value.encode("ascii"))
    except (InvalidToken, UnicodeEncodeError, ValueError):
        return False
    return True


def blind_index(value: str | None) -> str:
    """Deterministic keyed hash of a normalised value (e.g. email) for lookups.

    The plaintext is never stored; the HMAC key is separate from the encryption keys.
    """
    if not value:
        return ""
    normalised = value.strip().lower().encode("utf-8")
    key = settings.BLIND_INDEX_KEY.encode("utf-8")
    return hmac.new(key, normalised, hashlib.sha256).hexdigest()
