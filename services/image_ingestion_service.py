from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

import cv2
import rasterio

from config import Config
from models import ImageBand
from services.campaign_service import CampaignService
from services.capture_service import (
    CaptureService,
    InvalidCaptureError,
)


class ImageIngestionError(Exception):
    """
    Error producido durante la incorporación física
    de una imagen al almacenamiento administrado.
    """
    pass


class InvalidImageFileError(ImageIngestionError):
    """
    El archivo suministrado no existe, tiene un formato
    incompatible o no puede ser leído como imagen.
    """
    pass


class ImageIngestionService:

    MULTISPECTRAL_EXTENSIONS = {
        ".tif",
        ".tiff",
    }

    RGB_EXTENSIONS = {
        ".jpg",
        ".jpeg",
        ".png",
        ".tif",
        ".tiff",
    }

    @staticmethod
    def _normalize_band(
        band: ImageBand | str,
    ) -> ImageBand:

        if isinstance(band, ImageBand):
            return band

        if not isinstance(band, str):
            raise InvalidImageFileError(
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
            raise InvalidImageFileError(
                f"Banda no válida: {band}."
            ) from exc

    @staticmethod
    def _storage_root() -> Path:

        configured = Path(
            Config.CAMPAIGN_STORAGE_ROOT
        )

        if configured.is_absolute():
            return configured

        project_root = Path(
            __file__
        ).resolve().parents[1]

        return (
            project_root
            / configured
        ).resolve()

    @staticmethod
    def _validate_file_exists(
        source_path: Path,
    ) -> None:

        if not source_path.exists():
            raise InvalidImageFileError(
                f"El archivo no existe: "
                f"{source_path}"
            )

        if not source_path.is_file():
            raise InvalidImageFileError(
                f"La ruta no corresponde "
                f"a un archivo: {source_path}"
            )

        if source_path.stat().st_size <= 0:
            raise InvalidImageFileError(
                "El archivo está vacío."
            )

    @classmethod
    def _validate_extension(
        cls,
        *,
        source_path: Path,
        band: ImageBand,
    ) -> str:

        suffix = (
            source_path.suffix
            .lower()
        )

        allowed = (
            cls.RGB_EXTENSIONS
            if band == ImageBand.RGB
            else cls.MULTISPECTRAL_EXTENSIONS
        )

        if suffix not in allowed:
            raise InvalidImageFileError(
                f"Extensión {suffix or '(sin extensión)'} "
                f"no válida para la banda "
                f"{band.value}."
            )

        return suffix

    @staticmethod
    def _validate_raster(
        source_path: Path,
    ) -> None:

        try:
            with rasterio.open(
                source_path
            ) as dataset:

                if dataset.width <= 0:
                    raise InvalidImageFileError(
                        "El TIFF no tiene "
                        "un ancho válido."
                    )

                if dataset.height <= 0:
                    raise InvalidImageFileError(
                        "El TIFF no tiene "
                        "una altura válida."
                    )

                if dataset.count < 1:
                    raise InvalidImageFileError(
                        "El TIFF no contiene bandas."
                    )

                # Fuerza una lectura real del primer píxel.
                dataset.read(
                    1,
                    window=(
                        (0, 1),
                        (0, 1),
                    ),
                )

        except InvalidImageFileError:
            raise

        except Exception as exc:
            raise InvalidImageFileError(
                f"El archivo TIFF no puede "
                f"ser leído correctamente: {exc}"
            ) from exc

    @staticmethod
    def _validate_rgb(
        source_path: Path,
    ) -> None:

        image = cv2.imread(
            str(source_path),
            cv2.IMREAD_UNCHANGED,
        )

        if image is None:
            raise InvalidImageFileError(
                "La imagen RGB no puede "
                "ser decodificada."
            )

        if image.size == 0:
            raise InvalidImageFileError(
                "La imagen RGB está vacía."
            )

    @classmethod
    def _validate_content(
        cls,
        *,
        source_path: Path,
        suffix: str,
    ) -> None:

        if suffix in {
            ".tif",
            ".tiff",
        }:
            cls._validate_raster(
                source_path
            )
            return

        cls._validate_rgb(
            source_path
        )

    @staticmethod
    def _sha256(
        path: Path,
    ) -> str:

        digest = hashlib.sha256()

        with path.open("rb") as file_handle:

            for chunk in iter(
                lambda: file_handle.read(
                    1024 * 1024
                ),
                b"",
            ):
                digest.update(chunk)

        return digest.hexdigest()

    @classmethod
    def remove_capture_storage(
        cls,
        *,
        campaign_code: str,
        sequence: int,
    ) -> bool:
        """
        Elimina el directorio físico administrado
        correspondiente a una captura.
        """

        capture_directory = (
            cls._storage_root()
            / campaign_code
            / "captures"
            / f"{sequence:04d}"
        )

        if capture_directory.exists():
            shutil.rmtree(
                capture_directory
            )

        return not capture_directory.exists()
    
    @classmethod
    def ingest_file(
        cls,
        *,
        capture_id: int,
        band: ImageBand | str,
        source_path: str | os.PathLike,
        remote_path: str | None = None,
    ) -> dict:

        normalized_band = (
            cls._normalize_band(
                band
            )
        )

        source = Path(
            source_path
        ).expanduser().resolve()

        cls._validate_file_exists(
            source
        )

        suffix = cls._validate_extension(
            source_path=source,
            band=normalized_band,
        )

        cls._validate_content(
            source_path=source,
            suffix=suffix,
        )

        capture = CaptureService.get_capture(
            capture_id
        )

        if capture is None:
            raise InvalidImageFileError(
                f"La captura con ID "
                f"{capture_id} no existe."
            )

        campaign = CampaignService.get_campaign(
            capture["campaign_id"]
        )

        if campaign is None:
            raise ImageIngestionError(
                "La campaña asociada "
                "a la captura no existe."
            )

        # Validación previa de compatibilidad.
        if (
            capture["sensor_type"]
            == "MULTISPECTRAL"
            and normalized_band == ImageBand.RGB
        ):
            raise InvalidImageFileError(
                "Una campaña MULTISPECTRAL "
                "no admite un activo RGB."
            )

        if (
            capture["sensor_type"]
            == "RGB"
            and normalized_band != ImageBand.RGB
        ):
            raise InvalidImageFileError(
                "Una campaña RGB solo admite "
                "activos RGB."
            )

        relative_path = Path(
            campaign["campaign_code"]
        ) / "captures" / (
            f"{capture['sequence']:04d}"
        ) / (
            f"{normalized_band.value}"
            f"{suffix}"
        )

        storage_root = cls._storage_root()

        destination = (
            storage_root
            / relative_path
        )

        if destination.exists():
            raise ImageIngestionError(
                "Ya existe un archivo físico "
                f"para {normalized_band.value} "
                f"en la captura {capture_id}."
            )

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary = destination.with_name(
            destination.name + ".tmp"
        )

        copied = False

        try:
            shutil.copy2(
                source,
                temporary,
            )

            os.replace(
                temporary,
                destination,
            )

            copied = True

            digest = cls._sha256(
                destination
            )

            size_bytes = (
                destination.stat().st_size
            )

            updated_capture = (
                CaptureService.add_asset(
                    capture_id=capture_id,
                    band=normalized_band,
                    original_filename=(
                        source.name
                    ),
                    storage_path=(
                        relative_path.as_posix()
                    ),
                    remote_path=remote_path,
                )
            )

            asset = next(
                (
                    item
                    for item
                    in updated_capture["assets"]
                    if item["band"]
                    == normalized_band.value
                ),
                None,
            )

            return {
                "capture": updated_capture,
                "asset": asset,
                "ingestion": {
                    "size_bytes": size_bytes,
                    "sha256": digest,
                    "storage_path": (
                        relative_path.as_posix()
                    ),
                },
            }

        except Exception as exc:

            if temporary.exists():
                temporary.unlink()

            if copied and destination.exists():
                destination.unlink()

            if isinstance(
                exc,
                ImageIngestionError,
            ):
                raise

            if isinstance(
                exc,
                InvalidCaptureError,
            ):
                raise ImageIngestionError(
                    str(exc)
                ) from exc

            raise ImageIngestionError(
                "No fue posible incorporar "
                f"la imagen: {exc}"
            ) from exc