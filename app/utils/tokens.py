import secrets
from datetime import datetime, timedelta, timezone

from app.config import settings


def generate_activation_token() -> tuple[str, datetime]:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(
        hours=settings.ACTIVATION_TOKEN_EXPIRE_HOURS
    )
    return token, expires


def generate_password_reset_token() -> tuple[str, datetime]:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(
        hours=settings.PASSWORD_RESET_TOKEN_EXPIRE_HOURS
    )
    return token, expires
