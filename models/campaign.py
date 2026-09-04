from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from database import Base


if TYPE_CHECKING:
    from models.flight import Flight
    from models.image_capture import ImageCapture

class CampaignStatus(str, PyEnum):
    CREATED = "CREATED"
    CAPTURING = "CAPTURING"
    READY = "READY"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"
    ARCHIVED = "ARCHIVED"


class SensorType(str, PyEnum):
    MULTISPECTRAL = "MULTISPECTRAL"
    RGB = "RGB"


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    campaign_code: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    status: Mapped[CampaignStatus] = mapped_column(
        SqlEnum(
            CampaignStatus,
            native_enum=False,
            length=20,
        ),
        nullable=False,
        default=CampaignStatus.CREATED,
    )

    sensor_type: Mapped[SensorType] = mapped_column(
        SqlEnum(
            SensorType,
            native_enum=False,
            length=20,
        ),
        nullable=False,
    )

    sensor_model: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
    )

    flight_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "flights.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    acquired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    flight: Mapped["Flight | None"] = relationship(
        "Flight",
        back_populates="campaigns",
    )
    
    captures: Mapped[list["ImageCapture"]] = relationship(
        "ImageCapture",
        back_populates="campaign",
        cascade="all, delete-orphan",
        order_by="ImageCapture.sequence",
    )

    def __repr__(self) -> str:
        return (
            f"<Campaign "
            f"id={self.id} "
            f"code='{self.campaign_code}' "
            f"name='{self.name}' "
            f"status='{self.status.value}' "
            f"sensor='{self.sensor_type.value}'>"
        )