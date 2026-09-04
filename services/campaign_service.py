from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from database import SessionLocal
from models import (
    Campaign,
    CampaignStatus,
    Flight,
    SensorType,
)


class CampaignPersistenceError(Exception):
    """
    Error producido durante una operación de persistencia
    relacionada con campañas.
    """
    pass


class InvalidCampaignError(Exception):
    """
    Error producido cuando los datos suministrados para una
    campaña no son válidos.
    """
    pass


class CampaignService:

    @staticmethod
    def _serialize(campaign: Campaign) -> dict:
        return {
            "id": campaign.id,
            "campaign_code": campaign.campaign_code,
            "name": campaign.name,
            "description": campaign.description,
            "status": campaign.status.value,
            "sensor_type": campaign.sensor_type.value,
            "sensor_model": campaign.sensor_model,
            "flight_id": campaign.flight_id,
            "acquired_at": (
                campaign.acquired_at.isoformat()
                if campaign.acquired_at
                else None
            ),
            "created_at": (
                campaign.created_at.isoformat()
                if campaign.created_at
                else None
            ),
            "updated_at": (
                campaign.updated_at.isoformat()
                if campaign.updated_at
                else None
            ),
            "notes": campaign.notes,
        }

    @staticmethod
    def _normalize_sensor_type(
        sensor_type: SensorType | str
    ) -> SensorType:

        if isinstance(sensor_type, SensorType):
            return sensor_type

        if not isinstance(sensor_type, str):
            raise InvalidCampaignError(
                "El tipo de sensor debe ser MULTISPECTRAL o RGB."
            )

        try:
            return SensorType(sensor_type.strip().upper())

        except ValueError as exc:
            raise InvalidCampaignError(
                f"Tipo de sensor no válido: {sensor_type}."
            ) from exc

    @staticmethod
    def _get_campaign_entity(
        session,
        campaign_id: int,
    ) -> Campaign | None:

        statement = select(Campaign).where(
            Campaign.id == campaign_id
        )

        return session.scalar(statement)

    @classmethod
    def create_campaign(
        cls,
        *,
        name: str,
        sensor_type: SensorType | str,
        sensor_model: str | None = None,
        flight_id: int | None = None,
        acquired_at: datetime | None = None,
        description: str | None = None,
        notes: str | None = None,
    ) -> dict:

        if not isinstance(name, str) or not name.strip():
            raise InvalidCampaignError(
                "El nombre de la campaña es obligatorio."
            )

        normalized_sensor_type = cls._normalize_sensor_type(
            sensor_type
        )

        session = SessionLocal()

        try:
            if flight_id is not None:

                flight = session.get(
                    Flight,
                    flight_id,
                )

                if flight is None:
                    raise InvalidCampaignError(
                        f"El vuelo con ID {flight_id} no existe."
                    )

            provisional_code = (
                f"TEMP-{uuid4().hex}"
            )

            campaign = Campaign(
                campaign_code=provisional_code,
                name=name.strip(),
                description=(
                    description.strip()
                    if isinstance(description, str)
                    and description.strip()
                    else None
                ),
                status=CampaignStatus.CREATED,
                sensor_type=normalized_sensor_type,
                sensor_model=(
                    sensor_model.strip()
                    if isinstance(sensor_model, str)
                    and sensor_model.strip()
                    else None
                ),
                flight_id=flight_id,
                acquired_at=acquired_at,
                notes=(
                    notes.strip()
                    if isinstance(notes, str)
                    and notes.strip()
                    else None
                ),
            )

            session.add(campaign)

            session.flush()

            today = datetime.now(
                timezone.utc
            ).strftime(
                "%Y%m%d"
            )

            campaign.campaign_code = (
                f"CP-{today}-{campaign.id:04d}"
            )

            session.commit()

            session.refresh(campaign)

            return cls._serialize(
                campaign
            )

        except InvalidCampaignError:
            session.rollback()
            raise

        except SQLAlchemyError as exc:
            session.rollback()

            raise CampaignPersistenceError(
                "No fue posible crear la campaña: "
                f"{exc}"
            ) from exc

        finally:
            session.close()

    @classmethod
    def get_campaign(
        cls,
        campaign_id: int,
    ) -> dict | None:

        session = SessionLocal()

        try:
            campaign = cls._get_campaign_entity(
                session,
                campaign_id,
            )

            if campaign is None:
                return None

            return cls._serialize(
                campaign
            )

        except SQLAlchemyError as exc:

            raise CampaignPersistenceError(
                "No fue posible consultar la campaña: "
                f"{exc}"
            ) from exc

        finally:
            session.close()

    @classmethod
    def list_campaigns(
        cls,
        limit: int = 50,
    ) -> list[dict]:

        session = SessionLocal()

        try:
            limit = max(
                1,
                min(limit, 500),
            )

            statement = (
                select(Campaign)
                .order_by(
                    Campaign.id.desc()
                )
                .limit(limit)
            )

            campaigns = session.scalars(
                statement
            ).all()

            return [
                cls._serialize(campaign)
                for campaign in campaigns
            ]

        except SQLAlchemyError as exc:

            raise CampaignPersistenceError(
                "No fue posible listar las campañas: "
                f"{exc}"
            ) from exc

        finally:
            session.close()