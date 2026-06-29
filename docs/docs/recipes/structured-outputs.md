# Structured AI Outputs

Ensure AI responses follow a strict schema using Pydantic models.

## The Problem

LLMs return unstructured text. When you need structured data — JSON with specific
fields, types, and validation — you end up parsing and validating raw output.

## The Solution

forge's AI module accepts a Pydantic `output_schema` and handles everything:
JSON schema injection into the prompt, response parsing, validation, and automatic
retry with error feedback when the output doesn't match.

## Basic Usage

```python
from pydantic import BaseModel
from forge.ai import complete, Message


class Joke(BaseModel):
    setup: str
    punchline: str
    rating: int  # 1-10


joke = await complete(
    messages=[Message.user("Tell me a programming joke")],
    output_schema=Joke,
)
print(f"{joke.setup}\n{joke.punchline} (Rating: {joke.rating}/10)")
```

## Complex Schemas

```python
from pydantic import BaseModel
from typing import List


class Product(BaseModel):
    name: str
    price: float
    in_stock: bool


class CatalogResponse(BaseModel):
    products: List[Product]
    total_count: int
    category: str


result = await complete(
    messages=[Message.user("List 5 laptop products")],
    output_schema=CatalogResponse,
)
print(f"Found {result.total_count} products in {result.category}")
for product in result.products:
    print(f"  - {product.name}: ${product.price}")
```

## How It Works

1. forge injects the JSON schema of your Pydantic model into the system prompt
2. The LLM returns a JSON response
3. forge validates the response against your schema
4. If validation fails, forge retries with the error message as feedback
5. After max retries (configurable), raises `StructuredOutputError`

## Configuration

```python
from forge.config import AIConfig

config = AIConfig(
    structured_output_retries=3,  # Max retries on invalid output
)
```
