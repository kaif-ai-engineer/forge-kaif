"""
CRUD code generator — produces FastAPI route handlers from a Pydantic schema.

The generator analyzes a Pydantic model, extracts field metadata, and renders
Jinja2 templates to produce production-ready CRUD endpoints with pagination,
filtering, sorting, and optional soft-delete support.
"""

from __future__ import annotations

import types
import typing
from importlib import resources
from pathlib import Path
from typing import Any

import jinja2
from pydantic import BaseModel

from forge.crud.exceptions import (
    CrudGenerationError,
    SchemaValidationError,
    TemplateNotFoundError,
)
from forge.crud.models import (
    CrudGeneratorConfig,
    CrudOperation,
    FieldInfo,
    _to_snake,
)

_JINJA_ENV: jinja2.Environment | None = None


def _get_template_env() -> jinja2.Environment:
    """Get or create the Jinja2 template environment for CRUD templates."""
    global _JINJA_ENV  # noqa: PLW0603
    if _JINJA_ENV is None:
        _JINJA_ENV = _build_env()
    return _JINJA_ENV


def _build_env() -> jinja2.Environment:
    """Build and return the Jinja2 template environment."""
    templates = resources.files("forge.crud") / "templates"
    if not templates.is_dir():
        raise TemplateNotFoundError(
            f"CRUD templates directory not found at {templates}"
        )
    loader = jinja2.FileSystemLoader(str(templates))
    try:
        env = jinja2.Environment(
            loader=loader,
            undefined=jinja2.StrictUndefined,
            autoescape=jinja2.select_autoescape(disabled_extensions=("jinja",)),
            trim_blocks=True,
            lstrip_blocks=True,
        )
    except Exception as exc:
        raise CrudGenerationError(
            f"Failed to initialise Jinja2 template environment: {exc}"
        ) from exc
    return env


_PRIMARY_KEY_NAMES = frozenset({"id", "pk", "uid", "uuid", "slug"})
_TIMESTAMP_NAMES = frozenset({"created_at", "updated_at", "created", "updated"})
_SOFT_DELETE_NAMES = frozenset({"deleted_at", "is_deleted", "deleted", "is_active"})


def _infer_primary_key(fields: dict[str, Any]) -> str:
    """Guess the primary key field name from a schema's annotations."""
    if "id" in fields:
        return "id"
    for candidate in _PRIMARY_KEY_NAMES:
        if candidate in fields:
            return candidate
    # Fall back to the first field
    return next(iter(fields.keys()), "id")


def _infer_soft_delete(fields: dict[str, Any]) -> bool:
    """Check if the schema has a soft-delete field."""
    return any(name in fields for name in _SOFT_DELETE_NAMES)


_COLLECTION_HINT_MAP: dict[type, str] = {
    list: "list",
    dict: "dict",
    set: "set",
    tuple: "tuple",
}


def _parse_type_hint(annotation: Any) -> str:
    """Convert a Python type annotation to a string representation."""
    if annotation is type(None):
        return "None"
    origin = getattr(annotation, "__origin__", None)
    if origin is None:
        return getattr(annotation, "__name__", str(annotation))
    args = getattr(annotation, "__args__", ())
    if origin in _COLLECTION_HINT_MAP:
        inner = ", ".join(_parse_type_hint(a) for a in args)
        return f"{_COLLECTION_HINT_MAP[origin]}[{inner}]"
    if origin is typing.Union or origin is types.UnionType:
        return _format_union(args)
    return getattr(annotation, "__name__", str(annotation))


def _format_union(args: tuple[Any, ...]) -> str:
    """Format a Union type annotation as a string."""
    non_none = [a for a in args if a is not type(None)]
    if len(non_none) == 1 and type(None) in args:
        return f"{_parse_type_hint(non_none[0])} | None"
    inner = ", ".join(_parse_type_hint(a) for a in args)
    return f"Union[{inner}]"


