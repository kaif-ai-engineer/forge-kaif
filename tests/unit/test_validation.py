from __future__ import annotations

import pytest
from fastapi import HTTPException
from pydantic import BaseModel, EmailStr, Field, ValidationError

from forge.core.runtime import ForgeRuntime
from forge.validation import (
    ValidationErrorResponse,
    ValidationModule,
    format_validation_error,
    validate,
)


class UserRequest(BaseModel):
    name: str = Field(min_length=2)
    email: EmailStr
    age: int = Field(gt=0)


def test_format_validation_error() -> None:
    """Test converting a ValidationError to ValidationErrorResponse."""
    try:
        UserRequest(name="a", email="invalid-email", age=-5)
    except ValidationError as exc:
        res = format_validation_error(exc)
        assert isinstance(res, ValidationErrorResponse)
        assert len(res.detail) == 3

        # Match locations
        details_map = {d.loc[1]: d for d in res.detail}
        assert "name" in details_map
        assert "email" in details_map
        assert "age" in details_map

        # Verify body prefix is prepended
        for detail in res.detail:
            assert detail.loc[0] == "body"
            assert detail.msg != ""
            assert detail.type != ""


def test_validate_decorator_sync_valid() -> None:
    """Test @validate decorator with valid sync inputs."""

    @validate(UserRequest)
    def handle_user(data: UserRequest) -> str:
        assert isinstance(data, UserRequest)
        return f"Hello, {data.name}"

    valid_dict = {"name": "Alice", "email": "alice@example.com", "age": 25}
    res = handle_user(valid_dict)
    assert res == "Hello, Alice"


@pytest.mark.asyncio
async def test_validate_decorator_async_valid() -> None:
    """Test @validate decorator with valid async inputs."""

    @validate(UserRequest)
    async def handle_user_async(data: UserRequest) -> str:
        assert isinstance(data, UserRequest)
        return f"Hello, {data.name}"

    valid_dict = {"name": "Bob", "email": "bob@example.com", "age": 30}
    res = await handle_user_async(valid_dict)
    assert res == "Hello, Bob"


def test_validate_decorator_sync_invalid() -> None:
    """Test @validate decorator with invalid sync inputs raising HTTPException 422."""

    @validate(UserRequest)
    def handle_user(data: UserRequest) -> str:
        return "ok"

    invalid_dict = {"name": "A", "email": "not-an-email", "age": -1}

    with pytest.raises(HTTPException) as exc_info:
        handle_user(invalid_dict)

    assert exc_info.value.status_code == 422
    details = exc_info.value.detail
    assert isinstance(details, list)
    assert len(details) == 3
    assert details[0]["loc"][0] == "body"


@pytest.mark.asyncio
async def test_validate_decorator_async_invalid() -> None:
    """Test @validate decorator with invalid async inputs raising HTTPException 422."""

    @validate(UserRequest)
    async def handle_user_async(data: UserRequest) -> str:
        return "ok"

    invalid_dict = {"name": "A", "email": "not-an-email", "age": -1}

    with pytest.raises(HTTPException) as exc_info:
        await handle_user_async(invalid_dict)

    assert exc_info.value.status_code == 422
    details = exc_info.value.detail
    assert isinstance(details, list)
    assert len(details) == 3


def test_validate_decorator_keyword_arg() -> None:
    """Test @validate decorator when argument is passed as keyword argument."""

    @validate(UserRequest)
    def handle_user(data: UserRequest) -> str:
        assert isinstance(data, UserRequest)
        return data.name

    valid_dict = {"name": "Charlie", "email": "charlie@example.com", "age": 40}
    res = handle_user(data=valid_dict)
    assert res == "Charlie"


def test_validate_decorator_method() -> None:
    """Test @validate decorator on instance methods (self offset)."""

    class UserService:
        @validate(UserRequest)
        def create(self, data: UserRequest) -> str:
            assert isinstance(data, UserRequest)
            return data.name

        @validate(UserRequest)
        def create_kw(self, data: UserRequest) -> str:
            assert isinstance(data, UserRequest)
            return data.name

    service = UserService()
    valid_dict = {"name": "Dave", "email": "dave@example.com", "age": 35}

    # Positional method call
    res_pos = service.create(valid_dict)
    assert res_pos == "Dave"

    # Keyword method call
    res_kw = service.create_kw(data=valid_dict)
    assert res_kw == "Dave"


def test_validate_decorator_pass_through() -> None:
    """Test @validate decorator passes through already validated Pydantic model."""

    @validate(UserRequest)
    def handle_user(data: UserRequest) -> str:
        assert isinstance(data, UserRequest)
        return data.name

    user_obj = UserRequest(name="Eve", email="eve@example.com", age=22)
    res = handle_user(user_obj)
    assert res == "Eve"


@pytest.mark.asyncio
async def test_validation_module_integration() -> None:
    """Test ValidationModule setup, teardown and health check."""
    runtime = ForgeRuntime()
    module = ValidationModule()
    runtime.register(module)

    await runtime.init()
    try:
        health = module.health_check()
        assert health.status == "ok"
    finally:
        await runtime.teardown()
