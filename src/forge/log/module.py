from __future__ import annotations

import logging
import sys
from logging.handlers import QueueHandler, QueueListener
from queue import Queue
from typing import TYPE_CHECKING, Any, ClassVar

from forge.config.module import ConfigModule
from forge.core.module import ForgeModule, HealthResult
from forge.log.context import LogContextFilter
from forge.log.formatters import DevFormatter, JSONFormatter

if TYPE_CHECKING:
    from forge.core.runtime import ForgeRuntime

_ROOT = ""  # Python root logger name


class _BufferedHandler(logging.Handler):
    """Captures log records before the module is fully initialised."""

    def __init__(self) -> None:
        super().__init__()
        self.buffer: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.buffer.append(record)

    def flush_to(self, handler: logging.Handler) -> None:
        for record in self.buffer:
            handler.handle(record)
        self.buffer.clear()


class LogModule(ForgeModule):
    name = "log"
    dependencies: ClassVar[list[str]] = ["config"]

    def __init__(self) -> None:
        self._buffer: _BufferedHandler | None = None
        self._queue: Queue[logging.LogRecord] | None = None
        self._listener: QueueListener | None = None
        self._stream_handler: logging.StreamHandler[Any] | None = None
        self._queue_handler: QueueHandler | None = None
        self._context_filter: LogContextFilter | None = None

        self._install_buffer()

    # ── Public API ─────────────────────────────────────────────────

    def get_logger(self, name: str) -> logging.Logger:
        """Return a logger for *name* configured by this module."""
        logger = logging.getLogger(name)
        if self._context_filter is not None and logger.level == logging.NOTSET:
            logger.setLevel(logging.DEBUG)
        return logger

    # ── ForgeModule ────────────────────────────────────────────────

    async def setup(self, runtime: ForgeRuntime) -> None:
        config_module: ConfigModule = runtime.get(ConfigModule)  # type: ignore[assignment]
        log_cfg = config_module.config.log

        level: int = getattr(logging, log_cfg.level.upper(), logging.INFO)

        if log_cfg.format == "json":
            formatter: logging.Formatter = JSONFormatter()
        else:
            formatter = DevFormatter()

        # Build non-blocking pipeline: logger → QueueHandler → Queue → QueueListener → StreamHandler
        self._stream_handler = logging.StreamHandler(sys.stderr)
        self._stream_handler.setFormatter(formatter)
        self._stream_handler.setLevel(level)

        self._queue = Queue(-1)
        self._queue_handler = QueueHandler(self._queue)
        self._queue_handler.setLevel(logging.DEBUG)

        self._listener = QueueListener(self._queue, self._stream_handler)
        self._listener.start()

        # Context filter injects LogContext fields into records
        self._context_filter = LogContextFilter()

        # Wire into root logger
        root = logging.getLogger(_ROOT)
        root.addFilter(self._context_filter)
        root.addHandler(self._queue_handler)
        root.setLevel(logging.DEBUG)

        # Remove the pre-init buffer and flush captured records
        if self._buffer is not None:
            root.removeHandler(self._buffer)
            self._buffer.flush_to(self._stream_handler)
            self._buffer = None

        # Set per-module log levels from config
        for module_name, level_name in log_cfg.levels.items():
            logger = logging.getLogger(module_name)
            logger.setLevel(
                getattr(logging, level_name.upper(), logging.NOTSET)
            )

    async def teardown(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

        root = logging.getLogger(_ROOT)
        if self._queue_handler is not None:
            root.removeHandler(self._queue_handler)
            self._queue_handler = None

        self._queue = None
        self._stream_handler = None

    def health_check(self) -> HealthResult:
        if self._listener is None:
            return HealthResult.error("Log listener not running")
        if self._listener._thread is None or not self._listener._thread.is_alive():
            return HealthResult.error("Log listener thread died")
        return HealthResult.ok()

    # ── Internal ───────────────────────────────────────────────────

    def _install_buffer(self) -> None:
        """Install a buffered handler on the root logger before init."""
        self._buffer = _BufferedHandler()
        root = logging.getLogger(_ROOT)
        root.addHandler(self._buffer)
        root.setLevel(logging.DEBUG)


