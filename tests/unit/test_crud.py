from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from pydantic import BaseModel

from forge.crud import (
    CrudGenerationError,
    CrudGenerator,
    CrudGeneratorConfig,
    CrudModule,
    CrudOperation,
    FieldInfo,
    SchemaValidationError,
    TemplateNotFoundError,
    generate_crud,
)
from forge.crud.generator import _classify_fields, _infer_primary_key, _parse_type_hint, _to_snake
from forge.crud.models import _to_snake as models_to_snake

# ── Test Schemas ──────────────────────────────────────────────────────────


class User(BaseModel):
    id: int
    name: str
    email: str
    age: int = 18
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


class Product(BaseModel):
    sku: str
    name: str
    price: float
    category: str
    deleted_at: datetime | None = None


class EmptySchema(BaseModel):
    pass


class MinimalSchema(BaseModel):
    value: str


# ── Tests: _to_snake ──────────────────────────────────────────────────────


class TestToSnake:
    def test_pascal_case(self) -> None:
        assert _to_snake("UserProfile") == "user_profile"

    def test_camel_case(self) -> None:
        assert _to_snake("userProfile") == "user_profile"

    def test_single_word(self) -> None:
        assert _to_snake("User") == "user"

    def test_already_snake(self) -> None:
        assert _to_snake("user_profile") == "user_profile"

    def test_model_to_snake_consistency(self) -> None:
        assert models_to_snake is _to_snake or models_to_snake("User") == _to_snake("User")


# ── Tests: _parse_type_hint ────────────────────────────────────────────────


class TestParseTypeHint:
    def test_simple_type(self) -> None:
        assert _parse_type_hint(int) == "int"
        assert _parse_type_hint(str) == "str"
        assert _parse_type_hint(float) == "float"
        assert _parse_type_hint(bool) == "bool"

    def test_none_type(self) -> None:
        assert _parse_type_hint(type(None)) == "None"

    def test_optional_type(self) -> None:
        assert _parse_type_hint(str | None) == "str | None"

    def test_list_type(self) -> None:
        assert _parse_type_hint(list[str]) == "list[str]"

    def test_dict_type(self) -> None:
        assert _parse_type_hint(dict[str, int]) == "dict[str, int]"

    def test_custom_class(self) -> None:
        class Custom:
            pass

        assert _parse_type_hint(Custom) == "Custom"


# ── Tests: _infer_primary_key ──────────────────────────────────────────────


class TestInferPrimaryKey:
    def test_default_id_field(self) -> None:
        fields = {"id": int, "name": str}
        assert _infer_primary_key(fields) == "id"

    def test_uuid_field(self) -> None:
        fields = {"uuid": str, "name": str}
        assert _infer_primary_key(fields) == "uuid"

    def test_slug_field(self) -> None:
        fields = {"slug": str, "title": str}
        assert _infer_primary_key(fields) == "slug"

    def test_fallback_to_first(self) -> None:
        fields = {"code": str, "label": str}
        assert _infer_primary_key(fields) == "code"

    def test_empty_fields(self) -> None:
        assert _infer_primary_key({}) == "id"


# ── Tests: CrudGeneratorConfig ─────────────────────────────────────────────


class TestCrudGeneratorConfig:
    def test_default_operations(self) -> None:
        config = CrudGeneratorConfig(schema_name="User", output_dir="./output")
        assert CrudOperation.CREATE in config.operations
        assert CrudOperation.LIST in config.operations
        assert CrudOperation.READ in config.operations
        assert CrudOperation.UPDATE in config.operations
        assert CrudOperation.DELETE in config.operations

    def test_resolved_table_name_default(self) -> None:
        config = CrudGeneratorConfig(schema_name="User", output_dir="./output")
        assert config.resolved_table_name == "users"

    def test_resolved_table_name_custom(self) -> None:
        config = CrudGeneratorConfig(
            schema_name="User",
            output_dir="./output",
            table_name="custom_users",
        )
        assert config.resolved_table_name == "custom_users"

    def test_resolved_create_schema_default(self) -> None:
        config = CrudGeneratorConfig(schema_name="User", output_dir="./output")
        assert config.resolved_create_schema == "UserCreate"

    def test_resolved_create_schema_custom(self) -> None:
        config = CrudGeneratorConfig(
            schema_name="User",
            output_dir="./output",
            create_schema="CustomCreate",
        )
        assert config.resolved_create_schema == "CustomCreate"

    def test_resolved_update_schema_default(self) -> None:
        config = CrudGeneratorConfig(schema_name="User", output_dir="./output")
        assert config.resolved_update_schema == "UserUpdate"

    def test_resolved_response_model_default(self) -> None:
        config = CrudGeneratorConfig(schema_name="User", output_dir="./output")
        assert config.resolved_response_model == "UserResponse"

    def test_resolved_package_name_from_dir(self) -> None:
        config = CrudGeneratorConfig(
            schema_name="User",
            output_dir="app/crud/generated",
        )
        assert config.resolved_package_name == "app.crud.generated"


