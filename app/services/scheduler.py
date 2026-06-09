import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.occasion import Occasion
from app.models.user import User
from app.services.email_service import send_deadline_reminder
from app.services.occasion_service import occasion_audience_ids

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")


async def send_deadline_reminders() -> None:
    """Powiadamia wszystkie osoby związane z okazją (które mogą rezerwować, a jeszcze
    tego nie zrobiły), że termin zapisów mija za mniej niż 24h."""
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
            # Osoby, które już zarezerwowały – nie przypominamy im
            pledging_users = {p.user_id for item in occasion.items for p in item.pledges}

            # Pełne audytorium uprawnione do rezerwacji, minus już zapisani
            audience_ids = occasion_audience_ids(db, occasion, include_creator=True)
            to_remind = audience_ids - pledging_users

            if to_remind:
                users = db.query(User).filter(
                    User.id.in_(to_remind), User.is_active.is_(True)
                ).all()
                occasion_url = f"{settings.FRONTEND_URL}/occasions/{occasion.id}"
                for user in users:
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
