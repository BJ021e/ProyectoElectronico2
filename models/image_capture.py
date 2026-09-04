from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum as SqlEnum,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from database import Base


if TYPE_CHECKING:
    from models.campaign import Campaign
    from models.image_asset import ImageAsset


class CaptureStatus(str, PyEnum):
    CREATED = "CREATED"
    READY = "READY"
    ERROR = "ERROR"


class ImageCapture(Base):
    __tablename__ = "image_captures"

    __table_args__ = (
        UniqueConstraint(
            "campaign_id",
            "sequence",
            name="uq_image_capture_campaign_sequence",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    capture_code: Mapped[str] = mapped_column(
        String(70),
        unique=True,
        nullable=False,
        index=True,
    )

    campaign_id: Mapped[int] = mapped_column(
        ForeignKey(
            "campaigns.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    sequence: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    status: Mapped[CaptureStatus] = mapped_column(
        SqlEnum(
            CaptureStatus,
            native_enum=False,
            length=20,
        ),
        nullable=False,
        default=CaptureStatus.CREATED,
    )

    captured_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    latitude: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    longitude: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    altitude: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    campaign: Mapped["Campaign"] = relationship(
        "Campaign",
        back_populates="captures",
    )

    assets: Mapped[list["ImageAsset"]] = relationship(
        "ImageAsset",
        back_populates="capture",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<ImageCapture "
            f"id={self.id} "
            f"code='{self.capture_code}' "
            f"campaign_id={self.campaign_id} "
            f"sequence={self.sequence} "
            f"status='{self.status.value}'>"
        )