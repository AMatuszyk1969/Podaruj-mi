from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.family import Family, FamilyMember
from app.models.friendship import Friendship
from app.models.user import User
from app.schemas.social import (
    FamilyCreateRequest,
    FamilyMemberResponse,
    FamilyResponse,
    FriendshipResponse,
)
from app.schemas.user import UserPublic


class FriendService:

    @staticmethod
    def list_friends(db: Session, user_id: str) -> list[UserPublic]:
        sent = db.query(Friendship).filter(
            Friendship.requester_id == user_id, Friendship.status == "accepted"
        ).all()
        recv = db.query(Friendship).filter(
            Friendship.addressee_id == user_id, Friendship.status == "accepted"
        ).all()
        users = [f.addressee for f in sent] + [f.requester for f in recv]
        return [UserPublic.model_validate(u) for u in users]

    @staticmethod
    def list_invitations(db: Session, user_id: str) -> list[FriendshipResponse]:
        rows = db.query(Friendship).filter(
            (Friendship.requester_id == user_id) | (Friendship.addressee_id == user_id),
            Friendship.status == "pending",
        ).all()
        return [FriendshipResponse.model_validate(r) for r in rows]

    @staticmethod
    def invite(db: Session, addressee_email: str, requester_id: str) -> FriendshipResponse:
        addressee = db.query(User).filter(User.email == addressee_email).first()
        if not addressee:
            raise HTTPException(status_code=404, detail="Uzytkownik o podanym e-mail nie istnieje")
        if addressee.id == requester_id:
            raise HTTPException(status_code=400, detail="Nie mozna zaprosic samego siebie")

        existing = db.query(Friendship).filter(
            (
                (Friendship.requester_id == requester_id) &
                (Friendship.addressee_id == addressee.id)
            ) | (
                (Friendship.requester_id == addressee.id) &
                (Friendship.addressee_id == requester_id)
            )
        ).first()
        if existing:
            raise HTTPException(status_code=409,
                                detail="Zaproszenie juz istnieje lub jestescie znajomymi")

        friendship = Friendship(requester_id=requester_id, addressee_id=addressee.id)
        db.add(friendship)
        db.commit()
        db.refresh(friendship)
        return FriendshipResponse.model_validate(friendship)

    @staticmethod
    def accept(db: Session, invitation_id: str, user_id: str) -> FriendshipResponse:
        f = db.get(Friendship, invitation_id)
        if not f or f.status != "pending":
            raise HTTPException(status_code=404, detail="Zaproszenie nie istnieje")
        if f.addressee_id != user_id:
            raise HTTPException(status_code=403, detail="Nie jestes adresatem tego zaproszenia")
        f.status = "accepted"
        db.commit()
        db.refresh(f)
        return FriendshipResponse.model_validate(f)

    @staticmethod
    def reject(db: Session, invitation_id: str, user_id: str) -> dict:
        f = db.get(Friendship, invitation_id)
        if not f or f.status != "pending":
            raise HTTPException(status_code=404, detail="Zaproszenie nie istnieje")
        if f.addressee_id != user_id:
            raise HTTPException(status_code=403, detail="Nie jestes adresatem")
        f.status = "rejected"
        db.commit()
        return {"message": "Zaproszenie odrzucone"}

    @staticmethod
    def remove(db: Session, friend_id: str, user_id: str) -> None:
        f = db.query(Friendship).filter(
            Friendship.status == "accepted",
            (
                ((Friendship.requester_id == user_id) & (Friendship.addressee_id == friend_id)) |
                ((Friendship.requester_id == friend_id) & (Friendship.addressee_id == user_id))
            ),
        ).first()
        if not f:
            raise HTTPException(status_code=404, detail="Relacja znajomosci nie istnieje")
        db.delete(f)
        db.commit()


class FamilyService:

    @staticmethod
    def create(db: Session, data: FamilyCreateRequest, user_id: str) -> FamilyResponse:
        family = Family(name=data.name, created_by_id=user_id)
        db.add(family)
        db.flush()

        # Tworca automatycznie staje sie czlonkiem
        member = FamilyMember(
            family_id=family.id,
            user_id=user_id,
            status="accepted",
            joined_at=datetime.now(timezone.utc),
        )
        db.add(member)
        db.commit()
        db.refresh(family)
        return FamilyResponse.model_validate(family)

    @staticmethod
    def get_my_family(db: Session, user_id: str) -> FamilyResponse:
        membership = db.query(FamilyMember).filter(
            FamilyMember.user_id == user_id, FamilyMember.status == "accepted"
        ).first()
        if not membership:
            raise HTTPException(status_code=404, detail="Nie nalezysz do zadnej rodziny")
        return FamilyResponse.model_validate(membership.family)

    @staticmethod
    def invite(db: Session, family_id: str, user_email: str, inviter_id: str) -> dict:
        family = db.get(Family, family_id)
        if not family:
            raise HTTPException(status_code=404, detail="Rodzina nie istnieje")
        if family.created_by_id != inviter_id:
            raise HTTPException(status_code=403, detail="Tylko tworca rodziny moze zapraszac")

        invitee = db.query(User).filter(User.email == user_email).first()
        if not invitee:
            raise HTTPException(status_code=404, detail="Uzytkownik nie istnieje")

        existing = db.query(FamilyMember).filter(
            FamilyMember.family_id == family_id, FamilyMember.user_id == invitee.id
        ).first()
        if existing:
            raise HTTPException(status_code=409, detail="Uzytkownik jest juz czlonkiem lub zaproszony")

        member = FamilyMember(family_id=family_id, user_id=invitee.id, status="pending")
        db.add(member)
        db.commit()
        return {"message": "Zaproszenie wyslane"}

    @staticmethod
    def accept_membership(db: Session, family_id: str, member_id: str, user_id: str) -> FamilyMemberResponse:
        member = db.get(FamilyMember, member_id)
        if not member or member.family_id != family_id:
            raise HTTPException(status_code=404, detail="Czlonkostwo nie istnieje")
        if member.user_id != user_id:
            raise HTTPException(status_code=403, detail="Nie mozesz zaakceptowac cudzego zaproszenia")
        member.status = "accepted"
        member.joined_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(member)
        return FamilyMemberResponse.model_validate(member)
