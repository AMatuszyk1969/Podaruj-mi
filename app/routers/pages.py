"""Strony HTML – renderowane przez Jinja2 po stronie serwera."""
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import (
    APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, get_db

logger = logging.getLogger(__name__)
from app.models.family import FamilyMember
from app.models.item import Item
from app.models.occasion import Occasion
from app.models.pledge import Pledge
from app.schemas.auth import LoginRequest, RegisterRequest
from app.schemas.item import ItemCreateRequest, ItemUpdateRequest
from app.schemas.occasion import OccasionCreateRequest, OccasionUpdateRequest
from app.schemas.social import FamilyCreateRequest, PledgeCreateRequest
from app.models.pending_invitation import PendingInvitation
from app.services.auth_service import AuthService
from app.services.email_service import (
    send_added_to_occasion_email,
    send_family_invitation_email,
    send_friend_invitation_email,
    send_occasion_created_for_recipient_email,
    send_platform_invitation_email,
)
from app.utils.security import hash_password, verify_password
from app.services.occasion_service import (
    ItemService,
    OccasionService,
    PledgeService,
    occasion_audience_ids,
)
from app.services.social_service import FamilyService, FriendService
from app.utils.cookie_auth import get_user_from_cookie, require_user

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(include_in_schema=False)

COOKIE_MAX_AGE = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60


def _set_token_cookie(response, token: str):
    response.set_cookie(
        "pm_token", token,
        httponly=True,
        max_age=COOKIE_MAX_AGE,
        samesite="lax",
        secure=not settings.is_development,
    )


# ── Landing ───────────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
def landing(request: Request, db: Session = Depends(get_db)):
    user = get_user_from_cookie(request, db)
    if user:
        return RedirectResponse("/occasions", status_code=303)
    return templates.TemplateResponse("index.html", {"request": request})


# ── Strony prawne (publiczne) ──────────────────────────────────────────────────

@router.get("/regulamin", response_class=HTMLResponse)
def terms_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("legal/terms.html", {
        "request": request, "user": get_user_from_cookie(request, db),
    })


@router.get("/polityka-prywatnosci", response_class=HTMLResponse)
def privacy_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("legal/privacy.html", {
        "request": request, "user": get_user_from_cookie(request, db),
    })


# ── Auth ──────────────────────────────────────────────────────────────────────

@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    user = get_user_from_cookie(request, db)
    if user:
        return RedirectResponse("/occasions", status_code=303)
    return templates.TemplateResponse("auth/login.html", {"request": request, "error": None})


@router.post("/login", response_class=HTMLResponse)
def login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        token = AuthService.login(db, LoginRequest(email=email, password=password))
        # Sprawdź czy są oczekujące zaproszenia do platformy
        from app.models.user import User as UserModel
        logged_user = db.query(UserModel).filter(UserModel.email == email).first()
        has_pending = logged_user and db.query(PendingInvitation).filter(
            PendingInvitation.invited_email == logged_user.email
        ).first()
        redirect_url = "/invitations" if has_pending else "/occasions"
        resp = RedirectResponse(redirect_url, status_code=303)
        _set_token_cookie(resp, token.access_token)
        return resp
    except Exception:
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "error": "Nieprawidlowy e-mail lub haslo."},
            status_code=401,
        )


@router.get("/logout")
def logout():
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie("pm_token")
    return resp


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request, db: Session = Depends(get_db)):
    user = get_user_from_cookie(request, db)
    if user:
        return RedirectResponse("/occasions", status_code=303)
    return templates.TemplateResponse("auth/register.html", {"request": request, "error": None})


@router.post("/register", response_class=HTMLResponse)
async def register_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        await AuthService.register(
            db, RegisterRequest(email=email, password=password,
                                first_name=first_name, last_name=last_name)
        )
        return templates.TemplateResponse("auth/registered.html", {"request": request, "email": email})
    except Exception as exc:
        detail = getattr(exc, "detail", "Rejestracja nie powiodla sie.")
        return templates.TemplateResponse(
            "auth/register.html",
            {"request": request, "error": detail},
            status_code=400,
        )


@router.get("/activate", response_class=HTMLResponse)
def activate_page(request: Request, token: str = "", db: Session = Depends(get_db)):
    try:
        AuthService.activate(db, token)
        return templates.TemplateResponse("auth/activated.html", {"request": request, "success": True})
    except Exception:
        return templates.TemplateResponse("auth/activated.html", {"request": request, "success": False})


# ── Odzyskiwanie hasla ────────────────────────────────────────────────────────

@router.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_page(request: Request, db: Session = Depends(get_db)):
    user = get_user_from_cookie(request, db)
    if user:
        return RedirectResponse("/occasions", status_code=303)
    return templates.TemplateResponse("auth/forgot_password.html",
                                      {"request": request, "error": None, "email": ""})


