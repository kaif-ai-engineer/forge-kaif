from __future__ import annotations

from forge.core.exceptions import ForgeError


class CrudError(ForgeError):
    """Base exception for all CRUD generation errors."""


class CrudGenerationError(CrudError):
    """Raised when CRUD code generation fails."""


class SchemaValidationError(CrudError):
    """Raised when the provided Pydantic schema is invalid for CRUD generation."""


class TemplateNotFoundError(CrudError):
    """Raised when a required template file is not found."""
