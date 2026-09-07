from pathlib import Path

import numpy as np

import pytest
import rasterio

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
        
def test_mock_multispectral_bands_have_distinct_patterns():

    data = (
        MockPhotogrammetryBackend
        ._build_multispectral_mock(
            width=32,
            height=32,
        )
    )

    assert data.shape == (
        5,
        32,
        32,
    )

    assert data.dtype == np.uint16

    for first in range(
        5
    ):
        for second in range(
            first + 1,
            5,
        ):
            assert not np.array_equal(
                data[first],
                data[second],
            )
            
def test_mock_multispectral_band_patterns_are_spatially_variable():

    data = (
        MockPhotogrammetryBackend
        ._build_multispectral_mock(
            width=32,
            height=32,
        )
    )

    for band in data:

        assert (
            np.min(
                band
            )
            <
            np.max(
                band
            )
        )
        
def test_mock_multispectral_written_geotiff_uses_distinct_patterns(
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

    backend.process(
        PhotogrammetryRequest(
            campaign_id=1,
            sensor_type=(
                SensorType.MULTISPECTRAL
            ),
            input_files=(
                str(input_file),
            ),
            output_dir=str(
                output_dir
            ),
        )
    )

    output_path = (
        output_dir
        / "mock_orthomosaic_multispectral.tif"
    )

    with rasterio.open(
        output_path
    ) as dataset:

        data = dataset.read()

        assert dataset.count == 5

        assert data.shape == (
            5,
            32,
            32,
        )

        assert all(
            dtype == "uint16"
            for dtype in dataset.dtypes
        )

    expected = (
        MockPhotogrammetryBackend
        ._build_multispectral_mock(
            width=32,
            height=32,
        )
    )

    assert np.array_equal(
        data,
        expected,
    )

    for first in range(5):

        for second in range(
            first + 1,
            5,
        ):

            assert not np.array_equal(
                data[first],
                data[second],
            )