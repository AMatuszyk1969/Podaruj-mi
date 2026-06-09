import html
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


# ── Szablon HTML maili (kolorystyka i styl jak aplikacja webowa) ──────────────

_BRAND = "#1A569E"   # brand-700
_BRAND_50 = "#EDF3FB"
_INK = "#111827"     # gray-900
_BODY = "#4b5563"    # gray-600
_MUTED = "#9ca3af"   # gray-400


def _esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


def _p(content: str) -> str:
    return (f'<p style="margin:0 0 14px; font-size:15px; line-height:1.6; '
            f'color:{_BODY};">{content}</p>')


def _note(content: str) -> str:
    return (f'<p style="margin:18px 0 0; font-size:13px; line-height:1.5; '
            f'color:{_MUTED};">{content}</p>')


def _button(label: str, url: str) -> str:
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" '
        'style="margin:22px 0 6px;"><tr>'
        f'<td style="border-radius:12px; background-color:{_BRAND};">'
        f'<a href="{url}" target="_blank" style="display:inline-block; '
        'padding:12px 26px; font-size:15px; font-weight:600; color:#ffffff; '
        f'text-decoration:none; border-radius:12px;">{_esc(label)}</a>'
        '</td></tr></table>'
    )


def _highlight(content: str) -> str:
    """Kafelek z wyróżnieniem (np. tytuł okazji), w kolorystyce brand."""
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="margin:4px 0 16px; background-color:{_BRAND_50}; '
        f'border-radius:12px;"><tr><td style="padding:14px 16px; font-size:15px; '
        f'font-weight:600; color:{_BRAND};">{content}</td></tr></table>'
    )


