from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.friendship import Friendship
from app.models.family import Family, FamilyMember
from app.models.item import Item
from app.models.occasion import Occasion
from app.models.pledge import Pledge
from app.models.user import User
from app.schemas.item import ItemCreateRequest, ItemResponse, ItemUpdateRequest, PledgeResponse
from app.schemas.occasion import (
    OccasionCreateRequest,
    OccasionListItem,
    OccasionResponse,
    OccasionUpdateRequest,
    PaginatedOccasions,
)
from app.schemas.social import PledgeCreateRequest


# ── helpers ───────────────────────────────────────────────────────────────────

def _are_friends(db: Session, user_a: str, user_b: str) -> bool:
    return db.query(Friendship).filter(
        Friendship.status == "accepted",
        (
            (Friendship.requester_id == user_a) & (Friendship.addressee_id == user_b)
            | (Friendship.requester_id == user_b) & (Friendship.addressee_id == user_a)
        ),
    ).first() is not None


def _share_family(db: Session, user_a: str, user_b: str) -> bool:
    families_a = {
        m.family_id for m in db.query(FamilyMember).filter(
            FamilyMember.user_id == user_a, FamilyMember.status == "accepted"
        ).all()
    }
    families_b = {
        m.family_id for m in db.query(FamilyMember).filter(
            FamilyMember.user_id == user_b, FamilyMember.status == "accepted"
        ).all()
    }
    return bool(families_a & families_b)


def _can_see(db: Session, occasion: Occasion, viewer_id: str) -> bool:
    if viewer_id in (occasion.created_by_id, occasion.recipient_id):
        return True
    if occasion.visibility == "public":
        return True
    if occasion.visibility == "friends":
        return _are_friends(db, viewer_id, occasion.created_by_id) or \
               _are_friends(db, viewer_id, occasion.recipient_id)
    if occasion.visibility == "family":
        if occasion.family_id:
            # Konkretna rodzina – sprawdź czy oglądający należy do tej właśnie rodziny
            return db.query(FamilyMember).filter(
                FamilyMember.family_id == occasion.family_id,
                FamilyMember.user_id == viewer_id,
                FamilyMember.status == "accepted",
            ).first() is not None
        # Brak wybranej rodziny – stara logika: dowolna wspólna rodzina
        return _share_family(db, viewer_id, occasion.created_by_id) or \
               _share_family(db, viewer_id, occasion.recipient_id)
    return False


def _item_to_response(item: Item, viewer_id: str, recipient_id: str) -> ItemResponse:
    pledges = []
    if viewer_id != recipient_id:  # ukryj przed obdarowywanym
        pledges = [
            PledgeResponse(
                id=p.id,
                user_id=p.user_id,
                user_name=(f"{p.user.first_name} {p.user.last_name}" if p.user else None),
                user_avatar_url=(p.user.avatar_url if p.user else None),
                note=p.note,
                created_at=p.created_at,
            )
            for p in item.pledges
        ]
    return ItemResponse(
        id=item.id,
        name=item.name,
        description=item.description,
        url=item.url,
        estimated_price=item.estimated_price,
        collection_mode=item.collection_mode,
        max_pledges=item.max_pledges,
        status=item.status,
        pledges_count=len(item.pledges),
        pledges=pledges,
    )


# ── Occasion CRUD ─────────────────────────────────────────────────────────────

