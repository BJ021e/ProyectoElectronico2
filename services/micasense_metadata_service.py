from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import rasterio


class MicaSenseMetadataError(Exception):
    """
    Error general durante la lectura o validación
    de metadatos MicaSense.
    """
    pass


class InvalidMicaSenseMetadataError(
    MicaSenseMetadataError
):
    """
    Los metadatos de una imagen no son válidos.
    """
    pass


class InconsistentMicaSenseMetadataError(
    MicaSenseMetadataError
):
    """
    Las bandas de una misma captura contienen
    metadatos incompatibles entre sí.
    """
    pass


@dataclass(
    frozen=True
)
class MicaSenseImageMetadata:

    latitude: float | None
    longitude: float | None
    altitude: float | None
    captured_at: datetime | None

    flight_id: str | None
    capture_id: str | None

    band_name: str | None
    central_wavelength: float | None


@dataclass(
    frozen=True
)
class MicaSenseCaptureMetadata:

    latitude: float | None
    longitude: float | None
    altitude: float | None
    captured_at: datetime | None

    flight_id: str | None
    capture_id: str | None


class MicaSenseMetadataService:

    MICASENSE_NAMESPACE = (
        "http://micasense.com/"
        "MicaSense/1.0/"
    )

    CAMERA_NAMESPACE = (
        "http://pix4d.com/1.0"
    )

    DMS_PATTERN = re.compile(
        r"\(([^)]+)\)"
    )

    BAND_NAMES = {
        "BLUE": "BLUE",
        "GREEN": "GREEN",
        "RED": "RED",
        "NIR": "NIR",
        "REDEDGE": "RED_EDGE",
        "RED EDGE": "RED_EDGE",
        "RED_EDGE": "RED_EDGE",
    }

    @staticmethod
    def _parse_number(
        raw_value,
    ) -> float | None:

        if raw_value is None:
            return None

        text = (
            str(raw_value)
            .strip()
            .strip("()")
            .strip()
        )

        if not text:
            return None

        try:
            if "/" in text:

                numerator, denominator = (
                    text.split(
                        "/",
                        1,
                    )
                )

                denominator_value = float(
                    denominator
                )

                if denominator_value == 0:
                    raise ValueError

                value = (
                    float(numerator)
                    / denominator_value
                )

            else:
                value = float(
                    text
                )

        except ValueError as exc:
            raise InvalidMicaSenseMetadataError(
                "Valor numérico EXIF "
                f"inválido: {raw_value}"
            ) from exc

        if not math.isfinite(
            value
        ):
            raise InvalidMicaSenseMetadataError(
                "El metadato numérico "
                "no es finito."
            )

        return value

    @classmethod
    def _parse_dms(
        cls,
        raw_value,
        reference,
    ) -> float | None:

        if (
            raw_value is None
            or reference is None
        ):
            return None

        components = (
            cls.DMS_PATTERN.findall(
                str(raw_value)
            )
        )

        if len(components) != 3:
            raise InvalidMicaSenseMetadataError(
                "Coordenada GPS EXIF "
                f"inválida: {raw_value}"
            )

        degrees = cls._parse_number(
            components[0]
        )

        minutes = cls._parse_number(
            components[1]
        )

        seconds = cls._parse_number(
            components[2]
        )

        if (
            degrees is None
            or minutes is None
            or seconds is None
        ):
            raise InvalidMicaSenseMetadataError(
                "La coordenada GPS "
                "está incompleta."
            )

        decimal = (
            degrees
            + minutes / 60.0
            + seconds / 3600.0
        )

        normalized_reference = (
            str(reference)
            .strip()
            .upper()
        )

        if normalized_reference in {
            "S",
            "W",
        }:
            decimal *= -1.0

        elif normalized_reference not in {
            "N",
            "E",
        }:
            raise InvalidMicaSenseMetadataError(
                "Referencia GPS "
                f"inválida: {reference}"
            )

        return decimal

    @staticmethod
    def _parse_datetime(
        raw_value,
    ) -> datetime | None:

        if raw_value is None:
            return None

        text = (
            str(raw_value)
            .strip()
        )

        if not text:
            return None

        try:
            return datetime.strptime(
                text,
                "%Y:%m:%d %H:%M:%S",
            )

        except ValueError as exc:
            raise InvalidMicaSenseMetadataError(
                "Fecha EXIF inválida: "
                f"{text}"
            ) from exc

    @classmethod
    def _normalize_band_name(
        cls,
        value,
    ) -> str | None:

        if value is None:
            return None

        normalized = (
            str(value)
            .strip()
            .upper()
        )

        if not normalized:
            return None

        return cls.BAND_NAMES.get(
            normalized,
            normalized,
        )

    @staticmethod
    def _find_xml_text(
        root,
        namespace: str,
        element_name: str,
    ) -> str | None:

        element = root.find(
            (
                ".//"
                f"{{{namespace}}}"
                f"{element_name}"
            )
        )

        if (
            element is None
            or element.text is None
        ):
            return None

        value = element.text.strip()

        return value or None

    @classmethod
    def _parse_xmp(
        cls,
        xmp_raw: str | None,
    ) -> dict:

        if not xmp_raw:
            return {
                "flight_id": None,
                "capture_id": None,
                "band_name": None,
                "central_wavelength": None,
            }

        xmp_text = str(
            xmp_raw
        ).strip()

        # Rasterio puede devolver el prefijo
        # "xml:XMP=" en algunos TIFF creados
        # artificialmente para pruebas.
        if xmp_text.startswith(
            "xml:XMP="
        ):
            xmp_text = xmp_text[
                len("xml:XMP="):
            ]

        try:
            root = ET.fromstring(
                xmp_text
            )

        except ET.ParseError as exc:
            raise InvalidMicaSenseMetadataError(
                "El bloque XMP no contiene "
                "XML válido."
            ) from exc

        flight_id = (
            cls._find_xml_text(
                root,
                cls.MICASENSE_NAMESPACE,
                "FlightId",
            )
        )

        capture_id = (
            cls._find_xml_text(
                root,
                cls.MICASENSE_NAMESPACE,
                "CaptureId",
            )
        )

        band_name = (
            cls._normalize_band_name(
                cls._find_xml_text(
                    root,
                    cls.CAMERA_NAMESPACE,
                    "BandName",
                )
            )
        )

        wavelength_raw = (
            cls._find_xml_text(
                root,
                cls.CAMERA_NAMESPACE,
                "CentralWavelength",
            )
        )

        central_wavelength = (
            cls._parse_number(
                wavelength_raw
            )
            if wavelength_raw
            is not None
            else None
        )

        return {
            "flight_id": flight_id,
            "capture_id": capture_id,
            "band_name": band_name,
            "central_wavelength": (
                central_wavelength
            ),
        }

    @classmethod
    def extract_image_metadata(
        cls,
        source_path: str | Path,
    ) -> MicaSenseImageMetadata:

        path = Path(
            source_path
        ).resolve()

        if (
            not path.exists()
            or not path.is_file()
        ):
            raise InvalidMicaSenseMetadataError(
                "La imagen MicaSense "
                "no existe."
            )

        try:
            with rasterio.open(
                path
            ) as dataset:

                exif = dataset.tags(
                    ns="EXIF"
                )

                xmp_tags = dataset.tags(
                    ns="xml:XMP"
                )

        except (
            rasterio.errors.RasterioError,
            OSError,
        ) as exc:
            raise MicaSenseMetadataError(
                "No fue posible leer "
                f"los metadatos de {path.name}: "
                f"{exc}"
            ) from exc

        latitude = cls._parse_dms(
            exif.get(
                "EXIF_GPSLatitude"
            ),
            exif.get(
                "EXIF_GPSLatitudeRef"
            ),
        )

        longitude = cls._parse_dms(
            exif.get(
                "EXIF_GPSLongitude"
            ),
            exif.get(
                "EXIF_GPSLongitudeRef"
            ),
        )

        if (
            latitude is None
        ) != (
            longitude is None
        ):
            raise InvalidMicaSenseMetadataError(
                "La imagen contiene "
                "GPS incompleto."
            )

        if (
            latitude is not None
            and not (
                -90.0
                <= latitude
                <= 90.0
            )
        ):
            raise InvalidMicaSenseMetadataError(
                "Latitud GPS fuera "
                "de rango."
            )

        if (
            longitude is not None
            and not (
                -180.0
                <= longitude
                <= 180.0
            )
        ):
            raise InvalidMicaSenseMetadataError(
                "Longitud GPS fuera "
                "de rango."
            )

        altitude = cls._parse_number(
            exif.get(
                "EXIF_GPSAltitude"
            )
        )

        altitude_reference = (
            str(
                exif.get(
                    "EXIF_GPSAltitudeRef",
                    "",
                )
            )
            .strip()
            .lower()
        )

        if (
            altitude is not None
            and altitude_reference
            in {
                "0x01",
                "1",
                "01",
            }
        ):
            altitude *= -1.0

        captured_at = (
            cls._parse_datetime(
                exif.get(
                    "EXIF_DateTimeOriginal"
                )
                or exif.get(
                    "EXIF_DateTimeDigitized"
                )
            )
        )

        xmp = cls._parse_xmp(
            xmp_tags.get(
                "xml:XMP"
            )
        )

        return MicaSenseImageMetadata(
            latitude=latitude,
            longitude=longitude,
            altitude=altitude,
            captured_at=captured_at,
            flight_id=xmp[
                "flight_id"
            ],
            capture_id=xmp[
                "capture_id"
            ],
            band_name=xmp[
                "band_name"
            ],
            central_wavelength=xmp[
                "central_wavelength"
            ],
        )

    @classmethod
    def extract_capture_metadata(
        cls,
        files_by_band: Mapping[
            str,
            str | Path,
        ],
    ) -> MicaSenseCaptureMetadata:

        if not files_by_band:
            raise InvalidMicaSenseMetadataError(
                "La captura no contiene "
                "archivos para inspeccionar."
            )

        metadata_items = []

        for (
            expected_band,
            source_path,
        ) in files_by_band.items():

            normalized_expected = (
                cls._normalize_band_name(
                    expected_band
                )
            )

            metadata = (
                cls.extract_image_metadata(
                    source_path
                )
            )

            if (
                metadata.band_name
                is not None
                and normalized_expected
                is not None
                and metadata.band_name
                != normalized_expected
            ):
                raise (
                    InconsistentMicaSenseMetadataError(
                        "La banda declarada "
                        "en XMP no coincide "
                        "con el archivo esperado: "
                        f"{expected_band} != "
                        f"{metadata.band_name}."
                    )
                )

            metadata_items.append(
                metadata
            )

        cls._validate_group_consistency(
            metadata_items
        )

        first = metadata_items[0]

        return MicaSenseCaptureMetadata(
            latitude=first.latitude,
            longitude=first.longitude,
            altitude=first.altitude,
            captured_at=first.captured_at,
            flight_id=first.flight_id,
            capture_id=first.capture_id,
        )

    @classmethod
    def _validate_group_consistency(
        cls,
        metadata_items: list[
            MicaSenseImageMetadata
        ],
    ) -> None:

        cls._validate_optional_field_presence(
            metadata_items,
            "latitude",
        )

        cls._validate_optional_field_presence(
            metadata_items,
            "longitude",
        )

        cls._validate_optional_field_presence(
            metadata_items,
            "altitude",
        )

        cls._validate_optional_field_presence(
            metadata_items,
            "captured_at",
        )

        cls._validate_optional_field_presence(
            metadata_items,
            "capture_id",
        )

        cls._validate_optional_field_presence(
            metadata_items,
            "flight_id",
        )

        first = metadata_items[0]

        for metadata in metadata_items[
            1:
        ]:

            if (
                first.latitude
                is not None
                and not math.isclose(
                    first.latitude,
                    metadata.latitude,
                    abs_tol=1e-6,
                )
            ):
                raise (
                    InconsistentMicaSenseMetadataError(
                        "Las bandas poseen "
                        "latitudes diferentes."
                    )
                )

            if (
                first.longitude
                is not None
                and not math.isclose(
                    first.longitude,
                    metadata.longitude,
                    abs_tol=1e-6,
                )
            ):
                raise (
                    InconsistentMicaSenseMetadataError(
                        "Las bandas poseen "
                        "longitudes diferentes."
                    )
                )

            if (
                first.altitude
                is not None
                and not math.isclose(
                    first.altitude,
                    metadata.altitude,
                    abs_tol=0.5,
                )
            ):
                raise (
                    InconsistentMicaSenseMetadataError(
                        "Las bandas poseen "
                        "altitudes incompatibles."
                    )
                )

            if (
                first.captured_at
                is not None
                and abs(
                    (
                        first.captured_at
                        - metadata.captured_at
                    ).total_seconds()
                )
                > 1.0
            ):
                raise (
                    InconsistentMicaSenseMetadataError(
                        "Las bandas poseen "
                        "horas de captura "
                        "incompatibles."
                    )
                )

            if (
                first.capture_id
                is not None
                and (
                    first.capture_id
                    != metadata.capture_id
                )
            ):
                raise (
                    InconsistentMicaSenseMetadataError(
                        "Las bandas poseen "
                        "CaptureId diferentes."
                    )
                )

            if (
                first.flight_id
                is not None
                and (
                    first.flight_id
                    != metadata.flight_id
                )
            ):
                raise (
                    InconsistentMicaSenseMetadataError(
                        "Las bandas poseen "
                        "FlightId diferentes."
                    )
                )

    @staticmethod
    def _validate_optional_field_presence(
        metadata_items,
        field_name: str,
    ) -> None:

        presence = [
            getattr(
                item,
                field_name,
            )
            is not None
            for item in metadata_items
        ]

        if (
            any(presence)
            and not all(presence)
        ):
            raise (
                InconsistentMicaSenseMetadataError(
                    "El metadato "
                    f"{field_name} aparece "
                    "solo en algunas bandas."
                )
            )