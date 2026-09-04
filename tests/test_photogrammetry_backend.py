from pathlib import Path

import pytest

from geospatial import (
    InvalidPhotogrammetryRequestError,
    MockPhotogrammetryBackend,
    PhotogrammetryBackend,
    PhotogrammetryRequest,
)
from models import (
    GeospatialProductType,
    SensorType,
)
from services.raster_service import (
    RasterService,
)


def create_input_file(
    tmp_path: Path,
    name: str = "input.tif",
) -> Path:

    path = (
        tmp_path
        / name
    )

    path.write_bytes(
        b"mock input"
    )

    return path


def test_mock_implements_photogrammetry_contract():

    backend = (
        MockPhotogrammetryBackend()
    )

    assert isinstance(
        backend,
        PhotogrammetryBackend,
    )


def test_mock_backend_is_available():

    backend = (
        MockPhotogrammetryBackend()
    )

    assert backend.name == "MOCK"

    assert (
        backend.is_available()
        is True
    )


def test_mock_multispectral_generates_geotiff(
    tmp_path,
):

    input_file = create_input_file(
        tmp_path
    )

    output_dir = (
        tmp_path
        / "output"
    )

    backend = (
        MockPhotogrammetryBackend()
    )

    result = backend.process(
        PhotogrammetryRequest(
            campaign_id=1,
            sensor_type=(
                SensorType.MULTISPECTRAL
            ),
            input_files=(
                str(input_file),
            ),
            output_dir=(
                str(output_dir)
            ),
        )
    )

    assert result.success is True

    assert result.backend == "MOCK"

    assert len(
        result.products
    ) == 1

    product = (
        result.products[0]
    )

    assert (
        product.product_type
        == GeospatialProductType
        .ORTHOMOSAIC_MULTISPECTRAL
    )

    product_path = Path(
        product.path
    )

    assert product_path.exists()

    raster = (
        RasterService.inspect_raster(
            product_path
        )
    )

    assert (
        raster["is_georeferenced"]
        is True
    )

    assert raster["epsg"] == 32718

    assert raster["band_count"] == 5

    assert raster["width"] == 32

    assert raster["height"] == 32


def test_mock_rgb_generates_three_band_geotiff(
    tmp_path,
):

    input_file = create_input_file(
        tmp_path
    )

    backend = (
        MockPhotogrammetryBackend()
    )

    result = backend.process(
        PhotogrammetryRequest(
            campaign_id=1,
            sensor_type=SensorType.RGB,
            input_files=(
                str(input_file),
            ),
            output_dir=str(
                tmp_path
                / "output"
            ),
        )
    )

    product = (
        result.products[0]
    )

    assert (
        product.product_type
        == GeospatialProductType
        .ORTHOMOSAIC_RGB
    )

    raster = (
        RasterService.inspect_raster(
            product.path
        )
    )

    assert raster["band_count"] == 3

    assert raster["epsg"] == 32718


def test_mock_rejects_empty_input_files(
    tmp_path,
):

    backend = (
        MockPhotogrammetryBackend()
    )

    with pytest.raises(
        InvalidPhotogrammetryRequestError
    ):

        backend.process(
            PhotogrammetryRequest(
                campaign_id=1,
                sensor_type=(
                    SensorType.MULTISPECTRAL
                ),
                input_files=(),
                output_dir=str(
                    tmp_path
                    / "output"
                ),
            )
        )


def test_mock_rejects_missing_input_file(
    tmp_path,
):

    backend = (
        MockPhotogrammetryBackend()
    )

    missing = (
        tmp_path
        / "missing.tif"
    )

    with pytest.raises(
        InvalidPhotogrammetryRequestError
    ):

        backend.process(
            PhotogrammetryRequest(
                campaign_id=1,
                sensor_type=(
                    SensorType.MULTISPECTRAL
                ),
                input_files=(
                    str(missing),
                ),
                output_dir=str(
                    tmp_path
                    / "output"
                ),
            )
        )