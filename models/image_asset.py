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
    UniqueConstraint,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from database import Base


if TYPE_CHECKING:
    from models.image_capture import ImageCapture


class ImageBand(str, PyEnum):
    BLUE = "BLUE"
    GREEN = "GREEN"
    RED = "RED"
    NIR = "NIR"
    RED_EDGE = "RED_EDGE"
    RGB = "RGB"


class ImageAsset(Base):
    __tablename__ = "image_assets"

    __table_args__ = (
        UniqueConstraint(
            "capture_id",
            "band",
            name="uq_image_asset_capture_band",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    capture_id: Mapped[int] = mapped_column(
        ForeignKey(
            "image_captures.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    band: Mapped[ImageBand] = mapped_column(
        SqlEnum(
            ImageBand,
            native_enum=False,
            length=20,
        ),
        nullable=False,
    )

    original_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    storage_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    remote_path: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    capture: Mapped["ImageCapture"] = relationship(
        "ImageCapture",
        back_populates="assets",
    )

    def __repr__(self) -> str:
        return (
            f"<ImageAsset "
            f"id={self.id} "
            f"capture_id={self.capture_id} "
            f"band='{self.band.value}' "
            f"filename='{self.original_filename}'>"
        )