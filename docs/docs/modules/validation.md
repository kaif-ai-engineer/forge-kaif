# Validation Module

`forge.validation` — Pydantic-integrated input validation with consistent error responses.

## Overview

The Validation module validates function input against Pydantic schemas with zero
boilerplate. It integrates with FastAPI to return structured 422 error responses
that are consistent across your entire API.

## Installation

```bash
pip install forge-runtime
```

## Quick Start

```python
from pydantic import BaseModel
from forge.validation import validate

class CreateUserRequest(BaseModel):
    name: str
    email: str
    age: int

@validate(schema=CreateUserRequest)
async def create_user(data: CreateUserRequest):
    # data is already a validated CreateUserRequest instance
    return await db.insert_user(data)
```

## Key Features

### Structured Error Responses

When validation fails, the module returns a consistent error format:

```json
{
  "detail": [
    {
      "loc": ["body", "email"],
      "msg": "value is not a valid email address",
      "type": "value_error"
    }
  ]
}
```

### Automatic Error Formatting

```python
from pydantic import ValidationError
from forge.validation import format_validation_error

try:
    validated = schema.model_validate(data)
except ValidationError as exc:
    error_response = format_validation_error(exc)
    # error_response is a ValidationErrorResponse with structured detail
```

### FastAPI Integration

The validation decorator works seamlessly with FastAPI routes, raising
`HTTPException(422)` with structured error details that FastAPI converts
to proper JSON responses.

## API Reference

::: forge.validation
    options:
      show_root_heading: false
      show_bases: false
      show_source: false
