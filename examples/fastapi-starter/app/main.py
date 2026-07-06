from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from forge import ForgeRuntime, log
from forge.cache import cached
from forge.health import HealthResult, check, health_router

from .models import Item, ItemCreate, Weather
from .module import AppModule

runtime = ForgeRuntime()


@check("custom_dependency", critical=False)
async def check_custom_dep() -> HealthResult:
    return HealthResult.ok("Custom dependency is reachable")


@cached(ttl=120, key="weather:{city}", namespace="weather")
async def fetch_weather(city: str) -> dict:
    await asyncio.sleep(0.1)
    data = {
        "london": {"temperature": 15.2, "condition": "cloudy", "humidity": 72},
        "paris": {"temperature": 22.0, "condition": "sunny", "humidity": 55},
        "tokyo": {"temperature": 18.5, "condition": "rainy", "humidity": 85},
        "new york": {"temperature": 12.0, "condition": "windy", "humidity": 60},
        "sydney": {"temperature": 26.0, "condition": "clear", "humidity": 45},
    }
    result = data.get(city.lower())
    if result is None:
        raise ValueError(f"Weather data not available for '{city}'")
    return result


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    runtime.use_defaults()
    runtime.register(AppModule())
    await runtime.init()
    logger = log.get("app")
    logger.info("Application startup complete")
    yield
    await runtime.teardown()
    log.get("app").info("Application shutdown complete")


app = FastAPI(
    title="Forge FastAPI Starter",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health_router)


@app.get("/")
async def root() -> dict[str, str]:
    logger = log.get("app")
    logger.info("Root endpoint called")
    return {"message": "Forge FastAPI Starter is running", "version": "0.1.0"}


@app.get("/items/{item_id}", response_model=Item)
async def get_item(item_id: int) -> Item:
    items = {
        1: Item(id=1, name="Laptop", price=999.99),
        2: Item(id=2, name="Mouse", price=29.99),
        3: Item(id=3, name="Keyboard", price=79.99),
    }
    item = items.get(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    logger = log.get("app")
    logger.info("Item retrieved", item_id=item_id, item_name=item.name)
    return item


@app.post("/items", response_model=Item, status_code=201)
async def create_item(item_in: ItemCreate) -> Item:
    logger = log.get("app")
    logger.info("Item created", item_name=item_in.name)
    return Item(id=4, **item_in.model_dump())


@app.get("/weather/{city}", response_model=Weather)
async def get_weather(city: str) -> Weather:
    try:
        data = await fetch_weather(city)
        logger = log.get("app")
        logger.info("Weather fetched", city=city)
        return Weather(city=city.capitalize(), **data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


class EchoResponse(BaseModel):
    message: str
    echo: str


@app.post("/echo", response_model=EchoResponse)
async def echo(body: EchoResponse) -> EchoResponse:
    return EchoResponse(message=body.message, echo=body.message)


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