# ── Tests: _classify_fields ────────────────────────────────────────────────


class TestClassifyFields:
    def test_classify_user_schema(self) -> None:
        config = CrudGeneratorConfig(schema_name="User", output_dir=".")
        result = _classify_fields(User, config)
        (
            all_infos,
            response_fields,
            create_fields,
            _update_fields,
            _filter_fields,
            primary_key,
            pk_type,
        ) = result

        assert primary_key == "id"
        assert pk_type == "int"
        assert len(all_infos) == 7
        assert any(f.name == "id" and f.is_primary_key for f in all_infos)
        assert any(f.name == "created_at" and f.is_timestamp for f in all_infos)
        assert any(f.name == "updated_at" and f.is_timestamp for f in all_infos)

        # Create fields should exclude primary key and timestamps
        create_names = {f.name for f in create_fields}
        assert "id" not in create_names
        assert "created_at" not in create_names
        assert "updated_at" not in create_names
        assert "name" in create_names
        assert "email" in create_names

        # Response fields should include everything
        response_names = {f.name for f in response_fields}
        assert "id" in response_names
        assert "name" in response_names
        assert "email" in response_names

    def test_classify_with_soft_delete(self) -> None:
        config = CrudGeneratorConfig(
            schema_name="Product",
            output_dir=".",
            soft_delete=True,
        )
        result = _classify_fields(Product, config)
        (_all, _resp, _create, _update, _filter, pk, pk_type) = result

        assert pk == "sku"
        assert pk_type == "str"

        # With soft_deleted enabled, deleted_at is excluded from create fields
        create_names = {f.name for f in _create}
        assert "deleted_at" not in create_names

    def test_classify_empty_schema_raises(self) -> None:
        config = CrudGeneratorConfig(schema_name="EmptySchema", output_dir=".")
        with pytest.raises(SchemaValidationError):
            _classify_fields(EmptySchema, config)

    def test_classify_not_a_pydantic_model(self) -> None:
        config = CrudGeneratorConfig(schema_name="NotAModel", output_dir=".")

        class NotAModel:
            pass

        with pytest.raises(SchemaValidationError):
            _classify_fields(NotAModel, config)

    def test_custom_filter_fields(self) -> None:
        config = CrudGeneratorConfig(
            schema_name="User",
            output_dir=".",
            filter_fields=["name", "email"],
        )
        result = _classify_fields(User, config)
        filter_names = {f.name for f in result[4]}
        assert filter_names == {"name", "email"}

    def test_required_and_default_fields(self) -> None:
        config = CrudGeneratorConfig(schema_name="User", output_dir=".")
        result = _classify_fields(User, config)
        all_infos = result[0]
        id_info = next(f for f in all_infos if f.name == "id")
        age_info = next(f for f in all_infos if f.name == "age")
        assert id_info.required is True
        assert age_info.required is False
        assert age_info.default == "18"


# ── Tests: CrudGenerator ──────────────────────────────────────────────────


class TestCrudGeneratorInit:
    def test_minimal_init(self) -> None:
        generator = CrudGenerator(User, output_dir="output")
        assert generator.config.schema_name == "User"
        assert generator.config.output_dir == "output"

    def test_init_with_full_config(self) -> None:
        config = CrudGeneratorConfig(
            schema_name="User",
            output_dir="output",
            operations={CrudOperation.CREATE, CrudOperation.READ},
            auth_dependency="app.auth.get_current_user",
            pagination=True,
            soft_delete=True,
        )
        generator = CrudGenerator(User, config=config)
        assert generator.config == config

    def test_init_with_no_operations_raises(self) -> None:
        with pytest.raises(CrudGenerationError):
            CrudGenerator(
                User,
                output_dir="output",
                operations=set(),
            )

    def test_init_with_keyword_args(self) -> None:
        generator = CrudGenerator(
            User,
            output_dir="output",
            operations={CrudOperation.LIST},
            auth_dependency="myapp.auth.require_user",
            pagination=False,
            soft_delete=True,
            primary_key="uuid",
            table_name="users_custom",
        )
        assert generator.config.auth_dependency == "myapp.auth.require_user"
        assert generator.config.pagination is False
        assert generator.config.soft_delete is True
        assert generator.config.primary_key == "uuid"
        assert generator.config.table_name == "users_custom"


