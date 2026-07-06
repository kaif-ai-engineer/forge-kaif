# AI Chatbot

A streaming chatbot built with **Forge AI** that demonstrates structured output, conversation history, and retry logic.

## Features

- **Structured Output** — Uses Pydantic models (`ChatResponse`, `ConversationSummary`) to extract sentiment, topics, and confidence from each message
- **Conversation History** — Maintains the last 20 turns and injects them as context for coherent multi-turn dialogue
- **Streaming & Non-Streaming** — Toggle between real-time streaming and structured response modes
- **Retry Logic** — Automatic retry (exponential backoff) on API failures via `@retry` decorator
- **Conversation Summarization** — Generate a summary with key points and action items via `/summarize`

## Prerequisites

- Python 3.11+
- An OpenAI API key (or other provider supported by Forge AI)

## Installation

```bash
# Clone the repository (if you haven't already)
git clone <repo-url> && cd forge-kaif

# Install forge (editable, from project root)
pip install -e .[openai]

# Install example dependencies
cd examples/ai-chatbot
pip install -r requirements.txt
```

## API Key Setup

Copy the example env file and add your OpenAI API key:

```bash
cp .env.example .env
```

Edit `.env` and set:

```
FORGE_AI_OPENAI_API_KEY=sk-your-api-key-here
```

You can also configure the model, timeout, and retry settings via environment variables (see `.env.example`).

## Running

```bash
# From examples/ai-chatbot
python -m chatbot.main
```

## Usage

Once the chatbot starts, you'll see:

```
Chatbot started. Type 'exit' to quit, '/summarize' for summary, '/stream' to toggle streaming.
```

### Commands

| Input | Action |
|---|---|
| `exit` / `quit` | Stop the chatbot |
| `/summarize` | Generate a structured summary of the conversation |
| `/stream` | Toggle between streaming and structured response mode |

### Structured Response Mode (default)

Each response shows the reply plus analysis metadata:

```
You: What's the weather like in Paris?

Bot: I don't have real-time weather data, but Paris generally has a mild climate with average temperatures ranging from 5°C in winter to 25°C in summer.
[sentiment: neutral, confidence: 0.95]
[topics: weather, Paris, climate]
```

### Streaming Mode

Toggle with `/stream`. Responses appear character-by-character in real time without structured metadata.

### Conversation Summarization

Type `/summarize` at any point to get a structured overview:

```
[Summary] Title: Weather inquiry and chatbot capabilities
  - User asked about weather in Paris
  - Assistant explained climate information
  - Assistant clarified lack of real-time data access
```

## Project Structure

```
examples/ai-chatbot/
├── chatbot/
│   ├── __init__.py
│   ├── main.py          # Chatbot class, CLI loop, entry point
│   ├── models.py        # Pydantic schemas for structured output
│   └── history.py       # Conversation history manager
├── forge.config.toml    # Forge static config
├── .env                 # API keys (git-ignored)
├── .env.example         # Template for .env
├── requirements.txt
└── README.md
```

## How It Works

1. **Runtime initialization** — `ForgeRuntime` registers `ConfigModule`, `LogModule`, `RetryModule`, `HealthModule`, `CacheModule`, and `AIModule`
2. **Message construction** — `ConversationHistory.build_messages()` prepends a system prompt and all prior turns before each new user message
3. **AI call** — `forge.ai.complete()` routes the request through the model router to the appropriate provider adapter
4. **Structured enforcement** — The `StructuredOutputEnforcer` retries on malformed output (up to 3 times by default) to produce valid `ChatResponse` / `ConversationSummary` objects
5. **Retry** — The `@retry(attempts=3)` decorator on `_call_with_structured_output` handles transient API failures with exponential backoff + jitter
