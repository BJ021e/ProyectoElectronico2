from dataclasses import dataclass

from models import (
    GeospatialProductType,
    SensorType,
)


@dataclass(frozen=True)
class PhotogrammetryInputAsset:
    """
    Archivo de entrada perteneciente a una captura
    fotogramétrica.
    """

    band: str
    path: str


@dataclass(frozen=True)
class PhotogrammetryCaptureGroup:
    """
    Agrupación explícita de archivos pertenecientes
    a una misma captura física.
    """

    capture_code: str
    assets: tuple[
        PhotogrammetryInputAsset,
        ...,
    ]


@dataclass(frozen=True)
class PhotogrammetryRequest:
    """
    Solicitud normalizada que recibe cualquier backend
    de fotogrametría.
    """

    campaign_id: int
    sensor_type: SensorType
    input_files: tuple[str, ...]
    output_dir: str

    capture_groups: tuple[
        PhotogrammetryCaptureGroup,
        ...,
    ] = ()


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