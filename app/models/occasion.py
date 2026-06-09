import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Occasion(Base):
    __tablename__ = "occasions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    occasion_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="other"
    )  # birthday | name_day | christmas | anniversary | other
    occasion_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    pledge_deadline: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    visibility: Mapped[str] = mapped_column(
        String(20), nullable=False, default="friends"
    )  # public | friends | family
    reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    summary_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_by_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recipient_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    family_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("families.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relations
    created_by: Mapped["User"] = relationship(  # noqa: F821
        "User", foreign_keys=[created_by_id], back_populates="occasions_created"
    )
    recipient: Mapped["User"] = relationship(  # noqa: F821
        "User", foreign_keys=[recipient_id], back_populates="occasions_received"
    )
    family: Mapped["Family | None"] = relationship(  # noqa: F821
        "Family", foreign_keys=[family_id]
    )
    items: Mapped[list["Item"]] = relationship(  # noqa: F821
        "Item", back_populates="occasion", cascade="all, delete-orphan"
    )
