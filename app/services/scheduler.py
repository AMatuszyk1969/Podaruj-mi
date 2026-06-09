import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session, joinedload, selectinload

from app.config import settings
from app.database import SessionLocal
from app.models.item import Item
from app.models.occasion import Occasion
from app.models.user import User
from app.services.email_service import (
    send_deadline_reminder,
    send_occasion_closed_email,
    send_occasion_summary_email,
)
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

        # Świadomie tylko PRZED terminem (filtr >= now): po jego upływie rezerwacja
        # jest zamknięta, więc „zarezerwuj teraz” nie miałoby sensu. Powiadomienie
        # po terminie zapewnia osobny job podsumowujący (send_occasion_summaries).
        upcoming = db.query(Occasion).options(
            selectinload(Occasion.items).selectinload(Item.pledges)
        ).filter(
            Occasion.pledge_deadline >= now,
            Occasion.pledge_deadline <= window_end,
            Occasion.reminder_sent.is_(False),
        ).all()

        for occasion in upcoming:
            # Commit po każdej okazji – błąd jednej nie cofa już wysłanych powiadomień
            try:
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
                db.rollback()
                logger.error("Reminder failed for occasion %s: %s", occasion.id, exc,
                             exc_info=True)
    except Exception as exc:
        logger.error("Scheduler error: %s", exc, exc_info=True)
    finally:
        db.close()


async def send_occasion_summaries() -> None:
    """Po upływie terminu zapisów wysyła podsumowanie:
    - twórcy okazji (jeśli nie jest obdarowywanym) – liczbę zarezerwowanych prezentów,
    - obdarowywanemu – neutralną informację bez liczb (niespodzianka zachowana).
    Okno 7 dni chroni przed zaległą wysyłką dla bardzo starych okazji."""
    db: Session = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(days=7)

        passed = db.query(Occasion).options(
            selectinload(Occasion.items).selectinload(Item.pledges),
            joinedload(Occasion.created_by),
            joinedload(Occasion.recipient),
        ).filter(
            Occasion.pledge_deadline < now,
            Occasion.pledge_deadline >= window_start,
            Occasion.summary_sent.is_(False),
        ).all()

        for occasion in passed:
            # Commit po każdej okazji – izolacja błędów między okazjami
            try:
                total = len(occasion.items)
                reserved = sum(1 for item in occasion.items if item.pledges)
                url = f"{settings.FRONTEND_URL}/occasions/{occasion.id}"

                creator = occasion.created_by
                recipient = occasion.recipient

                # Szczegóły do twórcy – tylko gdy nie jest obdarowywanym (ochrona niespodzianki)
                if occasion.created_by_id != occasion.recipient_id and creator and creator.is_active:
                    await send_occasion_summary_email(
                        creator.email, creator.first_name, occasion.title, reserved, total, url
                    )
                    logger.info("Summary sent to creator %s for occasion %s",
                                creator.email, occasion.id)

                # Neutralnie do obdarowywanego
                if recipient and recipient.is_active:
                    await send_occasion_closed_email(
                        recipient.email, recipient.first_name, occasion.title
                    )

                occasion.summary_sent = True
                db.commit()
            except Exception as exc:
                db.rollback()
                logger.error("Summary failed for occasion %s: %s", occasion.id, exc,
                             exc_info=True)
    except Exception as exc:
        logger.error("Scheduler summary error: %s", exc, exc_info=True)
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
    scheduler.add_job(
        send_occasion_summaries,
        trigger="interval",
        hours=1,
        id="occasion_summaries",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown()
