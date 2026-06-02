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


async def send_friend_invitation_email(
    recipient_email: str, recipient_name: str, inviter_name: str, app_url: str
) -> None:
    message = MessageSchema(
        subject=f"{inviter_name} zaprasza Cię do znajomych w {settings.APP_NAME}",
        recipients=[recipient_email],
        body=f"""Cześć {recipient_name}!

{inviter_name} wysłał(-a) Ci zaproszenie do znajomych w {settings.APP_NAME}.

Zaloguj się i zaakceptuj lub odrzuć zaproszenie:
{app_url}/social/friends

Pozdrawiamy,
Zespół {settings.APP_NAME}
""",
        subtype=MessageType.plain,
    )
    try:
        await _fm.send_message(message)
    except Exception as exc:
        logger.error("Błąd wysyłki zaproszenia do znajomych do %s: %s", recipient_email, exc)


async def send_family_invitation_email(
    recipient_email: str, recipient_name: str, inviter_name: str,
    family_name: str, app_url: str
) -> None:
    message = MessageSchema(
        subject=f'Zaproszenie do rodziny "{family_name}" w {settings.APP_NAME}',
        recipients=[recipient_email],
        body=f"""Cześć {recipient_name}!

{inviter_name} zaprasza Cie do grupy rodzinnej "{family_name}" w {settings.APP_NAME}.

Zaloguj się i dołącz do rodziny:
{app_url}/social/family

Pozdrawiamy,
Zespół {settings.APP_NAME}
""",
        subtype=MessageType.plain,
    )
    try:
        await _fm.send_message(message)
    except Exception as exc:
        logger.error("Błąd wysyłki zaproszenia do rodziny do %s: %s", recipient_email, exc)


async def send_platform_invitation_email(
    recipient_email: str, inviter_name: str, group_type: str,
    family_name: str | None, register_url: str,
) -> None:
    if group_type == "friend":
        group_desc = "do swoich Znajomych"
    else:
        group_desc = f'do grupy rodzinnej "{family_name}"'

    message = MessageSchema(
        subject=f"{inviter_name} zaprasza Cie do aplikacji Podaruj mi",
        recipients=[recipient_email],
        body=f"""Czesc!

{inviter_name} zaprasza Cie {group_desc} w aplikacji Podaruj mi.

Podaruj mi to platforma do koordynacji prezentow - tworzysz listy zyczen,
znajomi zapisuja sie co kupic, bez duplikatow i niespodzianek.

Zarejestruj sie i dolacz do grupy:
{register_url}

Zaproszenie jest wazne 7 dni. Po rejestracji zobaczysz je w zakladce
Zaproszenia i bedziesz mogl/mogla je zaakceptowac lub odrzucic.

Pozdrawiamy,
Zespol Podaruj mi
""",
        subtype=MessageType.plain,
    )
    try:
        await _fm.send_message(message)
    except Exception as exc:
        logger.error("Blad wysylki zaproszenia do platformy do %s: %s", recipient_email, exc)


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
