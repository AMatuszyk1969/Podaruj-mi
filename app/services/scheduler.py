import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.occasion import Occasion
from app.models.pledge import Pledge
from app.services.email_service import send_deadline_reminder

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")


async def send_deadline_reminders() -> None:
    """Wysyla przypomnienia uzytkownikow, ktorzy jeszcze nie zarezerwowali prezentu
    na okazje, ktorych deadline jest za mniej niz 24h."""
    db: Session = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        window_end = now + timedelta(hours=24)

        upcoming = db.query(Occasion).filter(
            Occasion.pledge_deadline >= now,
            Occasion.pledge_deadline <= window_end,
            Occasion.reminder_sent.is_(False),
        ).all()

        for occasion in upcoming:
            # Zbierz uzytkownikow, ktorzy moga obdarowywac (widza okazje)
            # Uproszczenie MVP: wysylamy do twörcy i do "visible" users
            # Pelna implementacja wymagalaby iteracji po znajomych/rodzinie
            pledging_users = {p.user_id for item in occasion.items for p in item.pledges}

            # Kandydaci do przypomnienia: tutaj uproszczone do twórcy okazji
            # W pełnej wersji: wszyscy uprawnieni widzowie minus obdarowywany minus ci co już zapisani
            candidates = [occasion.created_by] if occasion.created_by_id not in pledging_users \
                else []

            for user in candidates:
                occasion_url = f"{__import__('app.config', fromlist=['settings']).settings.FRONTEND_URL}" \
                               f"/occasions/{occasion.id}"
                await send_deadline_reminder(
                    user.email, user.first_name, occasion.title, occasion_url
                )
                logger.info("Reminder sent to %s for occasion %s", user.email, occasion.id)

            occasion.reminder_sent = True

        db.commit()
    except Exception as exc:
        logger.error("Scheduler error: %s", exc)
    finally:
        db.close()


def start_scheduler() -> None:
    scheduler.add_job(
        send_deadline_reminders,
        trigger="interval",
        hours=1,
        id="deadline_reminders",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown()
