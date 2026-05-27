import logging
from pathlib import Path

from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType

from app.config import settings

logger = logging.getLogger(__name__)

_mail_config = ConnectionConfig(
    MAIL_USERNAME=settings.MAIL_USERNAME,
    MAIL_PASSWORD=settings.MAIL_PASSWORD,
    MAIL_FROM=settings.MAIL_FROM,
    MAIL_PORT=settings.MAIL_PORT,
    MAIL_SERVER=settings.MAIL_SERVER,
    MAIL_STARTTLS=settings.MAIL_STARTTLS,
    MAIL_SSL_TLS=settings.MAIL_SSL_TLS,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=not settings.is_development,
    TEMPLATE_FOLDER=Path(__file__).parent.parent / "templates" / "email",
)

_fm = FastMail(_mail_config)


async def send_activation_email(email: str, first_name: str, token: str) -> None:
    activation_url = f"{settings.FRONTEND_URL}/activate?token={token}"
    message = MessageSchema(
        subject=f"Aktywuj konto w {settings.APP_NAME}",
        recipients=[email],
        body=f"""Czesc {first_name}!

Kliknij ponizszy link, aby aktywowac konto (wazny 24h):
{activation_url}

Jesli nie rejestrowales(-as) sie w {settings.APP_NAME}, zignoruj ta wiadomosc.

Pozdrawiamy,
Zespol {settings.APP_NAME}
""",
        subtype=MessageType.plain,
    )
    try:
        await _fm.send_message(message)
    except Exception as exc:
        logger.error("Blad wysylki e-mail aktywacyjnego do %s: %s", email, exc)


async def send_password_reset_email(email: str, first_name: str, token: str) -> None:
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    message = MessageSchema(
        subject=f"Reset hasla w {settings.APP_NAME}",
        recipients=[email],
        body=f"""Czesc {first_name}!

Kliknij ponizszy link, aby zresetowac haslo (wazny 2h):
{reset_url}

Jesli nie prosiles(-as) o reset hasla, zignoruj ta wiadomosc.

Pozdrawiamy,
Zespol {settings.APP_NAME}
""",
        subtype=MessageType.plain,
    )
    try:
        await _fm.send_message(message)
    except Exception as exc:
        logger.error("Blad wysylki e-mail resetu hasla do %s: %s", email, exc)


async def send_deadline_reminder(email: str, first_name: str, occasion_title: str,
                                  occasion_url: str) -> None:
    message = MessageSchema(
        subject=f"Przypomnienie: jutro mija termin zapisu na okazje \"{occasion_title}\"",
        recipients=[email],
        body=f"""Czesc {first_name}!

Przypominamy, ze jutro mija termin zapisu na prezenty dla okazji:
\"{occasion_title}\"

Jeszcze nie zarezerwowales(-as) prezentu? Zrob to teraz:
{occasion_url}

Pozdrawiamy,
Zespol {settings.APP_NAME}
""",
        subtype=MessageType.plain,
    )
    try:
        await _fm.send_message(message)
    except Exception as exc:
        logger.error("Blad wysylki przypomnienia do %s: %s", email, exc)
