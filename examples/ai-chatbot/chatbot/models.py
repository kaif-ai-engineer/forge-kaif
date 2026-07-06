from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field


class Sentiment(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class ChatResponse(BaseModel):
    reply: str = Field(description="The chatbot's reply to the user")
    sentiment: Sentiment = Field(description="Detected sentiment of the user's message")
    topics: list[str] = Field(default_factory=list, description="Key topics mentioned")
    confidence: Annotated[float, Field(ge=0.0, le=1.0)] = Field(
        description="Confidence score for the detected sentiment"
    )


class ConversationSummary(BaseModel):
    title: str = Field(description="Short title for this conversation")
    key_points: list[str] = Field(description="Important points discussed")
    action_items: list[str] = Field(default_factory=list, description="Action items identified")