def _classify_fields(
    schema: type[BaseModel],
    config: CrudGeneratorConfig,
) -> tuple[
    list[FieldInfo],
    list[FieldInfo],
    list[FieldInfo],
    list[FieldInfo],
    list[FieldInfo],
    str,
    str,
]:
    """Analyze a Pydantic schema and classify its fields for generation."""
    try:
        model_fields = schema.model_fields
    except AttributeError as exc:
        raise SchemaValidationError(
            f"'{schema.__name__}' is not a valid Pydantic v2 model. "
            "Ensure your schema inherits from pydantic.BaseModel."
        ) from exc

    if not model_fields:
        raise SchemaValidationError(
            f"'{schema.__name__}' has no fields defined. "
            "CRUD generation requires at least one field."
        )

    primary_key = (
        config.primary_key
        if config.primary_key and config.primary_key in model_fields
        else _infer_primary_key(model_fields)
    )

    all_infos: list[FieldInfo] = []
    for name, field in model_fields.items():
        type_hint = _parse_type_hint(field.annotation) if field.annotation else "Any"
        default = None
        required = field.is_required()

        if not required and field.default is not None:
            default = repr(field.default)

        all_infos.append(
            FieldInfo(
                name=name,
                type_hint=type_hint,
                default=default,
                required=required,
                is_primary_key=(name == primary_key),
                is_timestamp=(name in _TIMESTAMP_NAMES),
                is_soft_delete=(name in _SOFT_DELETE_NAMES),
            )
        )

    response_fields = [
        f
        for f in all_infos
        if not (f.is_soft_delete and not config.soft_delete)
    ]

    create_fields = [
        f
        for f in all_infos
        if not f.is_primary_key
        and not f.is_timestamp
        and not f.is_soft_delete
    ]

    update_fields = create_fields

    filter_fields_raw = config.filter_fields
    if filter_fields_raw:
        filter_field_set = set(filter_fields_raw)
        configured = [f for f in response_fields if f.name in filter_field_set]
        filter_list = configured
    else:
        filter_list = [
            f
            for f in response_fields
            if not f.is_primary_key
            and f.type_hint
            in {
                "str",
                "int",
                "float",
                "bool",
                "datetime",
                "date",
            }
        ]

    pk_info = next(
        (f for f in all_infos if f.is_primary_key),
        FieldInfo(
            name=primary_key,
            type_hint="int",
            required=True,
            is_primary_key=True,
        ),
    )

    return (
        all_infos,
        response_fields,
        create_fields,
        update_fields,
        filter_list,
        primary_key,
        pk_info.type_hint,
    )


_MAX_AUTH_SPLIT_PARTS = 2


def _split_auth_dependency(auth: str | None) -> tuple[str | None, str | None]:
    """Split an auth dependency path into module and function name."""
    if not auth:
        return None, None
    parts = auth.rsplit(".", 1)
    if len(parts) == _MAX_AUTH_SPLIT_PARTS and parts[1]:
        return (parts[0], parts[1])
    return (None, parts[0])


def build_template_context(
    schema: type[BaseModel],
    config: CrudGeneratorConfig,
) -> dict[str, Any]:
    """Build the template rendering context from a schema and configuration."""
    (
        _all_infos,
        response_fields,
        create_fields,
        update_fields,
        filter_fields,
        primary_key,
        primary_key_type,
    ) = _classify_fields(schema, config)

    auth_module, auth_name = _split_auth_dependency(config.auth_dependency)

    sort_fields_list = config.sort_fields or []

    context: dict[str, Any] = {
        "schema_name": config.schema_name,
        "model_name": config.schema_name,
        "model_name_snake": _to_snake(config.schema_name),
        "model_name_plural": _to_snake(config.schema_name) + "s",
        "table_name": config.resolved_table_name,
        "package_name": config.resolved_package_name,
        "primary_key": primary_key,
        "primary_key_type": primary_key_type,
        "auth_dependency": config.auth_dependency,
        "auth_dependency_module": auth_module,
        "auth_dependency_name": auth_name,
        "create_schema_name": config.resolved_create_schema,
        "update_schema_name": config.resolved_update_schema,
        "response_schema_name": config.resolved_response_model,
        "filter_schema_name": f"{config.schema_name}Filter",
        "generate_create": CrudOperation.CREATE in config.operations,
        "generate_list": CrudOperation.LIST in config.operations,
        "generate_read": CrudOperation.READ in config.operations,
        "generate_update": CrudOperation.UPDATE in config.operations,
        "generate_delete": CrudOperation.DELETE in config.operations,
        "pagination": config.pagination,
        "soft_delete": config.soft_delete,
        "response_fields": [f.model_dump() for f in response_fields],
        "response_field_decls": [f.declaration(for_create=False) for f in response_fields],
        "create_fields": [f.model_dump() for f in create_fields],
        "create_field_decls": [f.declaration(for_create=True) for f in create_fields],
        "update_fields": [f.model_dump() for f in update_fields],
        "update_field_decls": [f.declaration(for_create=True) for f in update_fields],
        "filter_fields": [f.model_dump() for f in filter_fields],
        "sort_fields": sort_fields_list,
    }

    return context


