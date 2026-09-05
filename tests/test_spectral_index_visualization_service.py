import cv2
import numpy as np
import pytest
import rasterio

from rasterio.transform import (
    from_origin,
)

from services.spectral_index_visualization_service import (
    InvalidSpectralIndexVisualizationError,
    SpectralIndexVisualizationService,
)


def write_index_raster(
    path,
    *,
    values=None,
):

    transform = from_origin(
        280000,
        8660000,
        0.1,
        0.1,
    )

    if values is None:

        values = np.array(
            [
                [
                    -1.0,
                    -0.5,
                    0.0,
                    0.5,
                    1.0,
                ],
                [
                    -0.8,
                    -0.4,
                    0.1,
                    0.6,
                    0.9,
                ],
            ],
            dtype=np.float32,
        )

    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=(
            values.shape[1]
        ),
        height=(
            values.shape[0]
        ),
        count=1,
        dtype="float32",
        crs="EPSG:32718",
        transform=transform,
        nodata=-9999.0,
    ) as dataset:

        dataset.write(
            values,
            1,
        )


def decode_png(
    png_bytes,
):

    array = np.frombuffer(
        png_bytes,
        dtype=np.uint8,
    )

    return cv2.imdecode(
        array,
        cv2.IMREAD_UNCHANGED,
    )


def test_index_preview_generates_rgba_png(
    tmp_path,
):

    source = (
        tmp_path
        / "ndvi.tif"
    )

    write_index_raster(
        source
    )

    result = (
        SpectralIndexVisualizationService
        .render_png(
            source_path=source,
            index_name="NDVI",
        )
    )

    assert (
        result[:8]
        == b"\x89PNG\r\n\x1a\n"
    )

    image = decode_png(
        result
    )

    assert image is not None

    assert image.shape[2] == 4


def test_index_statistics_are_correct(
    tmp_path,
):

    source = (
        tmp_path
        / "ndvi.tif"
    )

    values = np.array(
        [
            [
                -1.0,
                0.0,
                1.0,
            ]
        ],
        dtype=np.float32,
    )

    write_index_raster(
        source,
        values=values,
    )

    statistics = (
        SpectralIndexVisualizationService
        .calculate_statistics(
            source_path=source,
            index_name="NDVI",
        )
    )

    assert (
        statistics["minimum"]
        == pytest.approx(
            -1.0
        )
    )

    assert (
        statistics["mean"]
        == pytest.approx(
            0.0
        )
    )

    assert (
        statistics["maximum"]
        == pytest.approx(
            1.0
        )
    )

    assert (
        statistics[
            "valid_pixel_count"
        ]
        == 3
    )


def test_nodata_is_excluded_from_statistics(
    tmp_path,
):

    source = (
        tmp_path
        / "ndvi.tif"
    )

    values = np.array(
        [
            [
                -9999.0,
                0.25,
                0.75,
            ]
        ],
        dtype=np.float32,
    )

    write_index_raster(
        source,
        values=values,
    )

    statistics = (
        SpectralIndexVisualizationService
        .calculate_statistics(
            source_path=source,
            index_name="NDVI",
        )
    )

    assert (
        statistics[
            "valid_pixel_count"
        ]
        == 2
    )

    assert (
        statistics["minimum"]
        == pytest.approx(
            0.25
        )
    )

    assert (
        statistics["mean"]
        == pytest.approx(
            0.5
        )
    )

    assert (
        statistics["maximum"]
        == pytest.approx(
            0.75
        )
    )


def test_fixed_legend_covers_minus_one_to_one():

    legend = (
        SpectralIndexVisualizationService
        .get_legend()
    )

    assert (
        legend[0]["value"]
        == -1.0
    )

    assert (
        legend[-1]["value"]
        == 1.0
    )


def test_unknown_index_is_rejected(
    tmp_path,
):

    source = (
        tmp_path
        / "index.tif"
    )

    write_index_raster(
        source
    )

    with pytest.raises(
        InvalidSpectralIndexVisualizationError
    ):
        (
            SpectralIndexVisualizationService
            .render_png(
                source_path=source,
                index_name="SAVI",
            )
        )