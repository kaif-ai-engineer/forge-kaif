from __future__ import annotations

import inspect
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar, cast

from fastapi import HTTPException
from pydantic import BaseModel, ValidationError

from forge.validation.module import ValidationModule

F = TypeVar("F", bound=Callable[..., Any])


class ValidationErrorDetail(BaseModel):
    """Details of a single validation error."""

    loc: list[str | int]
    msg: str
    type: str


class ValidationErrorResponse(BaseModel):
    """Standard error response for validation failures."""

    detail: list[ValidationErrorDetail]


def format_validation_error(exc: ValidationError) -> ValidationErrorResponse:
    """Convert Pydantic ValidationError to standard error response format."""
    details = []
    for error in exc.errors():
        loc = list(error.get("loc", []))
        # Ensure location starts with "body" for consistency with FastAPI
        if not loc or loc[0] != "body":
            loc.insert(0, "body")

        details.append(
            ValidationErrorDetail(
                loc=loc,
                msg=error.get("msg", ""),
                type=error.get("type", ""),
            )
        )
    return ValidationErrorResponse(detail=details)


def validate(schema: type[BaseModel]) -> Callable[[F], F]:
    """
    Decorator that validates function input against a Pydantic schema.

    On validation error, raises HTTPException(422) with structured error details.
    """

    def decorator(func: F) -> F:
        # Determine the position of the argument to validate
        # By default, we inspect the first parameter (after self/cls if applicable)
        first_param_name: str | None = None
        has_self_cls = False
        try:
            sig = inspect.signature(func)
            params = list(sig.parameters.keys())
            if params and params[0] in ("self", "cls"):
                has_self_cls = True
                if len(params) > 1:
                    first_param_name = params[1]
            elif params:
                first_param_name = params[0]
        except Exception:  # noqa: S110
            pass

        def _validate_args(
            args: tuple[Any, ...],
            kwargs: dict[str, Any],
        ) -> tuple[tuple[Any, ...], dict[str, Any]]:
            new_args = list(args)
            new_kwargs = dict(kwargs)

            # Check positional arguments
            body: Any = None
            body_index: int | None = None

            if args:
                if has_self_cls and len(args) > 1:
                    body = args[1]
                    body_index = 1
                elif not has_self_cls:
                    body = args[0]
                    body_index = 0

            # Check keyword arguments if not found positionally
            if body is None and first_param_name and first_param_name in kwargs:
                body = kwargs[first_param_name]

            if isinstance(body, dict):
                try:
                    validated = schema.model_validate(body)
                    if body_index is not None:
                        new_args[body_index] = validated
                    elif first_param_name:
                        new_kwargs[first_param_name] = validated
                except ValidationError as exc:
                    formatted = format_validation_error(exc)
                    raise HTTPException(
                        status_code=422,
                        detail=formatted.model_dump()["detail"],
                    ) from exc
            elif isinstance(body, schema):
                # Already correct type, pass through
                pass

            return tuple(new_args), new_kwargs

        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                validated_args, validated_kwargs = _validate_args(args, kwargs)
                return await func(*validated_args, **validated_kwargs)

            return cast("F", async_wrapper)

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            validated_args, validated_kwargs = _validate_args(args, kwargs)
            return func(*validated_args, **validated_kwargs)

        return cast("F", sync_wrapper)

    return decorator


__all__ = [
    "ValidationErrorDetail",
    "ValidationErrorResponse",
    "ValidationModule",
    "format_validation_error",
    "validate",
]