def _layout(heading: str, body_html: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="pl">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
</head>
<body style="margin:0; padding:0; background-color:#f3f4f6;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
    style="background-color:#f3f4f6; padding:24px 12px;">
    <tr><td align="center">
      <table role="presentation" width="480" cellpadding="0" cellspacing="0"
        style="max-width:480px; width:100%; background-color:#ffffff; border-radius:16px;
        overflow:hidden; border:1px solid #e5e7eb;">
        <tr><td style="background-color:{_BRAND}; padding:20px 28px;">
          <span style="color:#ffffff; font-size:20px; font-weight:700;
            letter-spacing:-0.3px;">&#127873; Podaruj mi</span>
        </td></tr>
        <tr><td style="padding:28px;">
          <h1 style="margin:0 0 16px; font-size:20px; font-weight:700; color:{_INK};">{heading}</h1>
          {body_html}
        </td></tr>
        <tr><td style="padding:18px 28px; border-top:1px solid #f3f4f6; background-color:#fafafa;">
          <p style="margin:0; font-size:13px; color:{_MUTED};">Pozdrawiamy,<br/>Zespół {_esc(settings.APP_NAME)}</p>
        </td></tr>
      </table>
      <p style="margin:14px 0 0; font-size:12px; color:{_MUTED};">
        Wiadomość wysłana automatycznie z platformy {_esc(settings.APP_NAME)}.
      </p>
    </td></tr>
  </table>
</body>
</html>"""


async def _send_html(email: str, subject: str, heading: str, body_html: str,
                     error_label: str) -> None:
    message = MessageSchema(
        subject=subject,
        recipients=[email],
        body=_layout(heading, body_html),
        subtype=MessageType.html,
    )
    try:
        await _fm.send_message(message)
    except Exception as exc:
        logger.error("Blad wysylki %s do %s: %s", error_label, email, exc)


# ── Konta ──────────────────────────────────────────────────────────────────────

async def send_activation_email(email: str, first_name: str, token: str) -> None:
    activation_url = f"{settings.FRONTEND_URL}/activate?token={token}"
    body = (
        _p(f"Cześć {_esc(first_name)}!")
        + _p("Dziękujemy za rejestrację. Kliknij przycisk poniżej, aby aktywować konto "
             "<strong>(link ważny 24 godziny)</strong>.")
        + _button("Aktywuj konto", activation_url)
        + _note(f"Jeśli to nie Ty zakładałeś(-aś) konto w {_esc(settings.APP_NAME)}, "
                "po prostu zignoruj tę wiadomość.")
    )
    await _send_html(email, f"Aktywuj konto w {settings.APP_NAME}",
                     "Witaj w Podaruj mi! 🎁", body, "e-mail aktywacyjny")


async def send_password_reset_email(email: str, first_name: str, token: str) -> None:
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    body = (
        _p(f"Cześć {_esc(first_name)}!")
        + _p("Otrzymaliśmy prośbę o zresetowanie hasła. Kliknij przycisk poniżej, aby "
             "ustawić nowe hasło <strong>(link ważny 2 godziny)</strong>.")
        + _button("Ustaw nowe hasło", reset_url)
        + _note("Jeśli nie prosiłeś(-aś) o reset hasła, zignoruj tę wiadomość — "
                "Twoje hasło pozostanie bez zmian.")
    )
    await _send_html(email, f"Reset hasła w {settings.APP_NAME}",
                     "Reset hasła", body, "e-mail resetu hasla")


# ── Społeczność ────────────────────────────────────────────────────────────────

async def send_friend_invitation_email(
    recipient_email: str, recipient_name: str, inviter_name: str, app_url: str
) -> None:
    body = (
        _p(f"Cześć {_esc(recipient_name)}!")
        + _p(f"<strong>{_esc(inviter_name)}</strong> wysłał(-a) Ci zaproszenie do grona "
             "znajomych w Podaruj mi.")
        + _button("Zobacz zaproszenie", f"{app_url}/social/friends")
    )
    await _send_html(recipient_email,
                     f"{inviter_name} zaprasza Cię do znajomych w {settings.APP_NAME}",
                     "Nowe zaproszenie do znajomych 👋", body, "zaproszenia do znajomych")


async def send_family_invitation_email(
    recipient_email: str, recipient_name: str, inviter_name: str,
    family_name: str, app_url: str
) -> None:
    body = (
        _p(f"Cześć {_esc(recipient_name)}!")
        + _p(f"<strong>{_esc(inviter_name)}</strong> zaprasza Cię do grupy rodzinnej:")
        + _highlight(f"👨‍👩‍👧 {_esc(family_name)}")
        + _button("Dołącz do rodziny", f"{app_url}/social/family")
    )
    await _send_html(recipient_email,
                     f'Zaproszenie do rodziny "{family_name}" w {settings.APP_NAME}',
                     "Zaproszenie do rodziny 👨‍👩‍👧", body, "zaproszenia do rodziny")


async def send_platform_invitation_email(
    recipient_email: str, inviter_name: str, group_type: str,
    family_name: str | None, register_url: str,
) -> None:
    if group_type == "friend":
        group_desc = "do grona swoich <strong>Znajomych</strong>"
    else:
        group_desc = f'do grupy rodzinnej <strong>"{_esc(family_name)}"</strong>'
    body = (
        _p("Cześć!")
        + _p(f"<strong>{_esc(inviter_name)}</strong> zaprasza Cię {group_desc} "
             "w aplikacji Podaruj mi.")
        + _p("Podaruj mi to platforma do koordynacji prezentów — tworzysz listy życzeń, "
             "a bliscy zapisują się, co kupić: bez duplikatów i bez psucia niespodzianki.")
        + _button("Zarejestruj się i dołącz", register_url)
        + _note("Zaproszenie jest ważne 7 dni. Po rejestracji znajdziesz je w zakładce "
                "„Zaproszenia” i zdecydujesz, czy dołączyć.")
    )
    await _send_html(recipient_email,
                     f"{inviter_name} zaprasza Cię do aplikacji {settings.APP_NAME}",
                     "Zaproszenie do Podaruj mi 🎁", body, "zaproszenia do platformy")


# ── Okazje ─────────────────────────────────────────────────────────────────────

async def send_occasion_created_for_recipient_email(
    email: str, first_name: str, occasion_title: str, occasion_url: str
) -> None:
    body = (
        _p(f"Cześć {_esc(first_name)}!")
        + _p("W Podaruj mi utworzono okazję dla Ciebie:")
        + _highlight(f"🎁 {_esc(occasion_title)}")
        + _p("Dodaj swoją listę życzeń, aby bliscy wiedzieli, co sprawi Ci radość.")
        + _button("Dodaj listę życzeń", occasion_url)
    )
    await _send_html(email, f'Utworzono okazję dla Ciebie: "{occasion_title}"',
                     "Nowa okazja dla Ciebie 🎉", body, "powiadomienia o okazji")


async def send_added_to_occasion_email(
    email: str, first_name: str, occasion_title: str,
    recipient_name: str, occasion_url: str
) -> None:
    body = (
        _p(f"Cześć {_esc(first_name)}!")
        + _p("Zostałeś(-aś) dodany(-a) do nowej okazji:")
        + _highlight(f"🎁 {_esc(occasion_title)}<br/>"
                     f'<span style="font-weight:400; color:{_BODY};">dla: '
                     f"{_esc(recipient_name)}</span>")
        + _p("Zajrzyj na listę życzeń i zarezerwuj prezent, zanim zrobią to inni.")
        + _button("Zobacz okazję", occasion_url)
    )
    await _send_html(email, f'Nowa okazja: "{occasion_title}" - możesz wybrać prezent',
                     "Dodano Cię do nowej okazji 🎁", body, "powiadomienia o dodaniu do okazji")


async def send_deadline_reminder(email: str, first_name: str, occasion_title: str,
                                  occasion_url: str) -> None:
    body = (
        _p(f"Cześć {_esc(first_name)}!")
        + _p("Przypominamy, że <strong>jutro mija termin</strong> wyboru prezentów dla okazji:")
        + _highlight(f"⏰ {_esc(occasion_title)}")
        + _p("Jeszcze nie zarezerwowałeś(-aś) prezentu? Zrób to teraz.")
        + _button("Zarezerwuj prezent", occasion_url)
    )
    await _send_html(email, f'Przypomnienie: jutro mija termin zapisu na okazję "{occasion_title}"',
                     "Termin zapisów dobiega końca ⏰", body, "przypomnienia")


async def send_occasion_summary_email(
    email: str, first_name: str, occasion_title: str,
    reserved: int, total: int, occasion_url: str
) -> None:
    """Podsumowanie po upływie terminu – do twórcy okazji (zawiera liczby rezerwacji)."""
    body = (
        _p(f"Cześć {_esc(first_name)}!")
        + _p(f'Termin wyboru prezentów dla okazji <strong>"{_esc(occasion_title)}"</strong> '
             "właśnie minął.")
        + _highlight(f"✅ Zarezerwowano {reserved} z {total} prezentów z listy życzeń")
        + _button("Zobacz szczegóły", occasion_url)
    )
    await _send_html(email, f'Podsumowanie okazji: "{occasion_title}"',
                     "Okazja zakończona 🎁", body, "podsumowania okazji")


async def send_occasion_closed_email(
    email: str, first_name: str, occasion_title: str
) -> None:
    """Neutralne powiadomienie po upływie terminu – do obdarowywanego (bez liczb,
    żeby nie psuć niespodzianki)."""
    body = (
        _p(f"Cześć {_esc(first_name)}!")
        + _p(f'Termin, w którym bliscy mogli wybierać prezenty dla okazji '
             f'<strong>"{_esc(occasion_title)}"</strong>, właśnie minął.')
        + _p("Wkrótce poznasz swoje prezenty! 🎉")
    )
    await _send_html(email, f'Termin wyboru prezentów minął: "{occasion_title}"',
                     "Niespodzianka już blisko 🎉", body, "powiadomienia o zamknieciu okazji")