@router.post("/forgot-password", response_class=HTMLResponse)
async def forgot_password_post(
    request: Request,
    email: str = Form(...),
    db: Session = Depends(get_db),
):
    await AuthService.forgot_password(db, email)
    return templates.TemplateResponse("auth/forgot_password_sent.html",
                                      {"request": request, "email": email})


@router.get("/reset-password", response_class=HTMLResponse)
def reset_password_page(request: Request, token: str = "", db: Session = Depends(get_db)):
    from app.models.user import User as UserModel
    user = db.query(UserModel).filter(UserModel.password_reset_token == token).first()
    token_invalid = not user or (
        user.password_reset_expires is not None and
        user.password_reset_expires.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc)
    )
    return templates.TemplateResponse("auth/reset_password.html", {
        "request": request,
        "token": token,
        "token_invalid": token_invalid,
        "error": None,
    })


@router.post("/reset-password", response_class=HTMLResponse)
def reset_password_post(
    request: Request,
    token: str = Form(...),
    new_password: str = Form(...),
    new_password2: str = Form(...),
    db: Session = Depends(get_db),
):
    from app.schemas.auth import PasswordResetConfirm
    if new_password != new_password2:
        return templates.TemplateResponse("auth/reset_password.html", {
            "request": request,
            "token": token,
            "token_invalid": False,
            "error": "Hasla nie sa identyczne.",
        }, status_code=400)
    try:
        AuthService.reset_password(db, PasswordResetConfirm(token=token, new_password=new_password))
        return templates.TemplateResponse("auth/reset_password_done.html", {"request": request})
    except Exception as exc:
        detail = getattr(exc, "detail", str(exc))
        token_invalid = "wygasl" in detail.lower() or "nieprawidlowy" in detail.lower()
        return templates.TemplateResponse("auth/reset_password.html", {
            "request": request,
            "token": token,
            "token_invalid": token_invalid,
            "error": detail if not token_invalid else None,
        }, status_code=400)


# ── Wyszukiwanie odbiorcy ─────────────────────────────────────────────────────

@router.get("/recipients/search", response_class=HTMLResponse)
def recipients_search(request: Request, q: str = "", db: Session = Depends(get_db)):
    """Wyszukiwanie ograniczone do znajomych i rodziny aktualnego użytkownika."""
    user = get_user_from_cookie(request, db)
    if not user:
        return HTMLResponse("", status_code=401)

    from app.models.user import User as UserModel
    from sqlalchemy import or_, func
    from app.services.occasion_service import (
        _accepted_friend_ids, _family_member_ids, _user_family_ids,
    )

    # Dozwolone ID: znajomi + członkowie wszystkich rodzin (wspólne helpery)
    friend_ids = _accepted_friend_ids(db, user.id)
    family_ids: set[str] = set()
    for fid in _user_family_ids(db, user.id):
        family_ids |= _family_member_ids(db, fid)
    family_ids.discard(user.id)

    allowed_ids = friend_ids | family_ids
    results = []
    query = q.strip()
    if len(query) >= 2 and allowed_ids:
        pattern = f"%{query}%"
        results = (
            db.query(UserModel)
            .filter(
                UserModel.is_active == True,  # noqa: E712
                UserModel.id.in_(allowed_ids),
                or_(
                    UserModel.email.ilike(pattern),
                    func.lower(
                        UserModel.first_name + " " + UserModel.last_name
                    ).contains(query.lower()),
                ),
            )
            .limit(8)
            .all()
        )

    return templates.TemplateResponse("partials/recipient_results.html", {
        "request": request,
        "users": results,
        "query": query,
    })


# ── Occasions ─────────────────────────────────────────────────────────────────

@router.get("/occasions", response_class=HTMLResponse)
def occasions_list(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)

    result = OccasionService.list_visible(db, user.id, upcoming_only=False, page=1, limit=50)
    today = datetime.now(timezone.utc).date()
    # Nadchodzące – data okazji jeszcze nie minęła (dziś włącznie), rosnąco
    upcoming = [o for o in result.items if o.occasion_date >= today]
    # Wykorzystane – data już przeszła, najnowsze na górze
    past = sorted(
        (o for o in result.items if o.occasion_date < today),
        key=lambda o: o.occasion_date, reverse=True,
    )
    return templates.TemplateResponse("occasions/list.html", {
        "request": request,
        "user": user,
        "upcoming": upcoming,
        "past": past,
    })


