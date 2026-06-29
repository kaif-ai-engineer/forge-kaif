from __future__ import annotations

from typing import Any, Self

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: str = Field(description="One of system, user, assistant, or tool")
    content: str = Field(description="Message text content")

    @classmethod
    def system(cls, content: str) -> Self:
        return cls(role="system", content=content)

    @classmethod
    def user(cls, content: str) -> Self:
        return cls(role="user", content=content)

    @classmethod
    def assistant(cls, content: str) -> Self:
        return cls(role="assistant", content=content)


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

    @property
    def prompt_tokens(self) -> int:
        return self.input_tokens

    @property
    def completion_tokens(self) -> int:
        return self.output_tokens

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


TokenUsage = Usage


class StreamChunk(BaseModel):
    delta: str = ""
    finish_reason: str | None = None
    usage: Usage | None = None
    model: str = ""
    provider: str = ""

    @property
    def token_usage(self) -> Usage | None:
        return self.usage


class CompletionResponse(BaseModel):
    model: str
    message: Message
    usage: Usage | None = None
    latency_ms: float = 0.0
    provider: str = ""
    cost: float = 0.0

    @property
    def content(self) -> str:
        return self.message.content

    @property
    def token_usage(self) -> Usage | None:
        return self.usage


AIResponse = CompletionResponse
