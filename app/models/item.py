import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Item(Base):
    __tablename__ = "items"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    occasion_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("occasions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimated_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    collection_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="single"
    )  # single | multiple
    max_pledges: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="available"
    )  # available | reserved | bought
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relations
    occasion: Mapped["Occasion"] = relationship(  # noqa: F821
        "Occasion", back_populates="items"
    )
    pledges: Mapped[list["Pledge"]] = relationship(  # noqa: F821
        "Pledge", back_populates="item", cascade="all, delete-orphan"
    )
