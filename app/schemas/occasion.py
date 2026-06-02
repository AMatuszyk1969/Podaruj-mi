from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.item import ItemResponse
from app.schemas.user import UserPublic

OccasionType = Literal["birthday", "name_day", "christmas", "anniversary", "other"]
Visibility = Literal["public", "friends", "family"]


class OccasionCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    occasion_type: OccasionType = "other"
    occasion_date: date
    pledge_deadline: datetime
    visibility: Visibility = "friends"
    recipient_id: str
    family_id: str | None = None

    @model_validator(mode="after")
    def deadline_before_occasion(self) -> "OccasionCreateRequest":
        if self.pledge_deadline.date() > self.occasion_date:
            raise ValueError("Deadline musi byc przed lub w dniu okazji")
        return self


class OccasionUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    occasion_type: OccasionType | None = None
    occasion_date: date | None = None
    pledge_deadline: datetime | None = None
    visibility: Visibility | None = None


class OccasionListItem(BaseModel):
    id: str
    title: str
    occasion_type: str
    occasion_date: date
    pledge_deadline: datetime
    recipient: UserPublic
    items_count: int
    pledged_count: int

    model_config = {"from_attributes": True}


class OccasionResponse(BaseModel):
    id: str
    title: str
    description: str | None
    occasion_type: str
    occasion_date: date
    pledge_deadline: datetime
    visibility: str
    created_by: UserPublic
    recipient: UserPublic
    items: list[ItemResponse]
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedOccasions(BaseModel):
    items: list[OccasionListItem]
    total: int
    page: int
    pages: int
