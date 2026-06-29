from __future__ import annotations

import logging
from typing import Any


class LoggerProxy:
    """
    Wraps a standard logging.Logger to support direct keyword arguments.

    Example::

        logger = log.get("module")
        logger.info("user logged in", user_id=123, ip="127.0.0.1")
        # → keyword arguments are merged into the structured extra fields.
    """

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.DEBUG, msg, args, kwargs)

    def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.INFO, msg, args, kwargs)

    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.WARNING, msg, args, kwargs)

    def warn(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.WARNING, msg, args, kwargs)

    def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.ERROR, msg, args, kwargs)

    def critical(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.CRITICAL, msg, args, kwargs)

    def exception(self, msg: str, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("exc_info", True)
        self._log(logging.ERROR, msg, args, kwargs)

    def log(self, level: int, msg: str, *args: Any, **kwargs: Any) -> None:
        self._log(level, msg, args, kwargs)

    def _log(self, level: int, msg: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        # Standard logging parameters accepted by Logger._log/log:
        # exc_info, stack_info, stacklevel, extra
        std_keys = {"exc_info", "stack_info", "stacklevel"}
        extra = {}
        log_kwargs = {}

        for k, v in kwargs.items():
            if k in std_keys:
                log_kwargs[k] = v
            elif k == "extra":
                if isinstance(v, dict):
                    extra.update(v)
            else:
                extra[k] = v

        if extra:
            log_kwargs["extra"] = extra

        self._logger.log(level, msg, *args, **log_kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._logger, name)
