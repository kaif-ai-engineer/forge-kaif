from __future__ import annotations

from pydantic import BaseModel


class Item(BaseModel):
    id: int
    name: str
    price: float
    in_stock: bool = True


class ItemCreate(BaseModel):
    name: str
    price: float
    in_stock: bool = True


class Weather(BaseModel):
    city: str
    temperature: float
    condition: str
    humidity: int
