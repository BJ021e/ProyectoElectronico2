from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


if TYPE_CHECKING:
    from models.route import Route


class Waypoint(Base):
    __tablename__ = "waypoints"

    __table_args__ = (
        UniqueConstraint(
            "route_id",
            "sequence",
            name="uq_waypoint_route_sequence"
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    route_id: Mapped[int] = mapped_column(
        ForeignKey(
            "routes.id",
            ondelete="CASCADE"
        ),
        nullable=False,
        index=True
    )

    sequence: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    latitude: Mapped[float] = mapped_column(
        Float,
        nullable=False
    )

    longitude: Mapped[float] = mapped_column(
        Float,
        nullable=False
    )

    altitude: Mapped[float | None] = mapped_column(
        Float,
        nullable=True
    )

    speed: Mapped[float | None] = mapped_column(
        Float,
        nullable=True
    )

    heading: Mapped[float | None] = mapped_column(
        Float,
        nullable=True
    )

    action: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    route: Mapped["Route"] = relationship(
        "Route",
        back_populates="waypoints"
    )

    def __repr__(self) -> str:
        return (
            f"<Waypoint "
            f"id={self.id} "
            f"route_id={self.route_id} "
            f"sequence={self.sequence} "
            f"lat={self.latitude} "
            f"lon={self.longitude}>"
        )