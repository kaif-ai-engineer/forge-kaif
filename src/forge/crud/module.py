from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from forge.core.module import ForgeModule, HealthResult

if TYPE_CHECKING:
    from forge.core.runtime import ForgeRuntime as Runtime


class CrudModule(ForgeModule):
    """
    Forge module providing CRUD code generation capabilities.

    The CrudModule integrates the CRUD generator into the forge runtime.
    It is a lightweight module that makes the ``CrudGenerator`` and
    ``generate_crud`` convenience function available through the runtime,
    enabling programmatic code generation during development workflows.
    """

    name = "crud"
    dependencies: ClassVar[list[str]] = []

    async def setup(self, runtime: Runtime) -> None:
        """Initialise the CRUD module."""

    async def teardown(self) -> None:
        """Teardown the CRUD module."""

    def health_check(self) -> HealthResult:
        """Return health status of the CRUD module."""
        return HealthResult.ok()
