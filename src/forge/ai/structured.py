from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, TypeVar

from pydantic import BaseModel, ValidationError

from forge.ai.exceptions import StructuredOutputError
from forge.ai.models import Message

if TYPE_CHECKING:
    from forge.ai.models import CompletionResponse

T = TypeVar("T", bound=BaseModel)

_JSON_BLOCK_PATTERN = re.compile(
    r"```(?:json)?\s*\n?(.*?)\n?```",
    re.DOTALL | re.IGNORECASE,
)


def extract_json(text: str) -> dict[str, Any]:
    """
    Robustly extract a JSON object from model output.

    Handles:
    1. Pure JSON (model responded with just a JSON object)
    2. JSON in a markdown code block (```json ... ```)
    3. JSON embedded in prose (extracts the first { ... } block)

    Raises:
        json.JSONDecodeError: If no valid JSON can be extracted
    """
    from typing import cast

    # Try direct parse first (cleanest case)
    stripped = text.strip()
    try:
        val = json.loads(stripped)
        if isinstance(val, dict):
            return cast("dict[str, Any]", val)
    except json.JSONDecodeError:
        pass

    # Try extracting from code block
    match = _JSON_BLOCK_PATTERN.search(text)
    if match:
        try:
            val = json.loads(match.group(1).strip())
            if isinstance(val, dict):
                return cast("dict[str, Any]", val)
        except json.JSONDecodeError:
            pass

    # Try extracting first {...} block
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            val = json.loads(text[start : end + 1])
            if isinstance(val, dict):
                return cast("dict[str, Any]", val)
        except json.JSONDecodeError:
            pass

    raise json.JSONDecodeError("No valid JSON found in model output", text, 0)


def build_schema_prompt(schema: type[BaseModel]) -> str:
    """
    Build a prompt instruction that tells the model to respond with JSON matching a schema.

    The prompt includes:
    - The JSON schema definition
    - An explicit instruction to return ONLY JSON
    - A reminder about required fields
    """
    schema_json = json.dumps(schema.model_json_schema(), indent=2)
    required_fields = list(schema.model_fields.keys())

    return (
        f"You must respond with a valid JSON object that matches this schema:\n\n"
        f"```json\n{schema_json}\n```\n\n"
        f"Required fields: {', '.join(required_fields)}\n\n"
        f"IMPORTANT: Respond with ONLY the JSON object. "
        f"Do not include any explanation, markdown formatting, or text outside the JSON."
    )


def build_retry_prompt(
    original_response: str,
    parse_error: str,
    schema: type[BaseModel],
) -> str:
    """
    Build a correction prompt when the model's response failed to parse.

    Includes the original bad response so the model can understand its mistake.
    """
    return (
        f"Your previous response failed JSON validation:\n\n"
        f"Error: {parse_error}\n\n"
        f"Your response was:\n{original_response}\n\n"
        f"Please provide a corrected response as a valid JSON object matching the schema:\n"
        f"{json.dumps(schema.model_json_schema(), indent=2)}\n\n"
        f"Respond with ONLY the JSON object."
    )


class StructuredOutputEnforcer:
    """Enforces that AI responses conform to a Pydantic schema using a retry loop."""

    def __init__(self, max_retries: int = 3) -> None:
        self.max_retries = max_retries

    async def enforce(
        self,
        messages: list[Message],
        schema: type[T],
        complete_fn: Callable[[list[Message]], Awaitable[CompletionResponse]],
    ) -> T:
        """
        Execute an AI call and enforce a Pydantic output schema with retry.

        Parameters
        ----------
        messages : list[Message]
            The input messages for the conversation.
        schema : type[T]
            The Pydantic model class to validate the response against.
        complete_fn : Callable[[list[Message]], Awaitable[CompletionResponse]]
            The function that executes the completion call.

        Returns
        -------
        T
            An instance of the Pydantic schema filled with validated data.

        Raises
        ------
        StructuredOutputError
            If all retries are exhausted.
        """
        schema_instruction = build_schema_prompt(schema)
        augmented_messages = list(messages) + [Message.user(schema_instruction)]
        current_messages = list(augmented_messages)

        total_attempts = max(1, self.max_retries + 1)
        for attempt in range(total_attempts):
            response = await complete_fn(current_messages)
            content = response.content

            try:
                raw_json = extract_json(content)
                validated = schema.model_validate(raw_json)
                return validated
            except (json.JSONDecodeError, ValidationError, KeyError) as exc:
                if attempt == total_attempts - 1:
                    raise StructuredOutputError(
                        schema_name=schema.__name__,
                        attempts=total_attempts,
                        last_response=content,
                        last_error=str(exc),
                    ) from exc

                correction = build_retry_prompt(
                    original_response=content,
                    parse_error=str(exc),
                    schema=schema,
                )

                current_messages = list(augmented_messages) + [
                    Message.assistant(content),
                    Message.user(correction),
                ]

        raise RuntimeError(
            "Unreachable: structured output retry loop exited without return or raise"
        )
