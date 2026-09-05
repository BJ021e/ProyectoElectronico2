import cv2
import numpy as np
import pytest
import rasterio

from rasterio.transform import (
    from_origin,
)

from services.raster_preview_service import (
    InvalidRasterPreviewError,
    RasterPreviewService,
)


def write_raster(
    path,
    *,
    band_count,
    width=120,
    height=80,
    crs="EPSG:32718",
):

    transform = from_origin(
        280000,
        8660000,
        0.1,
        0.1,
    )

    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=band_count,
        dtype="uint16",
        crs=crs,
        transform=transform,
    ) as dataset:

        for band_index in range(
            1,
            band_count + 1,
        ):

            x_gradient = np.linspace(
                0,
                1000,
                width,
                dtype=np.float32,
            )

            data = np.tile(
                x_gradient,
                (
                    height,
                    1,
                ),
            )

            data = (
                data
                + band_index * 500
            ).astype(
                np.uint16
            )

            dataset.write(
                data,
                band_index,
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


def test_rgb_raster_generates_png(
    tmp_path,
):

    source = (
        tmp_path
        / "rgb.tif"
    )

    write_raster(
        source,
        band_count=3,
    )

    result = (
        RasterPreviewService
        .render_png(
            source_path=source,
            product_type=(
                "ORTHOMOSAIC_RGB"
            ),
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


def test_multispectral_raster_generates_natural_color_preview(
    tmp_path,
):

    source = (
        tmp_path
        / "multispectral.tif"
    )

    write_raster(
        source,
        band_count=5,
    )

    result = (
        RasterPreviewService
        .render_png(
            source_path=source,
            product_type=(
                "ORTHOMOSAIC_MULTISPECTRAL"
            ),
        )
    )

    image = decode_png(
        result
    )

    assert image is not None

    assert image.shape[2] == 4

    assert (
        image.shape[0] > 0
    )

    assert (
        image.shape[1] > 0
    )


def test_preview_respects_max_dimension(
    tmp_path,
):

    source = (
        tmp_path
        / "large.tif"
    )

    write_raster(
        source,
        band_count=3,
        width=1200,
        height=600,
    )

    result = (
        RasterPreviewService
        .render_png(
            source_path=source,
            product_type=(
                "ORTHOMOSAIC_RGB"
            ),
            max_dimension=300,
        )
    )

    image = decode_png(
        result
    )

    assert image is not None

    height, width = (
        image.shape[:2]
    )

    assert max(
        width,
        height,
    ) <= 300


def test_preview_rejects_raster_without_crs(
    tmp_path,
):

    source = (
        tmp_path
        / "without_crs.tif"
    )

    write_raster(
        source,
        band_count=1,
        crs=None,
    )

    with pytest.raises(
        InvalidRasterPreviewError
    ):
        (
            RasterPreviewService
            .render_png(
                source_path=source,
            )
        )
        
def test_multispectral_band_preview_generates_png(
    tmp_path,
):

    source = (
        tmp_path
        / "multispectral.tif"
    )

    write_raster(
        source,
        band_count=5,
    )

    result = (
        RasterPreviewService
        .render_png(
            source_path=source,
            product_type=(
                "ORTHOMOSAIC_MULTISPECTRAL"
            ),
            display_mode="NIR",
        )
    )

    image = decode_png(
        result
    )

    assert image is not None

    assert image.shape[2] == 4


def test_multispectral_band_mapping():

    assert (
        RasterPreviewService
        ._select_band_indexes(
            band_count=5,
            product_type=(
                "ORTHOMOSAIC_MULTISPECTRAL"
            ),
            display_mode="BLUE",
        )
        == (1,)
    )

    assert (
        RasterPreviewService
        ._select_band_indexes(
            band_count=5,
            product_type=(
                "ORTHOMOSAIC_MULTISPECTRAL"
            ),
            display_mode="NIR",
        )
        == (4,)
    )

    assert (
        RasterPreviewService
        ._select_band_indexes(
            band_count=5,
            product_type=(
                "ORTHOMOSAIC_MULTISPECTRAL"
            ),
            display_mode="RED_EDGE",
        )
        == (5,)
    )


def test_invalid_preview_mode_is_rejected(
    tmp_path,
):

    source = (
        tmp_path
        / "multispectral.tif"
    )

    write_raster(
        source,
        band_count=5,
    )

    with pytest.raises(
        InvalidRasterPreviewError
    ):
        (
            RasterPreviewService
            .render_png(
                source_path=source,
                product_type=(
                    "ORTHOMOSAIC_MULTISPECTRAL"
                ),
                display_mode="THERMAL",
            )
        )