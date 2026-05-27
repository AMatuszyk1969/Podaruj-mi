from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.auth import MessageResponse
from app.schemas.social import FriendshipInviteRequest, FriendshipResponse
from app.schemas.user import UserPublic
from app.services.social_service import FriendService
from app.utils.deps import get_current_user

router = APIRouter(prefix="/friends", tags=["friends"])


@router.get("", response_model=list[UserPublic])
def list_friends(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return FriendService.list_friends(db, current_user.id)


@router.get("/invitations", response_model=list[FriendshipResponse])
def list_invitations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return FriendService.list_invitations(db, current_user.id)


@router.post("/invitations", status_code=201, response_model=FriendshipResponse)
def invite(
    data: FriendshipInviteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return FriendService.invite(db, data.addressee_email, current_user.id)


@router.post("/invitations/{invitation_id}/accept", response_model=FriendshipResponse)
def accept(
    invitation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return FriendService.accept(db, invitation_id, current_user.id)


@router.post("/invitations/{invitation_id}/reject", response_model=MessageResponse)
def reject(
    invitation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return FriendService.reject(db, invitation_id, current_user.id)


@router.delete("/{friend_id}", status_code=204)
def remove_friend(
    friend_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    FriendService.remove(db, friend_id, current_user.id)
