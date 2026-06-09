"""Konfiguracja logowania i monitoringu błędów (Sentry).

Sentry uruchamia się tylko, gdy ustawiono SENTRY_DSN — w dev domyślnie wyłączony.
Domyślnie nie wysyłamy danych osobowych (send_default_pii=False) ze względu na RODO.
"""
import logging

from app.config import settings

logger = logging.getLogger(__name__)


def configure_logging() -> None:
    """Spójny format logów aplikacji (czas, poziom, logger, treść)."""
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Wycisz zbyt gadatliwe loggery bibliotek
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("apscheduler.executors.default").setLevel(logging.WARNING)


def init_sentry() -> None:
    """Inicjalizuje Sentry, jeśli skonfigurowano DSN. Bezpieczne, gdy pakiet brak."""
    if not settings.SENTRY_DSN:
        logger.info("Sentry wyłączony (brak SENTRY_DSN).")
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.logging import LoggingIntegration
    except ImportError:
        logger.warning("sentry-sdk nie jest zainstalowany — monitoring błędów wyłączony.")
        return

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.APP_ENV,
        release=settings.APP_VERSION,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        # RODO: nie dołączaj domyślnie IP, ciasteczek ani danych użytkownika
        send_default_pii=False,
        # INFO+ jako breadcrumbs, ERROR+ jako zdarzenia (z tracebackiem gdy exc_info)
        integrations=[
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
    )
    logger.info("Sentry włączony (env=%s, release=%s).",
                settings.APP_ENV, settings.APP_VERSION)
