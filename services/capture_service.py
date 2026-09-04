from __future__ import annotations

from datetime import datetime
from math import isfinite

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload, selectinload

from database import SessionLocal
from models import (
    Campaign,
    CaptureStatus,
    ImageAsset,
    ImageBand,
    ImageCapture,
    SensorType,
)

from services.campaign_lifecycle import (
    CampaignLifecycleError,
    CampaignLifecyclePolicy,
)


class CapturePersistenceError(Exception):
    """
    Error producido durante una operación de persistencia
    relacionada con capturas.
    """
    pass


class InvalidCaptureError(Exception):
    """
    Error producido cuando una captura, banda o sus datos
    no cumplen las reglas de negocio.
    """
    pass


class CaptureService:

    MULTISPECTRAL_BANDS = (
        ImageBand.BLUE,
        ImageBand.GREEN,
        ImageBand.RED,
        ImageBand.NIR,
        ImageBand.RED_EDGE,
    )

    RGB_BANDS = (
        ImageBand.RGB,
    )

    @classmethod
    def _expected_bands(
        cls,
        sensor_type: SensorType,
    ) -> tuple[ImageBand, ...]:

        if sensor_type == SensorType.MULTISPECTRAL:
            return cls.MULTISPECTRAL_BANDS

        if sensor_type == SensorType.RGB:
            return cls.RGB_BANDS

        raise InvalidCaptureError(
            f"Tipo de sensor no soportado: {sensor_type}."
        )

    @staticmethod
    def _normalize_band(
        band: ImageBand | str,
    ) -> ImageBand:

        if isinstance(band, ImageBand):
            return band

        if not isinstance(band, str):
            raise InvalidCaptureError(
                "La banda suministrada no es válida."
            )

        normalized = (
            band.strip()
            .upper()
            .replace("-", "_")
            .replace(" ", "_")
        )

        try:
            return ImageBand(normalized)

        except ValueError as exc:
            raise InvalidCaptureError(
                f"Banda no válida: {band}."
            ) from exc

    @staticmethod
    def _normalize_coordinate(
        value: float | int | None,
        *,
        name: str,
        minimum: float | None = None,
        maximum: float | None = None,
    ) -> float | None:

        if value is None:
            return None

        if isinstance(value, bool):
            raise InvalidCaptureError(
                f"{name} no es válido."
            )

        try:
            normalized = float(value)

        except (TypeError, ValueError) as exc:
            raise InvalidCaptureError(
                f"{name} debe ser numérico."
            ) from exc

        if not isfinite(normalized):
            raise InvalidCaptureError(
                f"{name} debe ser finito."
            )

        if (
            minimum is not None
            and normalized < minimum
        ):
            raise InvalidCaptureError(
                f"{name} fuera de rango."
            )

        if (
            maximum is not None
            and normalized > maximum
        ):
            raise InvalidCaptureError(
                f"{name} fuera de rango."
            )

        return normalized

    @staticmethod
    def _get_capture_entity(
        session,
        capture_id: int,
    ) -> ImageCapture | None:

        statement = (
            select(ImageCapture)
            .options(
                selectinload(
                    ImageCapture.assets
                ),
                joinedload(
                    ImageCapture.campaign
                ),
            )
            .where(
                ImageCapture.id == capture_id
            )
        )

        return session.scalar(statement)

    @classmethod
    def _readiness(
        cls,
        *,
        sensor_type: SensorType,
        present_bands: set[ImageBand],
    ) -> dict:

        expected = cls._expected_bands(
            sensor_type
        )

        missing = [
            band
            for band in expected
            if band not in present_bands
        ]

        return {
            "is_complete": len(missing) == 0,
            "expected_bands": [
                band.value
                for band in expected
            ],
            "present_bands": [
                band.value
                for band in expected
                if band in present_bands
            ],
            "missing_bands": [
                band.value
                for band in missing
            ],
        }

    @classmethod
    def _serialize(
        cls,
        capture: ImageCapture,
    ) -> dict:

        sensor_type = (
            capture.campaign.sensor_type
        )

        expected = cls._expected_bands(
            sensor_type
        )

        band_order = {
            band: index
            for index, band in enumerate(
                expected
            )
        }

        assets = sorted(
            capture.assets,
            key=lambda asset: band_order.get(
                asset.band,
                999,
            ),
        )

        present_bands = {
            asset.band
            for asset in assets
        }

        return {
            "id": capture.id,
            "capture_code": capture.capture_code,
            "campaign_id": capture.campaign_id,
            "sequence": capture.sequence,
            "status": capture.status.value,
            "captured_at": (
                capture.captured_at.isoformat()
                if capture.captured_at
                else None
            ),
            "latitude": capture.latitude,
            "longitude": capture.longitude,
            "altitude": capture.altitude,
            "created_at": (
                capture.created_at.isoformat()
                if capture.created_at
                else None
            ),
            "sensor_type": sensor_type.value,
            "assets": [
                {
                    "id": asset.id,
                    "band": asset.band.value,
                    "original_filename": (
                        asset.original_filename
                    ),
                    "storage_path": (
                        asset.storage_path
                    ),
                    "remote_path": (
                        asset.remote_path
                    ),
                    "created_at": (
                        asset.created_at.isoformat()
                        if asset.created_at
                        else None
                    ),
                }
                for asset in assets
            ],
            "readiness": cls._readiness(
                sensor_type=sensor_type,
                present_bands=present_bands,
            ),
        }

    @classmethod
    def _synchronize_status(
        cls,
        session,
        capture: ImageCapture,
    ) -> None:

        statement = select(
            ImageAsset.band
        ).where(
            ImageAsset.capture_id
            == capture.id
        )

        present_bands = set(
            session.scalars(
                statement
            ).all()
        )

        readiness = cls._readiness(
            sensor_type=(
                capture.campaign.sensor_type
            ),
            present_bands=present_bands,
        )

        if capture.status != CaptureStatus.ERROR:
            capture.status = (
                CaptureStatus.READY
                if readiness["is_complete"]
                else CaptureStatus.CREATED
            )

    @classmethod
    def create_capture(
        cls,
        *,
        campaign_id: int,
        captured_at: datetime | None = None,
        latitude: float | int | None = None,
        longitude: float | int | None = None,
        altitude: float | int | None = None,
    ) -> dict:

        latitude = cls._normalize_coordinate(
            latitude,
            name="Latitud",
            minimum=-90.0,
            maximum=90.0,
        )

        longitude = cls._normalize_coordinate(
            longitude,
            name="Longitud",
            minimum=-180.0,
            maximum=180.0,
        )

        altitude = cls._normalize_coordinate(
            altitude,
            name="Altitud",
        )

        session = SessionLocal()

        try:
            campaign = session.get(
                Campaign,
                campaign_id,
            )

            if campaign is None:
                raise InvalidCaptureError(
                    f"La campaña con ID "
                    f"{campaign_id} no existe."
                )
            
            try:
                (
                    CampaignLifecyclePolicy
                    .assert_capture_mutation_allowed(
                        campaign
                    )
                )

            except CampaignLifecycleError as exc:
                raise InvalidCaptureError(
                    str(exc)
                ) from exc    

            statement = select(
                func.max(
                    ImageCapture.sequence
                )
            ).where(
                ImageCapture.campaign_id
                == campaign_id
            )

            last_sequence = (
                session.scalar(statement)
                or 0
            )

            sequence = (
                int(last_sequence) + 1
            )

            capture_code = (
                f"{campaign.campaign_code}"
                f"-CAP-{sequence:04d}"
            )

            capture = ImageCapture(
                capture_code=capture_code,
                campaign_id=campaign_id,
                sequence=sequence,
                status=CaptureStatus.CREATED,
                captured_at=captured_at,
                latitude=latitude,
                longitude=longitude,
                altitude=altitude,
            )

            session.add(capture)
            session.flush()
            
            (
                CampaignLifecyclePolicy
                .synchronize_capture_state(
                    session,
                    campaign,
                )
            )
            
            session.commit()

            capture = cls._get_capture_entity(
                session,
                capture.id,
            )

            return cls._serialize(
                capture
            )

        except InvalidCaptureError:
            session.rollback()
            raise

        except SQLAlchemyError as exc:
            session.rollback()

            raise CapturePersistenceError(
                "No fue posible crear "
                f"la captura: {exc}"
            ) from exc

        finally:
            session.close()

    @classmethod
    def add_asset(
        cls,
        *,
        capture_id: int,
        band: ImageBand | str,
        original_filename: str,
        storage_path: str,
        remote_path: str | None = None,
    ) -> dict:

        normalized_band = (
            cls._normalize_band(
                band
            )
        )

        if (
            not isinstance(
                original_filename,
                str,
            )
            or not original_filename.strip()
        ):
            raise InvalidCaptureError(
                "El nombre original del archivo es obligatorio."
            )

        if (
            not isinstance(
                storage_path,
                str,
            )
            or not storage_path.strip()
        ):
            raise InvalidCaptureError(
                "La ruta de almacenamiento es obligatoria."
            )

        session = SessionLocal()

        try:
            capture = cls._get_capture_entity(
                session,
                capture_id,
            )

            if capture is None:
                raise InvalidCaptureError(
                    f"La captura con ID "
                    f"{capture_id} no existe."
                )
            
            campaign = session.get(
                Campaign,
                capture.campaign_id,
            )

            if campaign is None:
                raise InvalidCaptureError(
                    "La campaña asociada "
                    "a la captura no existe."
                )

            try:
                (
                    CampaignLifecyclePolicy
                    .assert_capture_mutation_allowed(
                        campaign
                    )
                )

            except CampaignLifecycleError as exc:
                raise InvalidCaptureError(
                    str(exc)
                ) from exc
                
            expected_bands = (
                cls._expected_bands(
                    capture.campaign.sensor_type
                )
            )

            if normalized_band not in expected_bands:
                raise InvalidCaptureError(
                    f"La banda "
                    f"{normalized_band.value} "
                    "no es compatible con una "
                    f"campaña "
                    f"{capture.campaign.sensor_type.value}."
                )

            duplicate_statement = (
                select(ImageAsset)
                .where(
                    ImageAsset.capture_id
                    == capture_id,
                    ImageAsset.band
                    == normalized_band,
                )
            )

            if session.scalar(
                duplicate_statement
            ) is not None:
                raise InvalidCaptureError(
                    f"La captura {capture_id} "
                    "ya contiene la banda "
                    f"{normalized_band.value}."
                )

            asset = ImageAsset(
                capture_id=capture_id,
                band=normalized_band,
                original_filename=(
                    original_filename.strip()
                ),
                storage_path=(
                    storage_path.strip()
                ),
                remote_path=(
                    remote_path.strip()
                    if isinstance(
                        remote_path,
                        str,
                    )
                    and remote_path.strip()
                    else None
                ),
            )

            session.add(asset)

            session.flush()

            cls._synchronize_status(
                session,
                capture,
            )

            session.flush()

            (
                CampaignLifecyclePolicy
                .synchronize_capture_state(
                    session,
                    campaign,
                )
            )
            
            session.commit()

            capture = cls._get_capture_entity(
                session,
                capture_id,
            )

            return cls._serialize(
                capture
            )

        except InvalidCaptureError:
            session.rollback()
            raise

        except SQLAlchemyError as exc:
            session.rollback()

            raise CapturePersistenceError(
                "No fue posible registrar "
                f"la imagen: {exc}"
            ) from exc

        finally:
            session.close()

    @classmethod
    def validate_capture(
        cls,
        capture_id: int,
    ) -> dict:

        session = SessionLocal()

        try:
            capture = cls._get_capture_entity(
                session,
                capture_id,
            )

            if capture is None:
                raise InvalidCaptureError(
                    f"La captura con ID "
                    f"{capture_id} no existe."
                )

            cls._synchronize_status(
                session,
                capture,
            )

            session.commit()

            capture = cls._get_capture_entity(
                session,
                capture_id,
            )

            return cls._serialize(
                capture
            )

        except InvalidCaptureError:
            session.rollback()
            raise

        except SQLAlchemyError as exc:
            session.rollback()

            raise CapturePersistenceError(
                "No fue posible validar "
                f"la captura: {exc}"
            ) from exc

        finally:
            session.close()

    @classmethod
    def get_capture(
        cls,
        capture_id: int,
    ) -> dict | None:

        session = SessionLocal()

        try:
            capture = cls._get_capture_entity(
                session,
                capture_id,
            )

            if capture is None:
                return None

            return cls._serialize(
                capture
            )

        except SQLAlchemyError as exc:

            raise CapturePersistenceError(
                "No fue posible consultar "
                f"la captura: {exc}"
            ) from exc

        finally:
            session.close()

    @classmethod
    def list_captures(
        cls,
        campaign_id: int,
    ) -> list[dict]:

        session = SessionLocal()

        try:
            campaign = session.get(
                Campaign,
                campaign_id,
            )

            if campaign is None:
                raise InvalidCaptureError(
                    f"La campaña con ID "
                    f"{campaign_id} no existe."
                )

            statement = (
                select(ImageCapture)
                .options(
                    selectinload(
                        ImageCapture.assets
                    ),
                    joinedload(
                        ImageCapture.campaign
                    ),
                )
                .where(
                    ImageCapture.campaign_id
                    == campaign_id
                )
                .order_by(
                    ImageCapture.sequence
                )
            )

            captures = session.scalars(
                statement
            ).all()

            return [
                cls._serialize(capture)
                for capture in captures
            ]

        except InvalidCaptureError:
            raise

        except SQLAlchemyError as exc:

            raise CapturePersistenceError(
                "No fue posible listar "
                f"las capturas: {exc}"
            ) from exc

        finally:
            session.close()
            
    @classmethod
    def delete_capture(
        cls,
        capture_id: int,
    ) -> bool:
        """
        Elimina una captura y sus ImageAsset asociados.

        Se utiliza, entre otros casos, para revertir
        importaciones que no pudieron completarse.
        """

        session = SessionLocal()

        try:
            capture = session.get(
                ImageCapture,
                capture_id,
            )

            campaign = session.get(
                Campaign,
                capture.campaign_id,
            )

            if campaign is None:
                raise InvalidCaptureError(
                    "La campaña asociada a la captura no existe."
                )

            try:
                (
                    CampaignLifecyclePolicy
                    .assert_capture_mutation_allowed(
                        campaign
                    )
                )

            except CampaignLifecycleError as exc:
                raise InvalidCaptureError(
                    str(exc)
                ) from exc
                
            if capture is None:
                return False

            session.delete(
                capture
            )

            session.flush()

            (
                CampaignLifecyclePolicy
                .synchronize_capture_state(
                    session,
                    campaign,
                )
            )

            session.commit()

            return True

        except SQLAlchemyError as exc:
            session.rollback()

            raise CapturePersistenceError(
                "No fue posible eliminar "
                f"la captura: {exc}"
            ) from exc

        finally:
            session.close()