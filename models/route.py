from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import (
    DateTime,
    Enum as SqlEnum,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.waypoint import Waypoint

class RouteStatus(str, PyEnum):
    DRAFT = "DRAFT"
    READY = "READY"
    ARCHIVED = "ARCHIVED"


class Route(Base):
    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    route_code: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True
    )

    name: Mapped[str] = mapped_column(
        String(120),
        nullable=False
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    status: Mapped[RouteStatus] = mapped_column(
        SqlEnum(
            RouteStatus,
            native_enum=False,
            length=20
        ),
        nullable=False,
        default=RouteStatus.DRAFT
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )
    
    waypoints: Mapped[list["Waypoint"]] = relationship(
    "Waypoint",
    back_populates="route",
    cascade="all, delete-orphan",
    order_by="Waypoint.sequence"
    )

    def __repr__(self) -> str:
        return (
            f"<Route "
            f"id={self.id} "
            f"code='{self.route_code}' "
            f"name='{self.name}' "
            f"status='{self.status.value}'>"
        )