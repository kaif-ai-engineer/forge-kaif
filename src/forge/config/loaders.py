from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path
from typing import Any


def load_toml(path: str | Path) -> dict[str, Any]:
    """
    Parse a TOML file and return its contents as a dict.

    Raises
    ------
    ConfigurationError
        If the file cannot be parsed or contains circular references.
    """
    path = Path(path)
    if not path.exists():
        return {}

    try:
        raw = path.read_bytes()
        data: dict[str, Any] = tomllib.loads(raw.decode("utf-8"))
    except tomllib.TOMLDecodeError as exc:
        from forge.core.exceptions import ConfigurationError

        raise ConfigurationError(
            f"Failed to parse TOML file '{path}': {exc}"
        ) from exc

    _resolve_env_vars(data, path)
    return data


_ENV_REF_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _resolve_env_vars(
    data: dict[str, Any],
    source: Path,
    visited: set[str] | None = None,
) -> None:
    """Recursively resolve ``${VAR_NAME}`` references in string values."""
    if visited is None:
        visited = set()

    for key, value in data.items():
        if isinstance(value, str):
            data[key] = _resolve_string(value, source, visited)
        elif isinstance(value, dict):
            _resolve_env_vars(value, source, visited)


def _resolve_string(
    raw: str,
    source: Path,
    visited: set[str],
) -> str:
    def _replace(match: re.Match[str]) -> str:
        var = match.group(1)
        if var in visited:
            from forge.core.exceptions import ConfigurationError

            raise ConfigurationError(
                f"Circular environment variable reference detected: "
                f"{' -> '.join(visited)} -> {var} "
                f"in configuration file '{source}'"
            )
        visited.add(var)
        resolved = os.environ.get(var, "")
        # If the resolved value itself contains references, recurse
        if _ENV_REF_PATTERN.search(resolved):
            resolved = _resolve_string(resolved, source, visited)
        visited.discard(var)
        return resolved

    return _ENV_REF_PATTERN.sub(_replace, raw)


def load_dotenv(path: str | Path) -> dict[str, str]:
    """
    Load a ``.env`` file and return key-value pairs.

    Supports:
    - ``KEY=value``
    - ``KEY="quoted value"``
    - ``KEY='single quoted value'``
    - ``# comments``
    - Values containing ``=`` signs (e.g. connection strings)
    """
    path = Path(path)
    if not path.exists():
        return {}

    result: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if "=" not in stripped:
            continue

        key, _, raw_value = stripped.partition("=")
        key = key.strip()
        raw_value = raw_value.strip()

        if not key:
            continue

        # Strip surrounding quotes
        if len(raw_value) >= 2 and raw_value[0] == raw_value[-1] and raw_value[0] in ('"', "'"):  # noqa: PLR2004
            raw_value = raw_value[1:-1]

        result[key] = raw_value

    return result


def merge_config(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """
    Deep-merge *overlay* into *base*, returning a new dict.

    Later values win.  Nested dicts are merged recursively; all other
    values are replaced.
    """
    merged = dict(base)
    for key, value in overlay.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = merge_config(merged[key], value)
        else:
            merged[key] = value
    return merged


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Alias for :func:`merge_config`."""
    return merge_config(base, overlay)
