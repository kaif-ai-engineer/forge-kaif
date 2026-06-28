from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: str = Field(description="One of system, user, assistant, or tool")
    content: str = Field(description="Message text content")


class CompletionRequest(BaseModel):
    model: str
    messages: list[Message]
    max_tokens: int | None = Field(default=None, ge=1)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    stream: bool = False
    extra: dict[str, Any] = Field(default_factory=dict)


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class CompletionResponse(BaseModel):
    model: str
    message: Message
    usage: Usage | None = None
    latency_ms: float = 0.0
