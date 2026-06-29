from __future__ import annotations

from pydantic import SecretStr as PydanticSecretStr

MASK = "********"


def mask_value(value: str | PydanticSecretStr | None) -> str:
    """
    Return a masked representation of *value* suitable for logging.

    Actual secret values are never exposed in log output.
    """
    if value is None:
        return "<not set>"
    if isinstance(value, PydanticSecretStr):
        if not value.get_secret_value():
            return "<not set>"
        return MASK
    if not value:
        return "<not set>"
    return MASK


def is_secret(value: object) -> bool:
    """
    Return ``True`` if *value* is or contains a secret.

    Checks for ``SecretStr``, ``SecretBytes``, or any field name
    containing ``api_key``, ``password``, ``secret``, ``token``.
    """
    return isinstance(value, PydanticSecretStr)


def field_is_sensitive(name: str) -> bool:
    """Return ``True`` if *name* suggests it holds a secret value."""
    lowered = name.lower()
    sensitive_keywords = {"api_key", "api_secret", "password", "secret", "token", "auth"}
    return any(kw in lowered for kw in sensitive_keywords)


def str_from_secret(value: PydanticSecretStr | None) -> str | None:
    """Extract the plain-text string from a ``SecretStr``, or return ``None``."""
    if value is None:
        return None
    return value.get_secret_value()
