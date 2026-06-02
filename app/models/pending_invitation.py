import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PendingInvitation(Base):
    """Zaproszenie do platformy dla osoby, która nie ma jeszcze konta."""

    __tablename__ = "pending_invitations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    token: Mapped[str] = mapped_column(
        String(36), unique=True, nullable=False, index=True,
        default=lambda: str(uuid.uuid4()),
    )
    invited_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    inviter_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    group_type: Mapped[str] = mapped_column(String(20), nullable=False)  # "friend" | "family"
    family_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("families.id", ondelete="CASCADE"), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Relations
    inviter: Mapped["User"] = relationship("User", foreign_keys=[inviter_id])  # noqa: F821
    family: Mapped["Family | None"] = relationship("Family", foreign_keys=[family_id])  # noqa: F821
