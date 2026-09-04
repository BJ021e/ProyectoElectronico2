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
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from database import Base


if TYPE_CHECKING:
    from models.campaign import Campaign
    from models.processing_job import ProcessingJob


class GeospatialProductType(str, PyEnum):
    ORTHOMOSAIC_RGB = "ORTHOMOSAIC_RGB"
    ORTHOMOSAIC_MULTISPECTRAL = "ORTHOMOSAIC_MULTISPECTRAL"

    ORTHOMOSAIC_BLUE = "ORTHOMOSAIC_BLUE"
    ORTHOMOSAIC_GREEN = "ORTHOMOSAIC_GREEN"
    ORTHOMOSAIC_RED = "ORTHOMOSAIC_RED"
    ORTHOMOSAIC_NIR = "ORTHOMOSAIC_NIR"
    ORTHOMOSAIC_RED_EDGE = "ORTHOMOSAIC_RED_EDGE"

    DSM = "DSM"
    DTM = "DTM"

    NDVI = "NDVI"
    NDRE = "NDRE"
    GNDVI = "GNDVI"
    SAVI = "SAVI"


class GeospatialProduct(Base):
    __tablename__ = "geospatial_products"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    product_code: Mapped[str] = mapped_column(
        String(80),
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

    processing_job_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "processing_jobs.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    product_type: Mapped[GeospatialProductType] = mapped_column(
        SqlEnum(
            GeospatialProductType,
            native_enum=False,
            length=40,
        ),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    storage_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    crs: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    epsg: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    width: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    height: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    band_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    resolution_x: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    resolution_y: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    bounds_left: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    bounds_bottom: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    bounds_right: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    bounds_top: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    wgs84_left: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    wgs84_bottom: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    wgs84_right: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    wgs84_top: Mapped[float | None] = mapped_column(
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
        back_populates="geospatial_products",
    )

    processing_job: Mapped["ProcessingJob | None"] = relationship(
        "ProcessingJob",
        back_populates="products",
    )

    def __repr__(self) -> str:
        return (
            f"<GeospatialProduct "
            f"id={self.id} "
            f"code='{self.product_code}' "
            f"type='{self.product_type.value}' "
            f"campaign_id={self.campaign_id}>"
        )