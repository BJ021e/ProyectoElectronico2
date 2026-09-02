from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from database import Base


if TYPE_CHECKING:
    from models.flight import Flight
    from models.route import Route


class FlightRouteAssignment(Base):
    __tablename__ = "flight_route_assignments"

    __table_args__ = (
        UniqueConstraint(
            "flight_id",
            name="uq_flight_route_assignment_flight"
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    flight_id: Mapped[int] = mapped_column(
        ForeignKey(
            "flights.id",
            ondelete="CASCADE"
        ),
        nullable=False,
        index=True
    )

    route_id: Mapped[int] = mapped_column(
        ForeignKey(
            "routes.id",
            ondelete="RESTRICT"
        ),
        nullable=False,
        index=True
    )

    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    flight: Mapped["Flight"] = relationship(
        "Flight"
    )

    route: Mapped["Route"] = relationship(
        "Route"
    )

    def __repr__(self) -> str:
        return (
            f"<FlightRouteAssignment "
            f"id={self.id} "
            f"flight_id={self.flight_id} "
            f"route_id={self.route_id}>"
        )