from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.auth import MessageResponse
from app.schemas.social import FamilyCreateRequest, FamilyInviteRequest, FamilyMemberResponse, FamilyResponse
from app.services.social_service import FamilyService
from app.utils.deps import get_current_user

router = APIRouter(prefix="/families", tags=["families"])


@router.post("", status_code=201, response_model=FamilyResponse)
def create_family(
    data: FamilyCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return FamilyService.create(db, data, current_user.id)


@router.get("/my", response_model=FamilyResponse)
def my_family(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return FamilyService.get_my_family(db, current_user.id)


@router.post("/{family_id}/invite", status_code=201, response_model=MessageResponse)
def invite_to_family(
    family_id: str,
    data: FamilyInviteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return FamilyService.invite(db, family_id, data.user_email, current_user.id)


@router.post("/{family_id}/members/{member_id}/accept", response_model=FamilyMemberResponse)
def accept_membership(
    family_id: str,
    member_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return FamilyService.accept_membership(db, family_id, member_id, current_user.id)