class TestCrudGeneratorBuildContext:
    def test_context_contains_expected_keys(self) -> None:
        generator = CrudGenerator(User, output_dir="output")
        context = generator.build_context()

        assert context["schema_name"] == "User"
        assert context["model_name"] == "User"
        assert context["model_name_snake"] == "user"
        assert context["model_name_plural"] == "users"
        assert context["primary_key"] == "id"
        assert context["primary_key_type"] == "int"
        assert context["generate_create"] is True
        assert context["generate_list"] is True
        assert context["generate_read"] is True
        assert context["generate_update"] is True
        assert context["generate_delete"] is True
        assert context["pagination"] is True
        assert context["soft_delete"] is False
        assert context["auth_dependency"] is None

    def test_context_with_auth_dependency(self) -> None:
        generator = CrudGenerator(
            User,
            output_dir="output",
            auth_dependency="app.auth.get_current_user",
        )
        context = generator.build_context()
        assert context["auth_dependency"] == "app.auth.get_current_user"
        assert context["auth_dependency_module"] == "app.auth"
        assert context["auth_dependency_name"] == "get_current_user"

    def test_context_without_auth_module(self) -> None:
        generator = CrudGenerator(
            User,
            output_dir="output",
            auth_dependency="get_current_user",
        )
        context = generator.build_context()
        assert context["auth_dependency_module"] is None
        assert context["auth_dependency_name"] == "get_current_user"

    def test_context_operations_filtered(self) -> None:
        generator = CrudGenerator(
            User,
            output_dir="output",
            operations={CrudOperation.CREATE, CrudOperation.LIST},
        )
        context = generator.build_context()
        assert context["generate_create"] is True
        assert context["generate_list"] is True
        assert context["generate_read"] is False
        assert context["generate_update"] is False
        assert context["generate_delete"] is False

    def test_context_field_data(self) -> None:
        generator = CrudGenerator(User, output_dir="output")
        context = generator.build_context()
        response_fields = context["response_fields"]
        assert len(response_fields) >= 5


class TestCrudGeneratorRender:
    def test_render_creates_valid_python(self) -> None:
        generator = CrudGenerator(User, output_dir="output")
        rendered = generator.render()
        assert isinstance(rendered, str)
        assert len(rendered) > 0
        # Should be valid Python syntax
        compile(rendered, "<test>", "exec")

    def test_render_contains_endpoints(self) -> None:
        generator = CrudGenerator(User, output_dir="output")
        rendered = generator.render()
        assert "async def create_user(" in rendered
        assert "async def list_users(" in rendered
        assert "async def get_user(" in rendered
        assert "async def update_user(" in rendered
        assert "async def delete_user(" in rendered

    def test_render_partial_operations(self) -> None:
        generator = CrudGenerator(
            User,
            output_dir="output",
            operations={CrudOperation.CREATE, CrudOperation.READ},
        )
        rendered = generator.render()
        assert "async def create_user(" in rendered
        assert "async def get_user(" in rendered
        assert "async def list_users(" not in rendered
        assert "async def update_user(" not in rendered

    def test_render_with_auth_dependency(self) -> None:
        generator = CrudGenerator(
            User,
            output_dir="output",
            auth_dependency="app.auth.get_current_user",
        )
        rendered = generator.render()
        assert "Depends(get_current_user)" in rendered
        assert "from app.auth import get_current_user" in rendered

    def test_render_without_auth_dependency(self) -> None:
        generator = CrudGenerator(User, output_dir="output")
        rendered = generator.render()
        assert "Depends(" not in rendered

    def test_render_with_soft_delete(self) -> None:
        generator = CrudGenerator(
            User,
            output_dir="output",
            soft_delete=True,
        )
        rendered = generator.render()
        assert "soft_delete_user(" in rendered

    def test_render_without_pagination(self) -> None:
        generator = CrudGenerator(
            User,
            output_dir="output",
            pagination=False,
        )
        rendered = generator.render()
        assert "PaginatedUserResponse" not in rendered
        assert "list[UserResponse]" in rendered

    def test_render_with_pagination(self) -> None:
        generator = CrudGenerator(
            User,
            output_dir="output",
            pagination=True,
        )
        rendered = generator.render()
        assert "PaginatedUserResponse" in rendered
        assert "page: int" in rendered
        assert "page_size: int" in rendered

    def test_render_custom_schema_names(self) -> None:
        generator = CrudGenerator(
            User,
            output_dir="output",
            create_schema="UserCreateRequest",
            update_schema="UserUpdateRequest",
            response_model="UserOut",
        )
        rendered = generator.render()
        assert "class UserCreateRequest(BaseModel):" in rendered
        assert "class UserUpdateRequest(BaseModel):" in rendered
        assert "class UserOut(BaseModel):" in rendered
        assert "class PaginatedUserOut(BaseModel):" in rendered

    def test_render_template_not_found(self) -> None:
        generator = CrudGenerator(User, output_dir="output")
        with pytest.raises(TemplateNotFoundError):
            generator.render(template_name="nonexistent.jinja")

    def test_render_with_custom_table_name(self) -> None:
        generator = CrudGenerator(
            User,
            output_dir="output",
            table_name="accounts",
        )
        rendered = generator.render()
        assert 'prefix="/accounts"' in rendered


