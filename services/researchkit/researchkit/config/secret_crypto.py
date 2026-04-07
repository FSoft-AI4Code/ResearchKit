import base64
import os
import re

ENCRYPTION_KEY_ENV = "RESEARCHKIT_CONFIG_ENCRYPTION_KEY"
_HEX_KEY_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def _load_fernet():
    try:
        from cryptography.fernet import Fernet, InvalidToken
    except ImportError as exc:
        raise ValueError(
            "cryptography package is required for encrypted ResearchKit config secrets."
        ) from exc
    return Fernet, InvalidToken


def _get_raw_key() -> str:
    return os.getenv(ENCRYPTION_KEY_ENV, "").strip()


def _normalize_fernet_key(raw_key: str) -> bytes:
    if not raw_key:
        raise ValueError(
            f"Missing {ENCRYPTION_KEY_ENV}. Set a Fernet key or 64-char hex key."
        )

    if _HEX_KEY_RE.fullmatch(raw_key):
        key_bytes = bytes.fromhex(raw_key)
        return base64.urlsafe_b64encode(key_bytes)

    try:
        decoded = base64.urlsafe_b64decode(raw_key.encode("utf-8"))
    except Exception as exc:
        raise ValueError(
            f"Invalid {ENCRYPTION_KEY_ENV} format. Use a Fernet key or 64-char hex key."
        ) from exc

    if len(decoded) != 32:
        raise ValueError(
            f"Invalid {ENCRYPTION_KEY_ENV} length. Expected 32 decoded bytes."
        )

    return base64.urlsafe_b64encode(decoded)


def _get_cipher():
    Fernet, _ = _load_fernet()
    return Fernet(_normalize_fernet_key(_get_raw_key()))


def encrypt_secret(plain_text: str) -> str:
    cipher = _get_cipher()
    return cipher.encrypt(plain_text.encode("utf-8")).decode("utf-8")


def decrypt_secret(cipher_text: str) -> str:
    _, InvalidToken = _load_fernet()
    cipher = _get_cipher()
    try:
        return cipher.decrypt(cipher_text.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Encrypted secret token is invalid or cannot be decrypted.") from exc
