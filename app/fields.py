from __future__ import annotations

import base64
import binascii
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from loguru import logger
from tortoise.fields import CharField

from app import settings

# Fernet tokens are URL-safe base64 whose first decoded byte is the version
# marker 0x80. We sniff for this before attempting decryption so that plaintext
# values Tortoise feeds through `to_python_value` during model instantiation
# (`_set_kwargs` coerces every kwarg via `to_python_value`) are passed straight
# through, while genuine ciphertext read back from the DB is decrypted — and a
# tampered token (whose 0x80 prefix survives tail corruption) still hard-fails.
_FERNET_VERSION = 0x80


def _looks_like_fernet_token(value: str) -> bool:
    try:
        raw = base64.urlsafe_b64decode(value.encode())
    except (binascii.Error, ValueError):
        return False
    return bool(raw) and raw[0] == _FERNET_VERSION


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
    key = settings.booking_field_encryption_key
    if not key:
        raise RuntimeError(
            "BOOKING_FIELD_ENCRYPTION_KEY is not set — required to encrypt "
            "guest identity fields (document_number, pin_egn)."
        )
    return Fernet(key.encode())


class EncryptedCharField(CharField):
    """CharField that transparently Fernet-encrypts on write and decrypts on read.

    Ciphertext is always longer than plaintext (base64 + IV + HMAC) — callers
    must size ``max_length`` generously (512 is used for document_number/pin_egn).
    """

    def to_db_value(self, value: str | None, instance) -> str | None:
        if value is None:
            return None
        token = _get_fernet().encrypt(value.encode()).decode()
        return super().to_db_value(token, instance)

    def to_python_value(self, value: str | None) -> str | None:
        if value is None:
            return None
        if not _looks_like_fernet_token(value):
            # Plaintext coerced during model instantiation, before it is saved.
            return super().to_python_value(value)
        try:
            plaintext = _get_fernet().decrypt(value.encode()).decode()
        except InvalidToken:
            logger.error(
                "EncryptedCharField: tamper detected, could not decrypt stored value"
            )
            raise ValueError("Stored value could not be decrypted") from None
        return super().to_python_value(plaintext)
