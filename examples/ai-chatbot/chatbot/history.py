from __future__ import annotations

from dataclasses import dataclass, field

from forge.ai import Message


@dataclass
class ConversationEntry:
    user_message: str
    assistant_reply: str
    sentiment: str = "neutral"
    topics: list[str] = field(default_factory=list)


class ConversationHistory:
    def __init__(self, max_turns: int = 20) -> None:
        self._entries: list[ConversationEntry] = []
        self._max_turns = max_turns

    def add_entry(self, entry: ConversationEntry) -> None:
        self._entries.append(entry)
        if len(self._entries) > self._max_turns:
            self._entries.pop(0)

    @property
    def entries(self) -> list[ConversationEntry]:
        return list(self._entries)

    @property
    def turn_count(self) -> int:
        return len(self._entries)

    def build_messages(self, system_prompt: str, new_user_message: str) -> list[Message]:
        messages = [Message.system(system_prompt)]
        for entry in self._entries:
            messages.append(Message.user(entry.user_message))
            messages.append(Message.assistant(entry.assistant_reply))
        messages.append(Message.user(new_user_message))
        return messages

    def clear(self) -> None:
        self._entries.clear()
