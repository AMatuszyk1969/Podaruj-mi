from fastapi import Request
from jose import JWTError
from sqlalchemy.orm import Session

from app.models.user import User
from app.utils.security import decode_token


def get_user_from_cookie(request: Request, db: Session) -> User | None:
    """Czyta JWT z ciasteczka i zwraca użytkownika lub None."""
    token = request.cookies.get("pm_token")
    if not token:
        return None
    try:
        user_id = decode_token(token, expected_type="access")
        user = db.get(User, user_id)
        return user if user and user.is_active else None
    except (JWTError, Exception):
        return None


class _LoginRequired(Exception):
    """Wyrzucana gdy trasa wymaga zalogowania — obsługiwana przez handler w main.py."""
    pass


def require_user(request: Request, db: Session) -> User:
    """Zwraca zalogowanego użytkownika lub rzuca _LoginRequired (→ redirect /login).
    Użycie: user = require_user(request, db)
    Dla przyszłych tras zaleca się FastAPI Depends(require_html_user).
    """
    user = get_user_from_cookie(request, db)
    if not user:
        raise _LoginRequired()
    return user
