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
    from models.campaign import Campaign
    from models.geospatial_product import GeospatialProduct


class ProcessingJobStatus(str, PyEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    job_code: Mapped[str] = mapped_column(
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

    backend: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    status: Mapped[ProcessingJobStatus] = mapped_column(
        SqlEnum(
            ProcessingJobStatus,
            native_enum=False,
            length=20,
        ),
        nullable=False,
        default=ProcessingJobStatus.PENDING,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    campaign: Mapped["Campaign"] = relationship(
        "Campaign",
        back_populates="processing_jobs",
    )

    products: Mapped[list["GeospatialProduct"]] = relationship(
        "GeospatialProduct",
        back_populates="processing_job",
    )

    def __repr__(self) -> str:
        return (
            f"<ProcessingJob "
            f"id={self.id} "
            f"code='{self.job_code}' "
            f"campaign_id={self.campaign_id} "
            f"backend='{self.backend}' "
            f"status='{self.status.value}'>"
        )