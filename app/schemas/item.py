from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

CollectionMode = Literal["single", "multiple"]


class PledgeResponse(BaseModel):
    id: str
    user_id: str
    user_name: str | None = None
    user_avatar_url: str | None = None
    note: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ItemCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    url: str | None = None
    estimated_price: Decimal | None = Field(default=None, ge=0)
    collection_mode: CollectionMode = "single"
    max_pledges: int = Field(default=0, ge=0)


class ItemUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    url: str | None = None
    estimated_price: Decimal | None = Field(default=None, ge=0)
    collection_mode: CollectionMode | None = None
    max_pledges: int | None = Field(default=None, ge=0)


class ItemResponse(BaseModel):
    id: str
    name: str
    description: str | None
    url: str | None
    estimated_price: Decimal | None
    collection_mode: str
    max_pledges: int
    status: str
    pledges_count: int
    pledges: list[PledgeResponse]  # ukryte dla obdarowywanego – filtrowane w serwisie

    model_config = {"from_attributes": True}
