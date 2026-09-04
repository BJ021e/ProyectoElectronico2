from __future__ import annotations

from dataclasses import dataclass

from models import (
    GeospatialProductType,
    SensorType,
)


@dataclass(frozen=True)
class PhotogrammetryRequest:
    """
    Solicitud normalizada que recibe cualquier backend
    de fotogrametría.

    input_files contiene archivos de entrada ya
    administrados o accesibles para el backend.
    """

    campaign_id: int
    sensor_type: SensorType
    input_files: tuple[str, ...]
    output_dir: str


@dataclass(frozen=True)
class GeneratedRasterProduct:
    """
    Producto raster generado por un backend.

    Todavía no representa una entidad persistente.
    GeospatialProductService será responsable
    de registrarlo posteriormente.
    """

    product_type: GeospatialProductType
    name: str
    path: str


@dataclass(frozen=True)
class ProcessingResult:
    """
    Resultado normalizado e independiente del motor
    concreto de fotogrametría.
    """

    backend: str
    success: bool
    products: tuple[
        GeneratedRasterProduct,
        ...,
    ]
    error_message: str | None = None