@router.get("/occasions/new", response_class=HTMLResponse)
def occasions_new_page(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)

    friends = FriendService.list_friends(db, user.id)

    # Zbierz członków ze WSZYSTKICH rodzin użytkownika, pogrupowane po nazwie rodziny.
    # Deduplikacja: pomiń siebie i osoby już widoczne jako znajomi.
    seen_ids = {user.id} | {f.id for f in friends}
    all_memberships = db.query(FamilyMember).filter(
        FamilyMember.user_id == user.id,
        FamilyMember.status == "accepted",
    ).all()
    family_groups = []  # lista (nazwa_rodziny, [User, ...])
    for m in all_memberships:
        fms = db.query(FamilyMember).filter(
            FamilyMember.family_id == m.family_id,
            FamilyMember.status == "accepted",
            FamilyMember.user_id.notin_(seen_ids),
        ).all()
        members = [fm.user for fm in fms]
        if members:
            family_groups.append((m.family.name, members))
            seen_ids.update(fm.user_id for fm in fms)

    # Lista (id, nazwa) wszystkich rodzin użytkownika do pickera widoczności
    user_families = [(m.family_id, m.family.name) for m in all_memberships]

    return templates.TemplateResponse("occasions/create.html", {
        "request": request, "user": user, "error": None,
        "friends": friends,
        "family_groups": family_groups,
        "user_families": user_families,
    })


async def _notify_new_occasion(occasion_id: str, base_url: str) -> None:
    """Powiadamia mailem obdarowywanego oraz wszystkie osoby dodane do okazji.
    Uruchamiane jako BackgroundTask – własna sesja DB (sesja requestu jest już zamknięta)."""
    from app.models.user import User as UserModel
    db = SessionLocal()
    try:
        occasion_obj = db.get(Occasion, occasion_id)
        if not occasion_obj:
            return
        occ_url = f"{base_url}/occasions/{occasion_obj.id}"
        recipient = occasion_obj.recipient
        recipient_name = f"{recipient.first_name} {recipient.last_name}"

        # Obdarowywany (jeśli to nie twórca) – „utworzono okazję dla Ciebie"
        if occasion_obj.recipient_id != occasion_obj.created_by_id:
            await send_occasion_created_for_recipient_email(
                recipient.email, recipient.first_name, occasion_obj.title, occ_url,
            )

        # Audytorium – osoby, które mogą rezerwować (bez twórcy i obdarowywanego)
        audience_ids = occasion_audience_ids(db, occasion_obj, include_creator=False)
        if audience_ids:
            users = db.query(UserModel).filter(
                UserModel.id.in_(audience_ids),
                UserModel.is_active == True,  # noqa: E712
            ).all()
            for u in users:
                await send_added_to_occasion_email(
                    u.email, u.first_name, occasion_obj.title, recipient_name, occ_url,
                )
    except Exception as exc:
        logger.warning("Powiadomienie o nowej okazji %s nie powiodlo sie: %s", occasion_id, exc)
    finally:
        db.close()


