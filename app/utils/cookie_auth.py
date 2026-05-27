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