class OccasionService:

    @staticmethod
    def create(db: Session, data: OccasionCreateRequest, creator_id: str) -> OccasionResponse:
        recipient = db.get(User, data.recipient_id)
        if not recipient:
            raise HTTPException(status_code=404, detail="Obdarowywana osoba nie istnieje")

        occasion = Occasion(**data.model_dump(), created_by_id=creator_id)
        db.add(occasion)
        db.commit()
        db.refresh(occasion)
        return OccasionService._to_response(occasion, creator_id)

    @staticmethod
    def list_visible(
        db: Session, viewer_id: str, upcoming_only: bool, page: int, limit: int
    ) -> PaginatedOccasions:
        from sqlalchemy import or_, and_

        # 1. Graf społecznościowy widza — 3 zapytania zamiast N×M
        friend_ids = {r[0] for r in db.query(Friendship.addressee_id).filter(
            Friendship.requester_id == viewer_id, Friendship.status == "accepted",
        ).all()} | {r[0] for r in db.query(Friendship.requester_id).filter(
            Friendship.addressee_id == viewer_id, Friendship.status == "accepted",
        ).all()}

        viewer_family_ids = {r[0] for r in db.query(FamilyMember.family_id).filter(
            FamilyMember.user_id == viewer_id, FamilyMember.status == "accepted",
        ).all()}

        # 2. Warunki SQL
        conds = [
            Occasion.created_by_id == viewer_id,
            Occasion.recipient_id  == viewer_id,
            Occasion.visibility    == "public",
        ]
        if friend_ids:
            conds.append(and_(
                Occasion.visibility == "friends",
                or_(
                    Occasion.created_by_id.in_(friend_ids),
                    Occasion.recipient_id.in_(friend_ids),
                ),
            ))
        if viewer_family_ids:
            # Nowe okazje z konkretną rodziną
            conds.append(and_(
                Occasion.visibility == "family",
                Occasion.family_id.isnot(None),
                Occasion.family_id.in_(viewer_family_ids),
            ))

        base_q = db.query(Occasion).filter(or_(*conds))
        if upcoming_only:
            base_q = base_q.filter(
                Occasion.occasion_date >= datetime.now(timezone.utc).date()
            )
        sql_occasions = base_q.all()

        # 3. Stare okazje rodziny bez family_id — kompatybilność wsteczna
        if viewer_family_ids:
            family_member_ids = {r[0] for r in db.query(FamilyMember.user_id).filter(
                FamilyMember.family_id.in_(viewer_family_ids),
                FamilyMember.status == "accepted",
            ).all()}
            seen_ids = {o.id for o in sql_occasions}
            legacy_q = db.query(Occasion).filter(
                Occasion.visibility == "family",
                Occasion.family_id.is_(None),
                or_(
                    Occasion.created_by_id.in_(family_member_ids),
                    Occasion.recipient_id.in_(family_member_ids),
                ),
            )
            if upcoming_only:
                legacy_q = legacy_q.filter(
                    Occasion.occasion_date >= datetime.now(timezone.utc).date()
                )
            all_occasions = sql_occasions + [o for o in legacy_q.all()
                                             if o.id not in seen_ids]
        else:
            all_occasions = sql_occasions

        # 4. Sortowanie i paginacja w Pythonie (zbiory z dwóch zapytań)
        all_occasions.sort(key=lambda o: o.occasion_date)
        total = len(all_occasions)
        pages = max(1, (total + limit - 1) // limit)
        slice_ = all_occasions[(page - 1) * limit: page * limit]

        items = []
        for o in slice_:
            pledged = sum(len(i.pledges) for i in o.items)
            items.append(OccasionListItem(
                id=o.id,
                title=o.title,
                occasion_type=o.occasion_type,
                occasion_date=o.occasion_date,
                pledge_deadline=o.pledge_deadline,
                recipient=o.recipient,
                items_count=len(o.items),
                pledged_count=pledged,
            ))
        return PaginatedOccasions(items=items, total=total, page=page, pages=pages)

    @staticmethod
    def get(db: Session, occasion_id: str, viewer_id: str) -> OccasionResponse:
        occasion = db.get(Occasion, occasion_id)
        if not occasion:
            raise HTTPException(status_code=404, detail="Okazja nie istnieje")
        if not _can_see(db, occasion, viewer_id):
            raise HTTPException(status_code=403, detail="Brak dostepu do tej okazji")
        return OccasionService._to_response(occasion, viewer_id)

    @staticmethod
    def update(db: Session, occasion_id: str, data: OccasionUpdateRequest,
               user_id: str) -> OccasionResponse:
        occasion = db.get(Occasion, occasion_id)
        if not occasion:
            raise HTTPException(status_code=404, detail="Okazja nie istnieje")
        if occasion.created_by_id != user_id:
            raise HTTPException(status_code=403, detail="Tylko tworca moze edytowac okazje")
        # Edycja dozwolona tylko do dnia okazji (włącznie)
        if occasion.occasion_date < datetime.now(timezone.utc).date():
            raise HTTPException(status_code=409,
                                detail="Nie mozna edytowac okazji po jej dacie")

        for field, value in data.model_dump(exclude_none=True).items():
            setattr(occasion, field, value)
        db.commit()
        db.refresh(occasion)
        return OccasionService._to_response(occasion, user_id)

    @staticmethod
    def delete(db: Session, occasion_id: str, user_id: str) -> None:
        occasion = db.get(Occasion, occasion_id)
        if not occasion:
            raise HTTPException(status_code=404, detail="Okazja nie istnieje")
        if occasion.created_by_id != user_id:
            raise HTTPException(status_code=403, detail="Tylko tworca moze usunac okazje")
        has_pledges = any(len(i.pledges) > 0 for i in occasion.items)
        if has_pledges:
            raise HTTPException(status_code=409,
                                detail="Nie mozna usunac okazji z istniejacymi rezerwacjami")
        db.delete(occasion)
        db.commit()

    @staticmethod
    def _to_response(occasion: Occasion, viewer_id: str) -> OccasionResponse:
        return OccasionResponse(
            id=occasion.id,
            title=occasion.title,
            description=occasion.description,
            occasion_type=occasion.occasion_type,
            occasion_date=occasion.occasion_date,
            pledge_deadline=occasion.pledge_deadline,
            visibility=occasion.visibility,
            created_by=occasion.created_by,
            recipient=occasion.recipient,
            items=[_item_to_response(i, viewer_id, occasion.recipient_id)
                   for i in occasion.items],
            created_at=occasion.created_at,
        )


# ── Item CRUD ─────────────────────────────────────────────────────────────────

class ItemService:

    @staticmethod
    def _item_response(item: Item, viewer_id: str, recipient_id: str) -> ItemResponse:
        return _item_to_response(item, viewer_id, recipient_id)

    @staticmethod
    def create(db: Session, occasion_id: str, data: ItemCreateRequest,
               user_id: str) -> ItemResponse:
        occasion = db.get(Occasion, occasion_id)
        if not occasion:
            raise HTTPException(status_code=404, detail="Okazja nie istnieje")
        if user_id not in (occasion.recipient_id, occasion.created_by_id):
            raise HTTPException(status_code=403,
                                detail="Tylko obdarowywany lub tworca moze dodawac zyczenia")
        item = Item(occasion_id=occasion_id, **data.model_dump())
        db.add(item)
        db.commit()
        db.refresh(item)
        return _item_to_response(item, user_id, occasion.recipient_id)

    @staticmethod
    def update(db: Session, item_id: str, data: ItemUpdateRequest, user_id: str) -> ItemResponse:
        item = db.get(Item, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Przedmiot nie istnieje")
        occasion = item.occasion
        # Tylko twórca okazji może edytować życzenia
        if occasion.created_by_id != user_id:
            raise HTTPException(status_code=403,
                                detail="Tylko tworca okazji moze edytowac zyczenia")
        # Niedozwolone gdy ktokolwiek już zarezerwował
        if item.pledges:
            raise HTTPException(status_code=409,
                                detail="Zarezerwowane zyczenie nie moze byc edytowane")
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(item, field, value)
        db.commit()
        db.refresh(item)
        return _item_to_response(item, user_id, occasion.recipient_id)

    @staticmethod
    def delete(db: Session, item_id: str, user_id: str) -> None:
        item = db.get(Item, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Przedmiot nie istnieje")
        occasion = item.occasion
        # Tylko twórca okazji może usuwać życzenia
        if occasion.created_by_id != user_id:
            raise HTTPException(status_code=403,
                                detail="Tylko tworca okazji moze usuwac zyczenia")
        # Niedozwolone gdy ktokolwiek już zarezerwował
        if item.pledges:
            raise HTTPException(status_code=409,
                                detail="Zarezerwowane zyczenie nie moze byc usuniete")
        db.delete(item)
        db.commit()


# ── Pledge logic ──────────────────────────────────────────────────────────────

class PledgeService:

    @staticmethod
    def create(db: Session, item_id: str, data: PledgeCreateRequest,
               user_id: str) -> PledgeResponse:
        item = db.get(Item, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Przedmiot nie istnieje")
        occasion = item.occasion

        # Blokady biznesowe
        if user_id == occasion.recipient_id:
            raise HTTPException(status_code=403,
                                detail="Obdarowywany nie moze rezerwowac wlasnych zychen")
        now = datetime.now(timezone.utc)
        deadline = occasion.pledge_deadline
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        if now > deadline:
            raise HTTPException(status_code=403, detail="Termin zapisu minal")

        existing = db.query(Pledge).filter(
            Pledge.item_id == item_id, Pledge.user_id == user_id
        ).first()
        if existing:
            raise HTTPException(status_code=409, detail="Juz zarezerwowales(-as) ten przedmiot")

        # Blokada dla trybu single – jeden darczyńca, po pierwszej rezerwacji zamknięte
        if item.collection_mode == "single" and item.status != "available":
            raise HTTPException(status_code=409, detail="Przedmiot w pelni zarezerwowany")

        current_count = len(item.pledges)
        if item.max_pledges > 0 and current_count >= item.max_pledges:
            raise HTTPException(status_code=409, detail="Przedmiot w pelni zarezerwowany")

        pledge = Pledge(item_id=item_id, user_id=user_id, note=data.note)
        db.add(pledge)

        # Aktualizuj status itemu
        new_count = current_count + 1
        if item.collection_mode == "single" or \
                (item.max_pledges > 0 and new_count >= item.max_pledges):
            item.status = "reserved"

        db.commit()
        db.refresh(pledge)
        return PledgeResponse.model_validate(pledge)

    @staticmethod
    def delete(db: Session, item_id: str, user_id: str) -> None:
        pledge = db.query(Pledge).filter(
            Pledge.item_id == item_id, Pledge.user_id == user_id
        ).first()
        if not pledge:
            raise HTTPException(status_code=404, detail="Brak aktywnej rezerwacji")

        item = pledge.item
        occasion = item.occasion
        now = datetime.now(timezone.utc)
        deadline = occasion.pledge_deadline
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        if now > deadline:
            raise HTTPException(status_code=403,
                                detail="Termin minal – nie mozna wycofac rezerwacji")

        db.delete(pledge)
        item.status = "available"
        db.commit()
