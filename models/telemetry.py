from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum as SqlEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

if TYPE_CHECKING:
    from models.flight import Flight


class TelemetrySource(str, PyEnum):
    RPI = "RPI"
    DJI = "DJI"
    UNKNOWN = "UNKNOWN"


class TelemetryPoint(Base):
    __tablename__ = "telemetry_points"

    __table_args__ = (
        Index(
            "ix_telemetry_flight_time",
            "flight_id",
            "recorded_at"
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
        nullable=False
    )

    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    latitude: Mapped[float | None] = mapped_column(
        Float,
        nullable=True
    )

    longitude: Mapped[float | None] = mapped_column(
        Float,
        nullable=True
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

    battery: Mapped[float | None] = mapped_column(
        Float,
        nullable=True
    )

    gps_sats: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True
    )

    flight_mode: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True
    )

    source: Mapped[TelemetrySource] = mapped_column(
        SqlEnum(
            TelemetrySource,
            native_enum=False,
            length=20
        ),
        nullable=False,
        default=TelemetrySource.UNKNOWN
    )

    flight: Mapped["Flight"] = relationship(
        "Flight",
        back_populates="telemetry_points"
    )

    def __repr__(self) -> str:
        return (
            f"<TelemetryPoint "
            f"id={self.id} "
            f"flight_id={self.flight_id} "
            f"lat={self.latitude} "
            f"lon={self.longitude}>"
        )