from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.schemas.user import UserPublic


# ── Friendship ────────────────────────────────────────────────────────────────

class FriendshipInviteRequest(BaseModel):
    addressee_email: EmailStr


class FriendshipResponse(BaseModel):
    id: str
    requester: UserPublic
    addressee: UserPublic
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Family ────────────────────────────────────────────────────────────────────

class FamilyCreateRequest(BaseModel):
    name: str


class FamilyInviteRequest(BaseModel):
    user_email: EmailStr


class FamilyMemberResponse(BaseModel):
    id: str
    user: UserPublic
    status: str
    joined_at: datetime | None = None

    model_config = {"from_attributes": True}


class FamilyResponse(BaseModel):
    id: str
    name: str
    created_by: UserPublic
    members: list[FamilyMemberResponse]
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Pledge request ────────────────────────────────────────────────────────────

class PledgeCreateRequest(BaseModel):
    note: str | None = None
