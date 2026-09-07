from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
import time

from rasterio.transform import (
    from_origin,
)

from geospatial.photogrammetry_backend import (
    InvalidPhotogrammetryRequestError,
    PhotogrammetryBackendError,
)
from geospatial.processing_types import (
    GeneratedRasterProduct,
    PhotogrammetryRequest,
    ProcessingResult,
)
from models import (
    GeospatialProductType,
    SensorType,
)


class MockPhotogrammetryBackend:
    
    def __init__(
        self,
        *,
        delay_seconds: float = 0.0,
    ):
        self._delay_seconds = max(
            0.0,
            float(delay_seconds),
        )
    
    @property
    def name(self) -> str:
        return "MOCK"

    def is_available(self) -> bool:
        return True

    @staticmethod
    def _build_multispectral_mock(
        *,
        width: int,
        height: int,
    ) -> np.ndarray:

        x = np.linspace(
            0.0,
            1.0,
            width,
            dtype=np.float32,
        )

        y = np.linspace(
            0.0,
            1.0,
            height,
            dtype=np.float32,
        )

        xx, yy = np.meshgrid(
            x,
            y,
        )

        blue = (
            1000.0
            + 3500.0 * xx
        )

        green = (
            1000.0
            + 3500.0 * yy
        )

        red = (
            1000.0
            + 3500.0
            * (
                xx + yy
            )
            / 2.0
        )

        distance = np.sqrt(
            (
                xx - 0.5
            ) ** 2
            +
            (
                yy - 0.5
            ) ** 2
        )

        nir = (
            1000.0
            + 4000.0
            * np.clip(
                1.0
                - distance * 1.7,
                0.0,
                1.0,
            )
        )

        red_edge = (
            2500.0
            + 1500.0
            * (
                np.sin(
                    xx
                    * np.pi
                    * 4.0
                )
                *
                np.cos(
                    yy
                    * np.pi
                    * 4.0
                )
            )
        )

        data = np.stack(
            [
                blue,
                green,
                red,
                nir,
                red_edge,
            ],
            axis=0,
        )

        return np.clip(
            data,
            1,
            65535,
        ).astype(
            np.uint16
        )
        
    @staticmethod
    def _validate_request(
        request: PhotogrammetryRequest,
    ) -> None:

        if request.campaign_id <= 0:
            raise InvalidPhotogrammetryRequestError(
                "campaign_id debe ser mayor que cero."
            )

        if not isinstance(
            request.sensor_type,
            SensorType,
        ):
            raise InvalidPhotogrammetryRequestError(
                "sensor_type no es válido."
            )

        if not request.input_files:
            raise InvalidPhotogrammetryRequestError(
                "El procesamiento requiere "
                "al menos un archivo de entrada."
            )

        for input_file in request.input_files:

            path = Path(
                input_file
            ).expanduser().resolve()

            if not path.exists():
                raise InvalidPhotogrammetryRequestError(
                    "El archivo de entrada "
                    f"no existe: {path}"
                )

            if not path.is_file():
                raise InvalidPhotogrammetryRequestError(
                    "La entrada no corresponde "
                    f"a un archivo: {path}"
                )

        if not request.output_dir.strip():
            raise InvalidPhotogrammetryRequestError(
                "output_dir es obligatorio."
            )

    @staticmethod
    def _write_mock_rgb(
        output_path: Path,
    ) -> None:

        width = 32
        height = 32

        data = np.stack(
            [
                np.full(
                    (height, width),
                    60,
                    dtype=np.uint8,
                ),
                np.full(
                    (height, width),
                    120,
                    dtype=np.uint8,
                ),
                np.full(
                    (height, width),
                    180,
                    dtype=np.uint8,
                ),
            ]
        )

        transform = from_origin(
            280000.0,
            8668000.0,
            0.05,
            0.05,
        )

        with rasterio.open(
            output_path,
            "w",
            driver="GTiff",
            width=width,
            height=height,
            count=3,
            dtype="uint8",
            crs="EPSG:32718",
            transform=transform,
            nodata=0,
        ) as dataset:

            dataset.write(
                data
            )

    @staticmethod
    def _write_mock_multispectral(
        output_path: Path,
    ) -> None:

        width = 32
        height = 32

        transform = from_origin(
            280000.0,
            8668000.0,
            20.0,
            20.0,
        )

        data = (
            MockPhotogrammetryBackend
            ._build_multispectral_mock(
                width=width,
                height=height,
            )
        )

        with rasterio.open(
            output_path,
            "w",
            driver="GTiff",
            width=width,
            height=height,
            count=5,
            dtype="uint16",
            crs="EPSG:32718",
            transform=transform,
            nodata=0,
        ) as dataset:

            dataset.write(
                data
            )
    
    def process(
        self,
        request: PhotogrammetryRequest,
    ) -> ProcessingResult:

        self._validate_request(
            request
        )

        output_dir = Path(
            request.output_dir
        ).expanduser().resolve()

        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        if self._delay_seconds > 0:

            time.sleep(
                self._delay_seconds
            )
        
        if (
            request.sensor_type
            == SensorType.RGB
        ):

            output_path = (
                output_dir
                / "mock_orthomosaic_rgb.tif"
            )

            product_type = (
                GeospatialProductType
                .ORTHOMOSAIC_RGB
            )

            product_name = (
                "Ortomosaico RGB Mock"
            )

            writer = (
                self._write_mock_rgb
            )

        elif (
            request.sensor_type
            == SensorType.MULTISPECTRAL
        ):

            output_path = (
                output_dir
                / (
                    "mock_orthomosaic_"
                    "multispectral.tif"
                )
            )

            product_type = (
                GeospatialProductType
                .ORTHOMOSAIC_MULTISPECTRAL
            )

            product_name = (
                "Ortomosaico Multiespectral Mock"
            )

            writer = (
                self._write_mock_multispectral
            )

        else:
            raise InvalidPhotogrammetryRequestError(
                "Tipo de sensor no soportado."
            )

        if output_path.exists():
            raise PhotogrammetryBackendError(
                "El archivo de salida Mock "
                f"ya existe: {output_path}"
            )

        try:
            writer(
                output_path
            )

        except Exception as exc:

            if output_path.exists():
                output_path.unlink()

            raise PhotogrammetryBackendError(
                "No fue posible generar "
                f"el producto Mock: {exc}"
            ) from exc

        product = GeneratedRasterProduct(
            product_type=product_type,
            name=product_name,
            path=str(output_path),
        )

        return ProcessingResult(
            backend=self.name,
            success=True,
            products=(
                product,
            ),
            error_message=None,
        )
        