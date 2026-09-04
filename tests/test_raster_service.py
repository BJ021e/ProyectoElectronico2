from pathlib import Path

import numpy as np
import pytest
import rasterio

from rasterio.transform import (
    from_origin,
)

from services.raster_service import (
    InvalidRasterError,
    RasterService,
)


def write_raster(
    path: Path,
    data: np.ndarray,
    *,
    crs="EPSG:4326",
    transform=None,
    nodata=None,
):

    if data.ndim == 2:
        data = data[
            np.newaxis,
            :,
            :
        ]

    count, height, width = (
        data.shape
    )

    if transform is None:
        transform = from_origin(
            -77.10,
            -12.00,
            0.0001,
            0.0001,
        )

    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=count,
        dtype=data.dtype,
        crs=crs,
        transform=transform,
        nodata=nodata,
    ) as dataset:

        dataset.write(
            data
        )


def test_inspect_georeferenced_raster(
    tmp_path,
):

    path = (
        tmp_path
        / "orthomosaic.tif"
    )

    band_1 = np.arange(
        1,
        13,
        dtype=np.uint16,
    ).reshape(
        3,
        4,
    )

    band_2 = np.arange(
        21,
        33,
        dtype=np.uint16,
    ).reshape(
        3,
        4,
    )

    data = np.stack(
        [
            band_1,
            band_2,
        ]
    )

    write_raster(
        path,
        data,
    )

    result = (
        RasterService.inspect_raster(
            path
        )
    )

    assert result["driver"] == "GTiff"

    assert result["width"] == 4

    assert result["height"] == 3

    assert result["band_count"] == 2

    assert result["dtypes"] == [
        "uint16",
        "uint16",
    ]

    assert result["crs"] == "EPSG:4326"

    assert result["epsg"] == 4326

    assert (
        result["is_georeferenced"]
        is True
    )

    assert result["resolution"]["x"] == (
        pytest.approx(
            0.0001
        )
    )

    assert result["resolution"]["y"] == (
        pytest.approx(
            0.0001
        )
    )

    assert (
        result["bounds"]["left"]
        == pytest.approx(-77.10)
    )

    assert (
        result["bounds"]["top"]
        == pytest.approx(-12.00)
    )

    assert (
        result["bounds"]["right"]
        == pytest.approx(-77.0996)
    )

    assert (
        result["bounds"]["bottom"]
        == pytest.approx(-12.0003)
    )

    assert (
        result["bounds_wgs84"]
        is not None
    )

    assert len(
        result["statistics"]
    ) == 2

    assert (
        result["statistics"][0]
        ["mode"]
        == "exact"
    )

    assert (
        result["statistics"][0]
        ["mean"]
        == pytest.approx(6.5)
    )


def test_statistics_ignore_nodata(
    tmp_path,
):

    path = (
        tmp_path
        / "nodata.tif"
    )

    data = np.array(
        [
            [
                1.0,
                2.0,
            ],
            [
                3.0,
                -9999.0,
            ],
        ],
        dtype=np.float32,
    )

    write_raster(
        path,
        data,
        nodata=-9999.0,
    )

    result = (
        RasterService.inspect_raster(
            path
        )
    )

    stats = (
        result["statistics"][0]
    )

    assert (
        stats["valid_pixel_count"]
        == 3
    )

    assert stats["min"] == 1.0

    assert stats["max"] == 3.0

    assert (
        stats["mean"]
        == pytest.approx(2.0)
    )


def test_raster_without_crs_is_not_georeferenced(
    tmp_path,
):

    path = (
        tmp_path
        / "without_crs.tif"
    )

    data = np.ones(
        (
            4,
            4,
        ),
        dtype=np.uint8,
    )

    write_raster(
        path,
        data,
        crs=None,
    )

    result = (
        RasterService.inspect_raster(
            path
        )
    )

    assert result["crs"] is None

    assert result["epsg"] is None

    assert (
        result["is_georeferenced"]
        is False
    )

    assert (
        result["bounds_wgs84"]
        is None
    )


def test_large_raster_uses_sampled_statistics(
    tmp_path,
):

    path = (
        tmp_path
        / "large.tif"
    )

    data = np.arange(
        10000,
        dtype=np.uint16,
    ).reshape(
        100,
        100,
    )

    write_raster(
        path,
        data,
    )

    result = (
        RasterService.inspect_raster(
            path,
            max_statistics_pixels=100,
        )
    )

    stats = (
        result["statistics"][0]
    )

    assert (
        stats["mode"]
        == "sampled"
    )

    assert (
        stats["sample_pixel_count"]
        <= 100
    )

    assert (
        stats["valid_pixel_count"]
        <= 100
    )


def test_missing_raster_is_rejected(
    tmp_path,
):

    with pytest.raises(
        InvalidRasterError
    ):

        RasterService.inspect_raster(
            tmp_path
            / "missing.tif"
        )


def test_corrupted_raster_is_rejected(
    tmp_path,
):

    path = (
        tmp_path
        / "corrupted.tif"
    )

    path.write_bytes(
        b"esto no es un raster"
    )

    with pytest.raises(
        InvalidRasterError
    ):

        RasterService.inspect_raster(
            path
        )