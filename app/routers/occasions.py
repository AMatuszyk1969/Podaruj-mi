from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.item import ItemCreateRequest, ItemResponse, ItemUpdateRequest
from app.schemas.occasion import OccasionCreateRequest, OccasionResponse, OccasionUpdateRequest, PaginatedOccasions
from app.schemas.social import PledgeCreateRequest
from app.schemas.item import PledgeResponse
from app.services.occasion_service import ItemService, OccasionService, PledgeService
from app.utils.deps import get_current_user

router = APIRouter(tags=["occasions & items"])


# ── Occasions ─────────────────────────────────────────────────────────────────

@router.get("/occasions", response_model=PaginatedOccasions)
def list_occasions(
    upcoming_only: bool = Query(True),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return OccasionService.list_visible(db, current_user.id, upcoming_only, page, limit)


@router.post("/occasions", status_code=201, response_model=OccasionResponse)
def create_occasion(
    data: OccasionCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return OccasionService.create(db, data, current_user.id)


@router.get("/occasions/{occasion_id}", response_model=OccasionResponse)
def get_occasion(
    occasion_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return OccasionService.get(db, occasion_id, current_user.id)


@router.patch("/occasions/{occasion_id}", response_model=OccasionResponse)
def update_occasion(
    occasion_id: str,
    data: OccasionUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return OccasionService.update(db, occasion_id, data, current_user.id)


@router.delete("/occasions/{occasion_id}", status_code=204)
def delete_occasion(
    occasion_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    OccasionService.delete(db, occasion_id, current_user.id)


# ── Items ─────────────────────────────────────────────────────────────────────

@router.post("/occasions/{occasion_id}/items", status_code=201, response_model=ItemResponse)
def create_item(
    occasion_id: str,
    data: ItemCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ItemService.create(db, occasion_id, data, current_user.id)


@router.patch("/items/{item_id}", response_model=ItemResponse)
def update_item(
    item_id: str,
    data: ItemUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ItemService.update(db, item_id, data, current_user.id)


@router.delete("/items/{item_id}", status_code=204)
def delete_item(
    item_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ItemService.delete(db, item_id, current_user.id)


# ── Pledges ───────────────────────────────────────────────────────────────────

@router.post("/items/{item_id}/pledge", status_code=201, response_model=PledgeResponse)
def create_pledge(
    item_id: str,
    data: PledgeCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return PledgeService.create(db, item_id, data, current_user.id)


@router.delete("/items/{item_id}/pledge", status_code=204)
def delete_pledge(
    item_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    PledgeService.delete(db, item_id, current_user.id)