class TestCrudGeneratorGenerate:
    def test_generate_writes_file(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "crud_output"
        generator = CrudGenerator(User, output_dir=str(output_dir))
        output_path = generator.generate()

        assert output_path.exists()
        assert output_path.name == "users.py"
        content = output_path.read_text(encoding="utf-8")
        assert "async def create_user(" in content

    def test_generate_custom_filename(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "crud_output"
        generator = CrudGenerator(User, output_dir=str(output_dir))
        output_path = generator.generate(output_filename="my_users.py")

        assert output_path.exists()
        assert output_path.name == "my_users.py"

    def test_generate_existing_file_no_force(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "crud_output"
        output_dir.mkdir()
        existing = output_dir / "users.py"
        existing.write_text("original", encoding="utf-8")

        generator = CrudGenerator(User, output_dir=str(output_dir))
        with pytest.raises(CrudGenerationError):
            generator.generate()

    def test_generate_existing_file_with_force(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "crud_output"
        output_dir.mkdir()
        existing = output_dir / "users.py"
        existing.write_text("original", encoding="utf-8")

        generator = CrudGenerator(User, output_dir=str(output_dir))
        output_path = generator.generate(force=True)

        content = output_path.read_text(encoding="utf-8")
        assert "original" not in content
        assert "async def create_user(" in content


# ── Tests: generate_crud convenience function ─────────────────────────────


class TestGenerateCrudFunction:
    def test_generate_crud_basic(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "crud_gen"
        result = generate_crud(User, output_dir=str(output_dir))
        assert result.exists()
        assert result.name == "users.py"

    def test_generate_crud_with_options(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "crud_gen"
        result = generate_crud(
            Product,
            output_dir=str(output_dir),
            operations={CrudOperation.CREATE, CrudOperation.LIST},
            auth_dependency="auth.get_user",
            soft_delete=True,
            force=True,
        )
        content = result.read_text(encoding="utf-8")
        assert "async def create_product(" in content
        assert "async def list_products(" in content
        assert "async def get_product(" not in content
        assert "from auth import get_user" in content


# ── Tests: CrudOperation enum ──────────────────────────────────────────────


class TestCrudOperation:
    def test_enum_values(self) -> None:
        assert CrudOperation.CREATE.value == "create"
        assert CrudOperation.LIST.value == "list"
        assert CrudOperation.READ.value == "read"
        assert CrudOperation.UPDATE.value == "update"
        assert CrudOperation.DELETE.value == "delete"

    def test_enum_membership(self) -> None:
        ops = {CrudOperation.CREATE, CrudOperation.READ}
        assert CrudOperation.CREATE in ops
        assert CrudOperation.READ in ops
        assert CrudOperation.UPDATE not in ops


# ── Tests: FieldInfo model ──────────────────────────────────────────────────


class TestFieldInfo:
    def test_field_info_defaults(self) -> None:
        field = FieldInfo(name="test_field", type_hint="str")
        assert field.default is None
        assert field.required is True
        assert field.is_primary_key is False
        assert field.is_timestamp is False
        assert field.is_soft_delete is False

    def test_field_info_full(self) -> None:
        field = FieldInfo(
            name="id",
            type_hint="int",
            default=None,
            required=True,
            is_primary_key=True,
        )
        assert field.is_primary_key is True


# ── Tests: CrudModule ──────────────────────────────────────────────────────


class TestCrudModule:
    def test_module_name(self) -> None:
        module = CrudModule()
        assert module.name == "crud"

    def test_module_dependencies(self) -> None:
        module = CrudModule()
        assert module.dependencies == []

    def test_health_check_ok(self) -> None:
        module = CrudModule()
        health = module.health_check()
        assert health.status == "ok"

    @pytest.mark.asyncio
    async def test_setup_and_teardown(self) -> None:
        module = CrudModule()
        # setup and teardown should not raise
        await module.setup(None)  # type: ignore[arg-type]
        await module.teardown()


# ── Tests: Integration ─────────────────────────────────────────────────────


class TestFieldInfoModel:
    def test_field_info_serialization(self) -> None:
        field = FieldInfo(
            name="email",
            type_hint="str",
            required=True,
        )
        data = field.model_dump()
        assert data["name"] == "email"
        assert data["type_hint"] == "str"
        assert data["required"] is True


class TestSchemaNamesInGeneratedCode:
    @pytest.mark.parametrize(
        ("schema", "expected_create", "expected_update", "expected_response"),
        [
            (User, "UserCreate", "UserUpdate", "UserResponse"),
            (MinimalSchema, "MinimalSchemaCreate", "MinimalSchemaUpdate", "MinimalSchemaResponse"),
        ],
    )
    def test_default_schema_names(
        self,
        schema: type[BaseModel],
        expected_create: str,
        expected_update: str,
        expected_response: str,
        tmp_path: Path,
    ) -> None:
        output_dir = tmp_path / "names_test"
        result = generate_crud(schema, output_dir=str(output_dir), force=True)
        content = result.read_text(encoding="utf-8")
        assert f"class {expected_create}(BaseModel):" in content
        assert f"class {expected_update}(BaseModel):" in content
        assert f"class {expected_response}(BaseModel):" in content

    def test_custom_schema_names_in_output(
        self,
        tmp_path: Path,
    ) -> None:
        output_dir = tmp_path / "custom_names"
        result = generate_crud(
            User,
            output_dir=str(output_dir),
            create_schema="CreateUser",
            update_schema="UpdateUser",
            response_model="UserDTO",
            force=True,
        )
        content = result.read_text(encoding="utf-8")
        assert "class CreateUser(BaseModel):" in content
        assert "class UpdateUser(BaseModel):" in content
        assert "class UserDTO(BaseModel):" in content
        assert "class PaginatedUserDTO(BaseModel):" in content


class TestGeneratedCodeQuality:
    def test_generated_code_is_parseable_python(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "quality"
        generator = CrudGenerator(User, output_dir=str(output_dir))
        rendered = generator.render()
        # Should compile without syntax errors
        compile(rendered, "generated_users.py", "exec")

    def test_generated_code_structure(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "structure"
        result = generate_crud(
            User,
            output_dir=str(output_dir),
            auth_dependency="app.auth.current_user",
            soft_delete=True,
            force=True,
        )
        content = result.read_text(encoding="utf-8")

        # Should start with a module docstring
        assert content.startswith('"""')

        # Has the auto-generated warning
        assert "Auto-generated" in content

        # Contains all import sections
        assert "from __future__ import annotations" in content
        assert "from fastapi import" in content
        assert "from pydantic import" in content

        # Auth import section
        assert "from app.auth import current_user" in content

        # Has the APIRouter definition
        assert "router = APIRouter(" in content

        # All endpoints raise 501 (not implemented)
        assert "status.HTTP_501_NOT_IMPLEMENTED" in content

    def test_all_endpoints_return_proper_status_codes(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "status_codes"
        result = generate_crud(
            User,
            output_dir=str(output_dir),
            force=True,
        )
        content = result.read_text(encoding="utf-8")

        # POST returns 201
        assert "status_code=status.HTTP_201_CREATED" in content

        # DELETE returns 204
        assert "status_code=status.HTTP_204_NO_CONTENT" in content

        # GET and PUT don't explicitly set status (defaults to 200)
        # Should have response_model on all read/update endpoints
        assert "response_model=UserResponse" in content
