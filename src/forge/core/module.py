from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from forge.core.runtime import ForgeRuntime as Runtime


class ModuleLifecycleState(enum.Enum):
    """Lifecycle states for a forge module."""

    UNREGISTERED = "UNREGISTERED"
    REGISTERED = "REGISTERED"
    INITIALIZING = "INITIALIZING"
    READY = "READY"
    TEARDOWN = "TEARDOWN"
    STOPPED = "STOPPED"


class HealthResult:
    """Result of a single health check."""

    OK = "ok"
    DEGRADED = "degraded"
    ERROR = "error"

    def __init__(self, status: str = OK, message: str | None = None) -> None:
        self.status = status
        self.message = message

    @staticmethod
    def ok() -> HealthResult:
        return HealthResult(HealthResult.OK)

    @staticmethod
    def degraded(message: str = "") -> HealthResult:
        return HealthResult(HealthResult.DEGRADED, message)

    @staticmethod
    def error(message: str = "") -> HealthResult:
        return HealthResult(HealthResult.ERROR, message)


class ForgeModule(ABC):
    """
    Base interface for all forge modules.

    Every module in the framework must implement this contract.
    Subclasses must provide a unique ``name`` and may optionally declare
    ``dependencies``, ``setup``, ``teardown``, and ``health_check``.
    """

    _lifecycle_state: ModuleLifecycleState = ModuleLifecycleState.UNREGISTERED

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique module identifier used for DI resolution."""

    @property
    def dependencies(self) -> list[str]:
        """
        Names of modules this module depends on.

        The runtime guarantees that all dependencies are initialised
        before ``setup`` is called on this module.
        """
        return []

    async def setup(self, runtime: Runtime) -> None:
        """
        Called once during runtime initialisation.

        Order is guaranteed to follow a topological sort of the
        dependency graph declared across all registered modules.
        """

    async def teardown(self) -> None:
        """
        Called during graceful shutdown.

        Implementations should release any held resources.
        """

    def health_check(self) -> HealthResult:
        """
        Optional health check registered automatically by the runtime.

        Return ``HealthResult.ok()`` by default.
        """
        return HealthResult.ok()

    # ------------------------------------------------------------------
    # Internal lifecycle helpers (used by the runtime)
    # ------------------------------------------------------------------

    def _transition(self, target: ModuleLifecycleState) -> None:
        _valid: dict[ModuleLifecycleState, set[ModuleLifecycleState]] = {
            ModuleLifecycleState.UNREGISTERED: {ModuleLifecycleState.REGISTERED},
            ModuleLifecycleState.REGISTERED: {ModuleLifecycleState.INITIALIZING},
            ModuleLifecycleState.INITIALIZING: {ModuleLifecycleState.READY},
            ModuleLifecycleState.READY: {ModuleLifecycleState.TEARDOWN},
            ModuleLifecycleState.TEARDOWN: {ModuleLifecycleState.STOPPED},
        }
        allowed = _valid.get(self._lifecycle_state, set())
        if target not in allowed:
            from forge.core.exceptions import ModuleStateError

            raise ModuleStateError(
                f"Cannot transition {self.name} from "
                f"{self._lifecycle_state.value} to {target.value}"
            )
        self._lifecycle_state = target
