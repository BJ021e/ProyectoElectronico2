from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio

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

    @property
    def name(self) -> str:
        return "MOCK"

    def is_available(self) -> bool:
        return True

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

        data = np.stack(
            [
                np.full(
                    (height, width),
                    1000 + index * 100,
                    dtype=np.uint16,
                )
                for index in range(5)
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