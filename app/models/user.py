import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    activation_token: Mapped[str | None] = mapped_column(String(100), nullable=True)
    activation_token_expires: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    password_reset_token: Mapped[str | None] = mapped_column(String(100), nullable=True)
    password_reset_expires: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relations
    occasions_created: Mapped[list["Occasion"]] = relationship(  # noqa: F821
        "Occasion", foreign_keys="Occasion.created_by_id", back_populates="created_by"
    )
    occasions_received: Mapped[list["Occasion"]] = relationship(  # noqa: F821
        "Occasion", foreign_keys="Occasion.recipient_id", back_populates="recipient"
    )
    pledges: Mapped[list["Pledge"]] = relationship("Pledge", back_populates="user")  # noqa: F821
    friendships_sent: Mapped[list["Friendship"]] = relationship(  # noqa: F821
        "Friendship", foreign_keys="Friendship.requester_id", back_populates="requester"
    )
    friendships_received: Mapped[list["Friendship"]] = relationship(  # noqa: F821
        "Friendship", foreign_keys="Friendship.addressee_id", back_populates="addressee"
    )
    family_memberships: Mapped[list["FamilyMember"]] = relationship(  # noqa: F821
        "FamilyMember", back_populates="user"
    )
    families_created: Mapped[list["Family"]] = relationship(  # noqa: F821
        "Family", back_populates="created_by"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email}>"
