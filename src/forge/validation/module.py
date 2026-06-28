from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from forge.core.module import ForgeModule, HealthResult

if TYPE_CHECKING:
    from forge.core.runtime import ForgeRuntime as Runtime


class ValidationModule(ForgeModule):
    """
    Lightweight module providing Pydantic integration and consistent validation helpers.
    """

    name = "validation"
    dependencies: ClassVar[list[str]] = []

    async def setup(self, runtime: Runtime) -> None:
        """Set up the validation module."""

    async def teardown(self) -> None:
        """Teardown the validation module."""

    def health_check(self) -> HealthResult:
        """Return the health check status of the validation module."""
        return HealthResult.ok()