@router.post("/occasions/new", response_class=HTMLResponse)
async def occasions_new_post(
    request: Request,
    background_tasks: BackgroundTasks,
    title: str = Form(...),
    occasion_type: str = Form("other"),
    occasion_date: str = Form(...),
    pledge_deadline: str = Form(...),
    visibility: str = Form("friends"),
    recipient_id: str = Form(...),
    description: str = Form(""),
    family_id: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    try:
        occ_date = date.fromisoformat(occasion_date)
        deadline_date = date.fromisoformat(pledge_deadline)
        if deadline_date >= occ_date:
            raise HTTPException(status_code=400,
                                detail="Termin zapisów musi być wcześniejszy niż data okazji.")
        deadline_dt = datetime.combine(deadline_date, datetime.max.time().replace(microsecond=0))
        occ = OccasionService.create(db, OccasionCreateRequest(
            title=title,
            description=description or None,
            occasion_type=occasion_type,
            family_id=family_id if (visibility == "family" and family_id) else None,
            occasion_date=occ_date,
            pledge_deadline=deadline_dt,
            visibility=visibility,
            recipient_id=recipient_id,
        ), user.id)
        # Powiadomienia w tle – nie blokują redirectu na N wysyłek SMTP
        background_tasks.add_task(
            _notify_new_occasion, occ.id, str(request.base_url).rstrip("/")
        )
        return RedirectResponse(f"/occasions/{occ.id}", status_code=303)
    except Exception as exc:
        detail = getattr(exc, "detail", str(exc))
        return templates.TemplateResponse("occasions/create.html", {
            "request": request, "user": user, "error": detail,
        }, status_code=400)


@router.get("/occasions/{occasion_id}", response_class=HTMLResponse)
def occasion_detail(occasion_id: str, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    try:
        occ = OccasionService.get(db, occasion_id, user.id)
    except Exception:
        return RedirectResponse("/occasions", status_code=303)

    is_recipient = (occ.recipient.id == user.id)
    is_creator = (occ.created_by.id == user.id)
    now = datetime.now(timezone.utc)
    deadline_passed = (
        occ.pledge_deadline.replace(tzinfo=timezone.utc) < now
        if occ.pledge_deadline.tzinfo is None
        else occ.pledge_deadline < now
    )
    occasion_passed = occ.occasion_date < now.date()

    # Rezerwacje użytkownika ograniczone do tej okazji (nie wszystkie globalnie)
    my_pledges = {
        r[0] for r in db.query(Pledge.item_id).join(
            Item, Pledge.item_id == Item.id
        ).filter(
            Pledge.user_id == user.id, Item.occasion_id == occasion_id
        ).all()
    }

    return templates.TemplateResponse("occasions/detail.html", {
        "request": request,
        "user": user,
        "occ": occ,
        "is_recipient": is_recipient,
        "is_creator": is_creator,
        "deadline_passed": deadline_passed,
        "occasion_passed": occasion_passed,
        "my_pledges": my_pledges,
    })


@router.get("/occasions/{occasion_id}/edit", response_class=HTMLResponse)
def occasion_edit_page(occasion_id: str, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    occ = db.get(Occasion, occasion_id)
    if not occ or occ.created_by_id != user.id:
        return RedirectResponse(f"/occasions/{occasion_id}", status_code=303)
    if occ.occasion_date < datetime.now(timezone.utc).date():
        return RedirectResponse(f"/occasions/{occasion_id}", status_code=303)
    return templates.TemplateResponse("occasions/edit.html", {
        "request": request, "user": user, "occ": occ, "error": None,
    })


@router.post("/occasions/{occasion_id}/edit", response_class=HTMLResponse)
def occasion_edit_post(
    occasion_id: str,
    request: Request,
    title: str = Form(...),
    occasion_type: str = Form("other"),
    occasion_date: str = Form(...),
    pledge_deadline: str = Form(...),
    description: str = Form(""),
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    try:
        occ_date = date.fromisoformat(occasion_date)
        deadline_date = date.fromisoformat(pledge_deadline)
        if deadline_date >= occ_date:
            raise HTTPException(status_code=400,
                                detail="Termin zapisów musi być wcześniejszy niż data okazji.")
        deadline_dt = datetime.combine(deadline_date, datetime.max.time().replace(microsecond=0))
        OccasionService.update(db, occasion_id, OccasionUpdateRequest(
            title=title,
            description=description,
            occasion_type=occasion_type,
            occasion_date=occ_date,
            pledge_deadline=deadline_dt,
        ), user.id)
        return RedirectResponse(f"/occasions/{occasion_id}", status_code=303)
    except Exception as exc:
        detail = getattr(exc, "detail", str(exc))
        occ = db.get(Occasion, occasion_id)
        return templates.TemplateResponse("occasions/edit.html", {
            "request": request, "user": user, "occ": occ, "error": detail,
        }, status_code=400)


# ── HTMX partials – items ─────────────────────────────────────────────────────

def _render_item_card(request: Request, db: Session, item_obj, user) -> HTMLResponse:
    """Renderuje kartę życzenia z poprawnymi flagami uprawnień i terminów."""
    occ = item_obj.occasion
    item = ItemService._item_response(item_obj, user.id, occ.recipient_id)
    now = datetime.now(timezone.utc)
    deadline = occ.pledge_deadline
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    # Czy ten konkretny przedmiot jest zarezerwowany przez użytkownika (1 indeksowane zapytanie)
    has_pledge = db.query(Pledge.id).filter(
        Pledge.item_id == item_obj.id, Pledge.user_id == user.id
    ).first() is not None
    my_pledges = {item_obj.id} if has_pledge else set()
    return templates.TemplateResponse("partials/item_card.html", {
        "request": request, "item": item, "user": user,
        "is_recipient": user.id == occ.recipient_id,
        "is_creator": user.id == occ.created_by_id,
        "deadline_passed": deadline < now,
        "my_pledges": my_pledges,
        "occasion_id": occ.id,
    })


@router.post("/occasions/{occasion_id}/items", response_class=HTMLResponse)
def add_item(
    occasion_id: str,
    request: Request,
    name: str = Form(...),
    url: str = Form(""),
    estimated_price: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_user_from_cookie(request, db)
    if not user:
        return HTMLResponse('<p class="text-red-500">Brak autoryzacji</p>', status_code=401)
    try:
        price = float(estimated_price) if estimated_price else None
        created = ItemService.create(db, occasion_id, ItemCreateRequest(
            name=name, url=url or None, estimated_price=price,
        ), user.id)
        return _render_item_card(request, db, db.get(Item, created.id), user)
    except Exception as exc:
        detail = getattr(exc, "detail", str(exc))
        return HTMLResponse(f'<p class="text-red-500 text-sm">{detail}</p>', status_code=400)


@router.post("/items/{item_id}/pledge", response_class=HTMLResponse)
def pledge_item(item_id: str, request: Request, db: Session = Depends(get_db)):
    user = get_user_from_cookie(request, db)
    if not user:
        return HTMLResponse('<p class="text-red-500">Brak autoryzacji</p>', status_code=401)
    try:
        PledgeService.create(db, item_id, PledgeCreateRequest(), user.id)
        return _render_item_card(request, db, db.get(Item, item_id), user)
    except Exception as exc:
        detail = getattr(exc, "detail", str(exc))
        return HTMLResponse(f'<p class="text-red-500 text-sm">{detail}</p>', status_code=400)


@router.delete("/items/{item_id}/pledge", response_class=HTMLResponse)
def unpledge_item(item_id: str, request: Request, db: Session = Depends(get_db)):
    user = get_user_from_cookie(request, db)
    if not user:
        return HTMLResponse('<p class="text-red-500">Brak autoryzacji</p>', status_code=401)
    try:
        PledgeService.delete(db, item_id, user.id)
        return _render_item_card(request, db, db.get(Item, item_id), user)
    except Exception as exc:
        detail = getattr(exc, "detail", str(exc))
        return HTMLResponse(f'<p class="text-red-500 text-sm">{detail}</p>', status_code=400)


@router.get("/items/{item_id}/card", response_class=HTMLResponse)
def item_card(item_id: str, request: Request, db: Session = Depends(get_db)):
    """Zwraca normalną kartę życzenia (np. po anulowaniu edycji)."""
    user = get_user_from_cookie(request, db)
    if not user:
        return HTMLResponse('<p class="text-red-500">Brak autoryzacji</p>', status_code=401)
    item_obj = db.get(Item, item_id)
    if not item_obj:
        return HTMLResponse("", status_code=404)
    return _render_item_card(request, db, item_obj, user)


@router.get("/items/{item_id}/edit", response_class=HTMLResponse)
def item_edit_form(item_id: str, request: Request, db: Session = Depends(get_db)):
    """Zwraca formularz edycji życzenia (tylko twórca, gdy niezarezerwowane)."""
    user = get_user_from_cookie(request, db)
    if not user:
        return HTMLResponse('<p class="text-red-500">Brak autoryzacji</p>', status_code=401)
    item_obj = db.get(Item, item_id)
    if not item_obj:
        return HTMLResponse("", status_code=404)
    occ = item_obj.occasion
    # Brak uprawnień (twórca lub obdarowywany) lub już zarezerwowane → normalna karta
    if user.id not in (occ.created_by_id, occ.recipient_id) or item_obj.pledges:
        return _render_item_card(request, db, item_obj, user)
    return templates.TemplateResponse("partials/item_edit_form.html", {
        "request": request, "item": item_obj,
    })


@router.post("/items/{item_id}/edit", response_class=HTMLResponse)
def item_edit_post(
    item_id: str,
    request: Request,
    name: str = Form(...),
    url: str = Form(""),
    estimated_price: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_user_from_cookie(request, db)
    if not user:
        return HTMLResponse('<p class="text-red-500">Brak autoryzacji</p>', status_code=401)
    try:
        price = float(estimated_price) if estimated_price else None
        ItemService.update(db, item_id, ItemUpdateRequest(
            name=name, url=url or None, estimated_price=price,
        ), user.id)
        return _render_item_card(request, db, db.get(Item, item_id), user)
    except Exception as exc:
        detail = getattr(exc, "detail", str(exc))
        return HTMLResponse(f'<p class="text-red-500 text-sm">{detail}</p>', status_code=400)


@router.delete("/items/{item_id}", response_class=HTMLResponse)
def item_delete(item_id: str, request: Request, db: Session = Depends(get_db)):
    """Usuwa życzenie (tylko twórca, gdy niezarezerwowane). Zwraca pusty HTML → karta znika."""
    user = get_user_from_cookie(request, db)
    if not user:
        return HTMLResponse('<p class="text-red-500">Brak autoryzacji</p>', status_code=401)
    try:
        ItemService.delete(db, item_id, user.id)
        return HTMLResponse("")
    except Exception as exc:
        detail = getattr(exc, "detail", str(exc))
        return HTMLResponse(f'<p class="text-red-500 text-sm">{detail}</p>', status_code=400)


# ── Profil ────────────────────────────────────────────────────────────────────

@router.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    return templates.TemplateResponse("profile/index.html", {"request": request, "user": user})


# ── Znajomi ───────────────────────────────────────────────────────────────────

@router.get("/social/friends", response_class=HTMLResponse)
def friends_page(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)

    friends = FriendService.list_friends(db, user.id)
    all_invitations = FriendService.list_invitations(db, user.id)
    received = [i for i in all_invitations if i.addressee.id == user.id]
    sent     = [i for i in all_invitations if i.requester.id == user.id]

    return templates.TemplateResponse("social/friends.html", {
        "request": request,
        "user": user,
        "friends": friends,
        "received_invitations": received,
        "sent_invitations": sent,
    })


@router.post("/social/friends/invite", response_class=HTMLResponse)
async def friends_invite_post(
    request: Request,
    email: str = Form(...),
    db: Session = Depends(get_db),
):
    user = get_user_from_cookie(request, db)
    if not user:
        return HTMLResponse("", status_code=401)
    try:
        invitation = FriendService.invite(db, email, user.id)
        app_url = str(request.base_url).rstrip("/")
        await send_friend_invitation_email(
            recipient_email=invitation.addressee.email,
            recipient_name=invitation.addressee.first_name,
            inviter_name=f"{user.first_name} {user.last_name}",
            app_url=app_url,
        )
        return HTMLResponse('<p class="text-sm text-green-600 font-medium mt-1">✓ Zaproszenie wysłane!</p>')
    except HTTPException as exc:
        if exc.status_code == 404:
            return templates.TemplateResponse("partials/invite_confirm.html", {
                "request": request, "email": email,
                "group_type": "friend", "group_label": "Znajomi",
                "family_id": None, "target_id": "invite-result",
            })
        return HTMLResponse(f'<p class="text-sm text-red-500 mt-1">{exc.detail}</p>')
    except Exception as exc:
        detail = getattr(exc, "detail", str(exc))
        return HTMLResponse(f'<p class="text-sm text-red-500 mt-1">{detail}</p>')


@router.post("/social/friends/invitations/{invitation_id}/accept")
def friends_accept_post(invitation_id: str, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    try:
        FriendService.accept(db, invitation_id, user.id)
    except Exception:
        pass
    return RedirectResponse("/social/friends", status_code=303)


@router.post("/social/friends/invitations/{invitation_id}/reject")
def friends_reject_post(invitation_id: str, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    try:
        FriendService.reject(db, invitation_id, user.id)
    except Exception:
        pass
    return RedirectResponse("/social/friends", status_code=303)


@router.post("/social/friends/{friend_id}/remove")
def friends_remove_post(friend_id: str, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    try:
        FriendService.remove(db, friend_id, user.id)
    except Exception:
        pass
    return RedirectResponse("/social/friends", status_code=303)


# ── Rodzina ───────────────────────────────────────────────────────────────────

def _get_family_context(db: Session, user_id: str) -> dict:
    """Zwraca słownik ze wszystkimi rodzinami i oczekującymi zaproszeniami użytkownika."""
    memberships = db.query(FamilyMember).filter(
        FamilyMember.user_id == user_id,
        FamilyMember.status == "accepted",
    ).all()
    families = [m.family for m in memberships]

    pending_invitations = db.query(FamilyMember).filter(
        FamilyMember.user_id == user_id,
        FamilyMember.status == "pending",
    ).all()
    return {"families": families, "pending_invitations": pending_invitations}


@router.get("/social/family", response_class=HTMLResponse)
def family_page(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    ctx = _get_family_context(db, user.id)
    return templates.TemplateResponse("social/family.html", {
        "request": request, "user": user, "error": None, **ctx,
    })


@router.post("/social/family/create")
def family_create_post(
    request: Request,
    name: str = Form(...),
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    try:
        FamilyService.create(db, FamilyCreateRequest(name=name), user.id)
        return RedirectResponse("/social/family", status_code=303)
    except Exception as exc:
        detail = getattr(exc, "detail", str(exc))
        ctx = _get_family_context(db, user.id)
        return templates.TemplateResponse("social/family.html", {
            "request": request, "user": user, "error": detail, **ctx,
        }, status_code=400)


@router.post("/social/family/invite", response_class=HTMLResponse)
async def family_invite_post(
    request: Request,
    email: str = Form(...),
    family_id: str = Form(...),
    db: Session = Depends(get_db),
):
    user = get_user_from_cookie(request, db)
    if not user:
        return HTMLResponse("", status_code=401)
    membership = db.query(FamilyMember).filter(
        FamilyMember.user_id == user.id,
        FamilyMember.family_id == family_id,
        FamilyMember.status == "accepted",
    ).first()
    if not membership:
        return HTMLResponse('<p class="text-sm text-red-500 mt-1">Brak dostępu do tej grupy rodzinnej.</p>')
    target_id = f"family-invite-result-{family_id}"
    from app.models.user import User as UserModel
    try:
        FamilyService.invite(db, family_id, email, user.id)
        invitee = db.query(UserModel).filter(UserModel.email == email).first()
        if invitee:
            app_url = str(request.base_url).rstrip("/")
            await send_family_invitation_email(
                recipient_email=invitee.email,
                recipient_name=invitee.first_name,
                inviter_name=f"{user.first_name} {user.last_name}",
                family_name=membership.family.name,
                app_url=app_url,
            )
        return HTMLResponse('<p class="text-sm text-green-600 font-medium mt-1">✓ Zaproszenie wysłane!</p>')
    except HTTPException as exc:
        if exc.status_code == 404:
            return templates.TemplateResponse("partials/invite_confirm.html", {
                "request": request, "email": email,
                "group_type": "family",
                "group_label": f'Rodzina "{membership.family.name}"',
                "family_id": family_id,
                "target_id": target_id,
            })
        return HTMLResponse(f'<p class="text-sm text-red-500 mt-1">{exc.detail}</p>')
    except Exception as exc:
        detail = getattr(exc, "detail", str(exc))
        return HTMLResponse(f'<p class="text-sm text-red-500 mt-1">{detail}</p>')


@router.post("/social/family/accept/{member_id}")
def family_accept_post(member_id: str, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    try:
        member = db.get(FamilyMember, member_id)
        if member:
            FamilyService.accept_membership(db, member.family_id, member_id, user.id)
    except Exception:
        pass
    return RedirectResponse("/social/family", status_code=303)


# ── Zaproszenia do platformy (dla niezarejestrowanych) ───────────────────────

@router.post("/social/invite-platform", response_class=HTMLResponse)
async def invite_platform_post(
    request: Request,
    email: str = Form(...),
    group_type: str = Form(...),
    family_id: str = Form(default=""),
    target_id: str = Form(default="invite-result"),
    db: Session = Depends(get_db),
):
    user = get_user_from_cookie(request, db)
    if not user:
        return HTMLResponse("", status_code=401)

    # Walidacja group_type — tylko dozwolone wartości
    if group_type not in ("friend", "family"):
        return HTMLResponse('<p class="text-sm text-red-500 mt-1">Nieprawidłowy typ grupy.</p>')

    # Sprawdź czy zaproszenie już zostało wysłane (i czy nie wygasło)
    existing = db.query(PendingInvitation).filter(
        PendingInvitation.invited_email == email,
        PendingInvitation.inviter_id == user.id,
        PendingInvitation.group_type == group_type,
    ).first()
    if existing and existing.expires_at.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc):
        return HTMLResponse(
            '<p class="text-sm text-amber-600 mt-1">Zaproszenie zostało już wysłane. Oczekuje na rejestrację.</p>'
        )
    # Jeśli istnieje ale wygasło – usuń i wyślij nowe
    if existing:
        db.delete(existing)
        db.flush()

    # Pobierz dane rodziny jeśli potrzeba
    family_obj = None
    if group_type == "family":
        if not family_id:
            return HTMLResponse('<p class="text-sm text-red-500 mt-1">Nie podano grupy rodzinnej.</p>')
        membership = db.query(FamilyMember).filter(
            FamilyMember.user_id == user.id,
            FamilyMember.family_id == family_id,
            FamilyMember.status == "accepted",
        ).first()
        if not membership:
            return HTMLResponse('<p class="text-sm text-red-500 mt-1">Brak dostępu do tej grupy rodzinnej.</p>')
        family_obj = membership.family

    # Utwórz rekord zaproszenia
    inv = PendingInvitation(
        invited_email=email,
        inviter_id=user.id,
        group_type=group_type,
        family_id=family_id or None,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(inv)
    db.commit()

    # Wyślij e-mail
    base_url = str(request.base_url).rstrip("/")
    await send_platform_invitation_email(
        recipient_email=email,
        inviter_name=f"{user.first_name} {user.last_name}",
        group_type=group_type,
        family_name=family_obj.name if family_obj else None,
        register_url=f"{base_url}/register",
    )
    return HTMLResponse('<p class="text-sm text-green-600 font-medium mt-1">✓ Zaproszenie do platformy zostało wysłane!</p>')


@router.get("/invitations", response_class=HTMLResponse)
def invitations_page(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    invitations = db.query(PendingInvitation).filter(
        PendingInvitation.invited_email == user.email,
        PendingInvitation.expires_at > datetime.now(timezone.utc),
    ).all()
    return templates.TemplateResponse("social/invitations.html", {
        "request": request, "user": user, "invitations": invitations,
    })


@router.post("/invitations/{inv_id}/accept")
def invitation_accept(inv_id: str, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)

    inv = db.get(PendingInvitation, inv_id)
    now = datetime.now(timezone.utc)
    if not inv or inv.invited_email != user.email:
        return RedirectResponse("/invitations", status_code=303)
    # Odrzuć wygasłe zaproszenia
    if inv.expires_at.replace(tzinfo=timezone.utc) < now:
        db.delete(inv)
        db.commit()
        return RedirectResponse("/invitations", status_code=303)

    try:
        if inv.group_type == "friend":
            # Używamy serwisu — chroni przed self-friendship i duplikatami
            FriendService.create_accepted(db, inv.inviter_id, user.id)

        elif inv.group_type == "family" and inv.family_id:
            exists = db.query(FamilyMember).filter(
                FamilyMember.family_id == inv.family_id,
                FamilyMember.user_id == user.id,
            ).first()
            if not exists:
                db.add(FamilyMember(
                    family_id=inv.family_id, user_id=user.id,
                    status="accepted",
                    joined_at=datetime.now(timezone.utc),
                ))

        db.delete(inv)
        db.commit()
    except Exception:
        db.rollback()

    remaining = db.query(PendingInvitation).filter(
        PendingInvitation.invited_email == user.email
    ).count()
    return RedirectResponse("/invitations" if remaining else "/occasions", status_code=303)


@router.post("/invitations/{inv_id}/decline")
def invitation_decline(inv_id: str, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    inv = db.get(PendingInvitation, inv_id)
    if inv and inv.invited_email == user.email:
        db.delete(inv)
        db.commit()
    remaining = db.query(PendingInvitation).filter(
        PendingInvitation.invited_email == user.email
    ).count()
    return RedirectResponse("/invitations" if remaining else "/occasions", status_code=303)


@router.post("/social/family/reject/{member_id}")
def family_reject_post(member_id: str, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    try:
        member = db.get(FamilyMember, member_id)
        if member and member.user_id == user.id:
            db.delete(member)
            db.commit()
    except Exception:
        pass
    return RedirectResponse("/social/family", status_code=303)


# ── Edycja profilu ────────────────────────────────────────────────────────────

@router.get("/profile/edit", response_class=HTMLResponse)
def profile_edit_page(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    return templates.TemplateResponse("profile/edit.html", {
        "request": request, "user": user,
    })


@router.post("/profile/edit/name", response_class=HTMLResponse)
def profile_edit_name(
    request: Request,
    first_name: str = Form(...),
    last_name: str = Form(...),
    db: Session = Depends(get_db),
):
    user = get_user_from_cookie(request, db)
    if not user:
        return HTMLResponse("", status_code=401)
    first_name = first_name.strip()
    last_name = last_name.strip()
    if not first_name or not last_name:
        return HTMLResponse('<p class="text-sm text-red-500">Imię i nazwisko nie mogą być puste.</p>')
    user.first_name = first_name
    user.last_name = last_name
    db.commit()
    return HTMLResponse('<p class="text-sm text-green-600 font-medium">✓ Dane zostały zapisane.</p>')


@router.post("/profile/edit/password", response_class=HTMLResponse)
def profile_edit_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = get_user_from_cookie(request, db)
    if not user:
        return HTMLResponse("", status_code=401)
    if not verify_password(current_password, user.hashed_password):
        return HTMLResponse('<p class="text-sm text-red-500">Nieprawidłowe aktualne hasło.</p>')
    if new_password != confirm_password:
        return HTMLResponse('<p class="text-sm text-red-500">Nowe hasła nie są identyczne.</p>')
    if len(new_password) < 8:
        return HTMLResponse('<p class="text-sm text-red-500">Hasło musi mieć minimum 8 znaków.</p>')
    user.hashed_password = hash_password(new_password)
    db.commit()
    return HTMLResponse('<p class="text-sm text-green-600 font-medium">✓ Hasło zostało zmienione.</p>')


@router.post("/profile/edit/avatar")
async def profile_edit_avatar(
    request: Request,
    avatar: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    from app.services.storage_service import delete_avatar, detect_image_type, save_avatar
    user = require_user(request, db)

    content = await avatar.read()
    if len(content) > 2 * 1024 * 1024:
        return templates.TemplateResponse("profile/edit.html", {
            "request": request, "user": user,
            "avatar_error": "Plik za duży (max 2 MB).",
        })

    img_type = detect_image_type(content)
    if img_type not in ("jpeg", "png", "gif", "webp"):
        return templates.TemplateResponse("profile/edit.html", {
            "request": request, "user": user,
            "avatar_error": "Dozwolone formaty: JPG, PNG, WebP, GIF.",
        })

    old_avatar = user.avatar_url
    try:
        new_url = await save_avatar(content, img_type, str(request.base_url))
    except Exception as exc:
        logger.warning("Upload avatara nie powiodl sie: %s", exc)
        return templates.TemplateResponse("profile/edit.html", {
            "request": request, "user": user,
            "avatar_error": "Nie udało się zapisać zdjęcia. Spróbuj ponownie.",
        }, status_code=502)

    user.avatar_url = new_url
    db.commit()
    await delete_avatar(old_avatar)  # sprzątanie starego pliku (best-effort)
    return RedirectResponse("/profile/edit", status_code=303)


@router.post("/profile/delete")
async def profile_delete(
    request: Request,
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    """Trwałe usunięcie konta (RODO). Kaskada DB czyści wszystkie powiązane dane."""
    from sqlalchemy import text
    from app.services.storage_service import delete_avatar
    user = require_user(request, db)

    if not verify_password(password, user.hashed_password):
        return templates.TemplateResponse("profile/edit.html", {
            "request": request, "user": user,
            "delete_error": "Nieprawidłowe hasło — konto nie zostało usunięte.",
        }, status_code=400)

    avatar_url = user.avatar_url
    # ON DELETE CASCADE czyści okazje, życzenia, rezerwacje, znajomości,
    # rodziny (utworzone przez użytkownika) i zaproszenia.
    db.execute(text("DELETE FROM users WHERE id = :id"), {"id": user.id})
    db.commit()
    await delete_avatar(avatar_url)

    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie("pm_token")
    return resp
