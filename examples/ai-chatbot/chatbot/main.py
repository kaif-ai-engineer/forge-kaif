from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from forge import AIModule, ForgeRuntime, log
from forge.ai import (
    AIError,
    AIProviderError,
    AllModelsFailedError,
    Message,
    RateLimitError,
    StructuredOutputError,
    complete,
    stream,
)
from forge.retry import retry

from .history import ConversationEntry, ConversationHistory
from .models import ChatResponse, ConversationSummary, Sentiment

SYSTEM_PROMPT = """You are a helpful, concise assistant. Respond naturally to the user.
When asked to analyze sentiment or extract topics, provide structured analysis."""


class Chatbot:
    def __init__(self) -> None:
        self.history = ConversationHistory(max_turns=20)
        self.logger = log.get("chatbot")

    async def chat(self, user_input: str) -> ChatResponse:
        messages = self.history.build_messages(SYSTEM_PROMPT, user_input)
        self.logger.info("Sending chat request", turn=self.history.turn_count + 1)

        try:
            result = await self._call_with_structured_output(messages)
        except (StructuredOutputError, AIProviderError, AllModelsFailedError):
            self.logger.warning("Structured output failed, falling back to plain completion")
            try:
                fallback_resp = await self._call_plain(messages)
            except AIError:
                self.logger.warning("Plain completion also failed, using fallback response")
                fallback_resp = "I'm having trouble connecting to my AI service right now."
            result = ChatResponse(
                reply=fallback_resp,
                sentiment=Sentiment.NEUTRAL,
                topics=[],
                confidence=0.0,
            )
        except Exception:
            self.logger.exception("Chat request failed")
            raise

        entry = ConversationEntry(
            user_message=user_input,
            assistant_reply=result.reply,
            sentiment=result.sentiment.value,
            topics=result.topics,
        )
        self.history.add_entry(entry)
        self.logger.info(
            "Chat response received",
            sentiment=result.sentiment.value,
            topics=result.topics,
            confidence=result.confidence,
        )
        return result

    async def chat_stream(self, user_input: str) -> AsyncIterator[str]:
        messages = self.history.build_messages(SYSTEM_PROMPT, user_input)
        self.logger.info("Starting streaming chat", turn=self.history.turn_count + 1)

        full_reply = ""
        async for chunk in stream(messages=messages, temperature=0.7):
            if chunk.delta:
                full_reply += chunk.delta
                yield chunk.delta

        entry = ConversationEntry(
            user_message=user_input,
            assistant_reply=full_reply,
        )
        self.history.add_entry(entry)
        self.logger.info("Streaming chat complete", chars=len(full_reply))

    async def summarize(self) -> ConversationSummary:
        if not self.history.entries:
            return ConversationSummary(title="Empty conversation", key_points=["No messages yet"])

        transcript = "\n".join(
            f"User: {e.user_message}\nAssistant: {e.assistant_reply}" for e in self.history.entries
        )
        try:
            summary = await complete(
                messages=[
                    Message.system(
                        "Summarize this conversation concisely with key points and action items."
                    ),
                    Message.user(transcript),
                ],
                output_schema=ConversationSummary,
                temperature=0.3,
            )
            return summary
        except StructuredOutputError:
            self.logger.warning("Summarization structured output failed, returning basic summary")
            return ConversationSummary(
                title="Conversation",
                key_points=[
                    f"{e.user_message} → {e.assistant_reply[:50]}" for e in self.history.entries
                ],
            )

    async def _call_with_structured_output(self, messages: list) -> ChatResponse:
        result = await complete(
            messages=messages,
            output_schema=ChatResponse,
            temperature=0.7,
        )
        return result

    @retry(attempts=2, retryable_exceptions=(RateLimitError,))
    async def _call_plain(self, messages: list) -> str:
        result = await complete(messages=messages, temperature=0.7)
        return result.content if hasattr(result, "content") else str(result)


async def interactive_mode() -> None:
    for lib in ("openai", "httpx", "httpcore", "urllib3"):
        logging.getLogger(lib).setLevel(logging.WARNING)

    runtime = ForgeRuntime()
    runtime.use_defaults()
    runtime.register(AIModule())
    await runtime.init()

    bot = Chatbot()
    logger = log.get("chatbot")
    logger.info(
        "Chatbot started. Type 'exit' to quit, '/summarize' for summary, '/stream' to toggle streaming."
    )

    streaming = False

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            break
        if user_input.lower() == "/summarize":
            summary = await bot.summarize()
            print(f"\nSummary: {summary.title}")
            for pt in summary.key_points:
                print(f"  - {pt}")
            if summary.action_items:
                print("  Action items:")
                for ai in summary.action_items:
                    print(f"    * {ai}")
            continue
        if user_input.lower() == "/stream":
            streaming = not streaming
            print(f"Streaming {'on' if streaming else 'off'}")
            continue

        print()
        if streaming:
            print("Bot:  ", end="", flush=True)
            async for delta in bot.chat_stream(user_input):
                print(delta, end="", flush=True)
            print()
            print()
        else:
            response = await bot.chat(user_input)
            print(f"Bot:  {response.reply}")
            print(
                f"      [{response.sentiment.value}, confidence={response.confidence:.2f}]"
                + (f" topics={', '.join(response.topics)}" if response.topics else "")
            )

    await runtime.teardown()
    logger.info("Chatbot stopped")


def main() -> None:
    asyncio.run(interactive_mode())


if __name__ == "__main__":
    main()
