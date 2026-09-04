from __future__ import annotations

from enum import Enum as PyEnum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.telemetry import TelemetryPoint
    from models.campaign import Campaign

class FlightStatus(str, PyEnum):
    CREATED = "CREATED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"
    
class Flight(Base):
    __tablename__ = "flights"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    flight_code: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True
    )

    name: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True
    )

    status: Mapped[FlightStatus] = mapped_column(
        Enum(
            FlightStatus,
            native_enum=False,
            length=20
        ),
        nullable=False,
        default=FlightStatus.CREATED
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    telemetry_points: Mapped[list["TelemetryPoint"]] = relationship(
        "TelemetryPoint",
        back_populates="flight",
        cascade="all, delete-orphan"
    )
    
    campaigns: Mapped[list["Campaign"]] = relationship(
        "Campaign",
        back_populates="flight",
    )
    
    def __repr__(self) -> str:
        return (
            f"<Flight "
            f"id={self.id} "
            f"code='{self.flight_code}' "
            f"status='{self.status.value}'>"
        )