import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Pledge(Base):
    __tablename__ = "pledges"
    __table_args__ = (
        UniqueConstraint("item_id", "user_id", name="uq_pledge_item_user"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relations
    item: Mapped["Item"] = relationship("Item", back_populates="pledges")  # noqa: F821
    user: Mapped["User"] = relationship("User", back_populates="pledges")  # noqa: F821