class CrudGenerator:
    """
    Template-based CRUD code generator.

    Analyzes a Pydantic schema and generates FastAPI route handler files
    with configurable operations, pagination, filtering, sorting,
    and soft-delete support.

    Usage:
        generator = CrudGenerator(User, output_dir="app/crud/generated")
        generator.generate()
    """

    def __init__(
        self,
        schema: type[BaseModel],
        output_dir: str = ".",
        operations: set[CrudOperation] | None = None,
        auth_dependency: str | None = None,
        response_model: str | None = None,
        create_schema: str | None = None,
        update_schema: str | None = None,
        pagination: bool = True,
        filter_fields: list[str] | None = None,
        sort_fields: list[str] | None = None,
        soft_delete: bool = False,
        primary_key: str | None = None,
        table_name: str | None = None,
        config: CrudGeneratorConfig | None = None,
    ) -> None:
        if config is not None:
            self._config = config
        else:
            self._config = CrudGeneratorConfig(
                schema_name=schema.__name__,
                operations=operations if operations is not None else {
                    CrudOperation.CREATE,
                    CrudOperation.LIST,
                    CrudOperation.READ,
                    CrudOperation.UPDATE,
                    CrudOperation.DELETE,
                },
                auth_dependency=auth_dependency,
                response_model=response_model,
                create_schema=create_schema,
                update_schema=update_schema,
                output_dir=output_dir,
                pagination=pagination,
                filter_fields=filter_fields,
                sort_fields=sort_fields,
                soft_delete=soft_delete,
                primary_key=primary_key or "id",
                table_name=table_name,
            )
        self._schema = schema
        self._validate()

    def _validate(self) -> None:
        """Validate that the schema and configuration are usable."""
        if not self._config.operations:
            raise CrudGenerationError(
                "At least one CRUD operation must be specified in 'operations'."
            )

    @property
    def config(self) -> CrudGeneratorConfig:
        """Return the current generator configuration."""
        return self._config

    def build_context(self) -> dict[str, Any]:
        """Build the Jinja2 template context from the schema and config."""
        return build_template_context(self._schema, self._config)

    def render(self, template_name: str = "crud_router.py.jinja") -> str:
        """
        Render the CRUD template into generated source code.

        Args:
            template_name: Name of the Jinja2 template file to render.

        Returns:
            The rendered source code as a string.
        """
        env = _get_template_env()
        try:
            template = env.get_template(template_name)
        except jinja2.TemplateNotFound as exc:
            raise TemplateNotFoundError(
                f"Template '{template_name}' not found. "
                f"Available templates: {', '.join(_list_templates())}"
            ) from exc

        context = self.build_context()
        return template.render(**context)

    def generate(
        self,
        template_name: str = "crud_router.py.jinja",
        output_filename: str | None = None,
        force: bool = False,
    ) -> Path:
        """
        Generate the CRUD router file and write it to disk.

        Args:
            template_name: The template file to render.
            output_filename: Optional custom output filename.
                Defaults to '{table_name}.py'.
            force: Overwrite existing file if True.

        Returns:
            The path to the generated file.

        Raises:
            CrudGenerationError: If the output file already exists
                and force is False.
        """
        rendered = self.render(template_name)
        output_path = self._resolve_output_path(output_filename)

        if output_path.exists() and not force:
            raise CrudGenerationError(
                f"Output file already exists: {output_path}\n\n"
                f"Use force=True to overwrite, or specify a different output filename."
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
        return output_path

    def _resolve_output_path(self, output_filename: str | None = None) -> Path:
        """Resolve the output file path from config and optional filename."""
        base = Path(self._config.output_dir)
        name = output_filename or f"{self._config.resolved_table_name}.py"
        return base / name


def _list_templates() -> list[str]:
    """List available CRUD template files."""
    try:
        templates = resources.files("forge.crud") / "templates"
        return sorted(
            t.name for t in templates.iterdir() if t.is_file() and t.name.endswith(".jinja")
        )
    except Exception:
        return []


def generate_crud(
    schema: type,
    output_dir: str = ".",
    operations: set[CrudOperation] | None = None,
    auth_dependency: str | None = None,
    response_model: str | None = None,
    create_schema: str | None = None,
    update_schema: str | None = None,
    pagination: bool = True,
    filter_fields: list[str] | None = None,
    sort_fields: list[str] | None = None,
    soft_delete: bool = False,
    primary_key: str | None = None,
    table_name: str | None = None,
    force: bool = False,
) -> Path:
    """
    Convenience function to generate CRUD routes in one call.

    Args:
        schema: A Pydantic model class to generate CRUD routes for.
        output_dir: Directory to write the generated file to.
        operations: Set of CRUD operations to generate.
        auth_dependency: Fully qualified auth dependency (e.g. 'app.auth.get_current_user').
        response_model: Custom response model class name.
        create_schema: Custom create schema class name.
        update_schema: Custom update schema class name.
        pagination: Enable pagination for list endpoint.
        filter_fields: List of field names to enable filtering on.
        sort_fields: List of field names to enable sorting on.
        soft_delete: Enable soft-delete support.
        primary_key: Primary key field name.
        table_name: Database table name (used for URL prefix).
        force: Overwrite existing output file.

    Returns:
        The path to the generated file.

    Example:
        >>> from pydantic import BaseModel
        >>> from forge.crud import generate_crud
        >>>
        >>> class User(BaseModel):
        ...     id: int
        ...     name: str
        ...     email: str
        ...
        >>> path = generate_crud(
        ...     User,
        ...     output_dir="app/crud/generated",
        ...     auth_dependency="app.auth.get_current_user",
        ...     soft_delete=True,
        ... )
    """
    generator = CrudGenerator(
        schema=schema,
        output_dir=output_dir,
        operations=operations,
        auth_dependency=auth_dependency,
        response_model=response_model,
        create_schema=create_schema,
        update_schema=update_schema,
        pagination=pagination,
        filter_fields=filter_fields,
        sort_fields=sort_fields,
        soft_delete=soft_delete,
        primary_key=primary_key,
        table_name=table_name,
    )
    return generator.generate(force=force)
