"""Strony HTML – renderowane przez Jinja2 po stronie serwera."""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.item import Item
from app.models.occasion import Occasion
from app.models.pledge import Pledge
from app.schemas.auth import LoginRequest, RegisterRequest
from app.schemas.item import ItemCreateRequest
from app.schemas.occasion import OccasionCreateRequest
from app.schemas.social import PledgeCreateRequest
from app.services.auth_service import AuthService
from app.services.occasion_service import ItemService, OccasionService, PledgeService
from app.utils.cookie_auth import get_user_from_cookie

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
        resp = RedirectResponse("/occasions", status_code=303)
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
    user = get_user_from_cookie(request, db)
    if not user:
        return HTMLResponse("", status_code=401)

    from app.models.user import User as UserModel
    from sqlalchemy import or_, func

    results = []
    query = q.strip()
    if len(query) >= 2:
        pattern = f"%{query}%"
        results = (
            db.query(UserModel)
            .filter(
                UserModel.is_active == True,  # noqa: E712
                UserModel.id != user.id,
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
    user = get_user_from_cookie(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)

    result = OccasionService.list_visible(db, user.id, upcoming_only=False, page=1, limit=50)
    return templates.TemplateResponse("occasions/list.html", {
        "request": request,
        "user": user,
        "occasions": result.items,
    })


@router.get("/occasions/new", response_class=HTMLResponse)
def occasions_new_page(request: Request, db: Session = Depends(get_db)):
    user = get_user_from_cookie(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse("occasions/create.html", {
        "request": request, "user": user, "error": None,
    })


@router.post("/occasions/new", response_class=HTMLResponse)
def occasions_new_post(
    request: Request,
    title: str = Form(...),
    occasion_type: str = Form("other"),
    occasion_date: str = Form(...),
    pledge_deadline: str = Form(...),
    visibility: str = Form("friends"),
    recipient_id: str = Form(...),
    description: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_user_from_cookie(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    try:
        deadline_date = date.fromisoformat(pledge_deadline)
        deadline_dt = datetime.combine(deadline_date, datetime.max.time().replace(microsecond=0))
        occ = OccasionService.create(db, OccasionCreateRequest(
            title=title,
            description=description or None,
            occasion_type=occasion_type,
            occasion_date=date.fromisoformat(occasion_date),
            pledge_deadline=deadline_dt,
            visibility=visibility,
            recipient_id=recipient_id,
        ), user.id)
        return RedirectResponse(f"/occasions/{occ.id}", status_code=303)
    except Exception as exc:
        detail = getattr(exc, "detail", str(exc))
        return templates.TemplateResponse("occasions/create.html", {
            "request": request, "user": user, "error": detail,
        }, status_code=400)


@router.get("/occasions/{occasion_id}", response_class=HTMLResponse)
def occasion_detail(occasion_id: str, request: Request, db: Session = Depends(get_db)):
    user = get_user_from_cookie(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
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

    my_pledges = {
        p.item_id for p in db.query(Pledge).filter(Pledge.user_id == user.id).all()
    }

    return templates.TemplateResponse("occasions/detail.html", {
        "request": request,
        "user": user,
        "occ": occ,
        "is_recipient": is_recipient,
        "is_creator": is_creator,
        "deadline_passed": deadline_passed,
        "my_pledges": my_pledges,
    })


# ── HTMX partials – items ─────────────────────────────────────────────────────

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
        item = ItemService.create(db, occasion_id, ItemCreateRequest(
            name=name, url=url or None, estimated_price=price,
        ), user.id)
        occ = OccasionService.get(db, occasion_id, user.id)
        is_recipient = occ.recipient.id == user.id
        return templates.TemplateResponse("partials/item_card.html", {
            "request": request, "item": item, "user": user,
            "is_recipient": is_recipient, "deadline_passed": False,
            "my_pledges": set(), "occasion_id": occasion_id,
        })
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
        item_obj = db.get(Item, item_id)
        occ = item_obj.occasion
        item = ItemService._item_response(item_obj, user.id, occ.recipient_id)
        return templates.TemplateResponse("partials/item_card.html", {
            "request": request, "item": item, "user": user,
            "is_recipient": user.id == occ.recipient_id,
            "deadline_passed": False,
            "my_pledges": {item_id},
            "occasion_id": occ.id,
        })
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
        item_obj = db.get(Item, item_id)
        occ = item_obj.occasion
        item = ItemService._item_response(item_obj, user.id, occ.recipient_id)
        return templates.TemplateResponse("partials/item_card.html", {
            "request": request, "item": item, "user": user,
            "is_recipient": user.id == occ.recipient_id,
            "deadline_passed": False,
            "my_pledges": set(),
            "occasion_id": occ.id,
        })
    except Exception as exc:
        detail = getattr(exc, "detail", str(exc))
        return HTMLResponse(f'<p class="text-red-500 text-sm">{detail}</p>', status_code=400)


# ── Profil ────────────────────────────────────────────────────────────────────

@router.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request, db: Session = Depends(get_db)):
    user = get_user_from_cookie(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse("profile/index.html", {"request": request, "user": user})
