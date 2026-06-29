from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, Field


class CrudOperation(StrEnum):
    """Supported CRUD operations for code generation."""

    CREATE = "create"
    LIST = "list"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"


class FieldInfo(BaseModel):
    """Describes a single field from a Pydantic schema for template context."""

    name: str
    type_hint: str
    default: str | None = None
    required: bool = True
    is_primary_key: bool = False
    is_timestamp: bool = False
    is_soft_delete: bool = False

    def declaration(self, for_create: bool = True) -> str:
        """Return the Python field declaration line."""
        if (self.is_primary_key or self.is_timestamp or self.is_soft_delete) and for_create:
            return ""
        if self.required:
            return f"{self.name}: {self.type_hint}"
        if self.default is not None:
            return f"{self.name}: {self.type_hint} = {self.default}"
        if " | None" in self.type_hint or " | " in self.type_hint:
            return f"{self.name}: {self.type_hint} = None"
        return f"{self.name}: {self.type_hint} | None = None"


class SortField(BaseModel):
    """Configuration for a sortable field."""

    name: str
    label: str = ""


class FilterField(BaseModel):
    """Configuration for a filterable field."""

    name: str
    type_hint: str = "str"
    operator: str = "eq"
    label: str = ""


class CrudGeneratorConfig(BaseModel):
    """
    Configuration for the CRUD generator.

    Controls which operations are generated, how the output is structured,
    and what features (pagination, filtering, sorting, soft delete) are included.
    """

    schema_name: str
    operations: set[CrudOperation] = Field(
        default_factory=lambda: {
            CrudOperation.CREATE,
            CrudOperation.LIST,
            CrudOperation.READ,
            CrudOperation.UPDATE,
            CrudOperation.DELETE,
        },
    )
    auth_dependency: str | None = None
    response_model: str | None = None
    create_schema: str | None = None
    update_schema: str | None = None
    output_dir: str = "."
    pagination: bool = True
    filter_fields: list[str] | None = None
    sort_fields: list[str] | None = None
    soft_delete: bool = False
    primary_key: str = "id"
    table_name: str | None = None
    package_name: str | None = None

    @property
    def resolved_table_name(self) -> str:
        """Return the table name, derived from schema_name if not set."""
        if self.table_name:
            return self.table_name
        return _to_snake(self.schema_name) + "s"

    @property
    def resolved_package_name(self) -> str:
        """Return the package name, derived from output_dir if not set."""
        if self.package_name:
            return self.package_name
        return self.output_dir.replace("/", ".").replace("\\", ".").strip(".")

    @property
    def resolved_create_schema(self) -> str:
        """Return the create schema class name."""
        return self.create_schema or f"{self.schema_name}Create"

    @property
    def resolved_update_schema(self) -> str:
        """Return the update schema class name."""
        return self.update_schema or f"{self.schema_name}Update"

    @property
    def resolved_response_model(self) -> str:
        """Return the response model class name."""
        return self.response_model or f"{self.schema_name}Response"


def _to_snake(name: str) -> str:
    """Convert PascalCase or camelCase to snake_case."""
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()
