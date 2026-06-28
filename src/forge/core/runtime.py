from __future__ import annotations

import asyncio
import logging
import signal
from collections.abc import Awaitable, Callable
from typing import Any, ClassVar, Self

from forge.core.container import Container
from forge.core.events import EventBus
from forge.core.exceptions import ForgeError, ModuleStateError
from forge.core.module import ForgeModule, ModuleLifecycleState

_log = logging.getLogger(__name__)

ShutdownHook = Callable[[], Awaitable[Any]]


class ForgeRuntime:
    """
    Central runtime coordinator for the forge framework.

    Manages module lifecycle, dependency injection, event dispatch,
    and graceful shutdown.

    Usage::

        runtime = ForgeRuntime()
        runtime.register(ConfigModule())
        await runtime.init()
        # ... application code ...
        await runtime.teardown()
    """

    _active: ClassVar[ForgeRuntime | None] = None

    @classmethod
    def get_active(cls) -> ForgeRuntime:
        """
        Return the active initialized runtime instance.

        Raises
        ------
        RuntimeNotInitializedError
            When no runtime is currently active/initialized.
        """
        if cls._active is None or not cls._active.is_initialized:
            from forge.core.exceptions import RuntimeNotInitializedError

            raise RuntimeNotInitializedError("Runtime is not initialized.")
        return cls._active

    def __init__(self) -> None:
        self._initialized = False
        self._shutting_down = False
        self._shutdown_timeout: float = 30.0
        self._container = Container()
        self._events = EventBus()
        self._ready_hooks: list[ShutdownHook] = []
        self._shutdown_hooks: list[ShutdownHook] = []
        self._loop: asyncio.AbstractEventLoop | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def events(self) -> EventBus:
        """The runtime event bus."""
        return self._events

    @property
    def container(self) -> Container:
        """The dependency injection container."""
        return self._container

    @property
    def is_initialized(self) -> bool:
        """Return ``True`` after :meth:`init` completes successfully."""
        return self._initialized

    @property
    def is_shutting_down(self) -> bool:
        """Return ``True`` during graceful shutdown."""
        return self._shutting_down

    # ------------------------------------------------------------------
    # Module registration
    # ------------------------------------------------------------------

    def register(self, module: ForgeModule, *, replace: bool = False) -> Self:
        """
        Register a module with the runtime.

        Parameters
        ----------
        module:
            An instantiated ``ForgeModule`` subclass.
        replace:
            If ``True``, silently replace an existing registration.

        Returns
        -------
        Self
            For method chaining.
        """
        self._container.register(module, replace=replace)
        return self

    def use_defaults(self) -> Self:
        """
        Register all default modules (config, log, retry, health, cache).

        This is a convenience method for standard applications.
        For custom configurations, register modules individually.

        Returns
        -------
        Self
            For method chaining.
        """
        from forge.config.module import ConfigModule
        from forge.log.module import LogModule
        from forge.retry.module import RetryModule

        self.register(ConfigModule())
        self.register(LogModule())
        self.register(RetryModule())

        try:
            from forge.health.module import HealthModule  # type: ignore[import-untyped]

            self.register(HealthModule())
        except ImportError:
            pass

        try:
            from forge.cache.module import CacheModule  # type: ignore[import-untyped]

            self.register(CacheModule())
        except ImportError:
            pass

        return self

    def get(self, module_type: type[ForgeModule]) -> ForgeModule:
        """
        Retrieve a registered module by its class.

        Raises ``ModuleNotFoundError`` if not registered.
        """
        return self._container.get(module_type)

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    def on_ready(self, callback: ShutdownHook) -> None:
        """
        Register a callback invoked after all modules are initialised.

        The callback must be an async function.
        """
        self._ready_hooks.append(callback)

    def on_shutdown(self, callback: ShutdownHook) -> None:
        """
        Register a callback invoked before teardown begins.

        The callback must be an async function.
        """
        self._shutdown_hooks.append(callback)

    # ------------------------------------------------------------------
    # Initialisation & teardown
    # ------------------------------------------------------------------

    async def init(self, shutdown_timeout: float = 30.0) -> None:
        """
        Initialise all registered modules in dependency order.

        Parameters
        ----------
        shutdown_timeout:
            Seconds to wait for graceful shutdown before forcible stop.
        """
        if self._initialized:
            raise ForgeError("Runtime is already initialised.")

        self._shutdown_timeout = shutdown_timeout
        self._loop = asyncio.get_running_loop()

        self._install_signal_handlers()

        modules = self._container.initialization_order()

        for module in modules:
            try:
                module._transition(ModuleLifecycleState.INITIALIZING)
                await module.setup(self)
                module._transition(ModuleLifecycleState.READY)
            except ModuleStateError:
                raise
            except Exception as exc:
                raise ForgeError(f"Failed to initialise module '{module.name}': {exc}") from exc

        await self._events.emit("runtime.ready")
        for hook in self._ready_hooks:
            await hook()

        self._initialized = True
        ForgeRuntime._active = self

    async def teardown(self) -> None:
        """
        Shut down all modules in reverse dependency order.

        Safe to call multiple times; subsequent calls are no-ops.
        """
        if self._shutting_down:
            return
        self._shutting_down = True

        await self._events.emit("runtime.shutdown")
        for hook in self._shutdown_hooks:
            try:
                await hook()
            except Exception:
                _log.exception("Shutdown hook failed")

        modules = list(reversed(self._container.initialization_order()))

        for module in modules:
            if module._lifecycle_state not in (
                ModuleLifecycleState.READY,
                ModuleLifecycleState.INITIALIZING,
            ):
                continue
            try:
                module._transition(ModuleLifecycleState.TEARDOWN)
                await module.teardown()
                module._transition(ModuleLifecycleState.STOPPED)
            except Exception:
                _log.exception("Error tearing down module '%s'", module.name)

        self._initialized = False
        if ForgeRuntime._active is self:
            ForgeRuntime._active = None

    # ------------------------------------------------------------------
    # Signal handling
    # ------------------------------------------------------------------

    def _install_signal_handlers(self) -> None:
        if self._loop is None:
            return
        try:

            def _make_handler(sig: signal.Signals) -> Callable[[], None]:
                def _handler() -> None:
                    self._handle_signal(sig)

                return _handler

            for sig in (signal.SIGTERM, signal.SIGINT):
                self._loop.add_signal_handler(sig, _make_handler(sig))
        except (NotImplementedError, ValueError):
            _log.warning("Signal handlers are not available on this platform.")

    def _handle_signal(self, sig: signal.Signals) -> None:
        _log.info("Received signal %s, initiating graceful shutdown...", sig.name)
        if self._loop is not None and not self._shutting_down:
            asyncio.ensure_future(self._shutdown_with_timeout(), loop=self._loop)  # noqa: RUF006

    async def _shutdown_with_timeout(self) -> None:
        try:
            await asyncio.wait_for(
                self.teardown(),
                timeout=self._shutdown_timeout,
            )
        except TimeoutError:
            _log.warning(
                "Shutdown timed out after %.1f seconds.",
                self._shutdown_timeout,
            )
        except Exception:
            _log.exception("Unexpected error during shutdown")
