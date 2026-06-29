"""
forge.crud — Template-based CRUD code generation for FastAPI.

Generates Create/Read/Update/Delete route handlers from a Pydantic schema
with pagination, filtering, sorting, and optional soft-delete support.
"""

from __future__ import annotations

from forge.crud.exceptions import (
    CrudError,
    CrudGenerationError,
    SchemaValidationError,
    TemplateNotFoundError,
)
from forge.crud.generator import CrudGenerator, generate_crud
from forge.crud.models import CrudGeneratorConfig, CrudOperation, FieldInfo
from forge.crud.module import CrudModule

__all__ = [
    "CrudError",
    "CrudGenerationError",
    "CrudGenerator",
    "CrudGeneratorConfig",
    "CrudModule",
    "CrudOperation",
    "FieldInfo",
    "SchemaValidationError",
    "TemplateNotFoundError",
    "generate_crud",
]
