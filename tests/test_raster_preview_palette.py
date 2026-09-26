
import cv2
import numpy as np
import pytest
import rasterio

from rasterio.transform import from_origin

from services.raster_preview_service import (
    RasterPreviewService,
    InvalidRasterPreviewError,
)


@pytest.fixture
def multispectral_raster(tmp_path):
    path = tmp_path / "multispectral.tif"

    y, x = np.indices((32, 32))

    bands = np.stack([
        1000 + 11 * x + 2 * y,
        1500 + 5 * x + 8 * y,
        2000 + x + 14 * y,
        2500 + 7 * x + 4 * y,
        3000 + 3 * x + 9 * y,
    ]).astype(np.uint16)

    bands[:, :3, :3] = 65535

    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=32,
        width=32,
        count=5,
        dtype="uint16",
        crs="EPSG:3857",
        transform=from_origin(0, 32, 1, 1),
        nodata=65535,
    ) as dataset:
        dataset.write(bands)

    return path


def render_preview(path, mode, palette):
    png = RasterPreviewService.render_png(
        source_path=path,
        product_type="ORTHOMOSAIC_MULTISPECTRAL",
        display_mode=mode,
        band_palette=palette,
    )

    return cv2.imdecode(
        np.frombuffer(png, dtype=np.uint8),
        cv2.IMREAD_UNCHANGED,
    )


def test_blue_pseudocolor_preserves_intensity_and_nodata(
    multispectral_raster,
):
    gray = render_preview(
        multispectral_raster, "BLUE", "GRAY"
    )

    pseudo = render_preview(
        multispectral_raster, "BLUE", "PSEUDO"
    )

    assert gray.shape == pseudo.shape
    assert gray.shape[2] == 4

    # La máscara de transparencia no debe cambiar.
    np.testing.assert_array_equal(
        gray[:, :, 3],
        pseudo[:, :, 3],
    )

    assert np.any(gray[:, :, 3] == 0)
    assert np.any(gray[:, :, 3] == 255)

    # El pseudocolor azul conserva la intensidad
    # de la banda, con tolerancia por redondeo.
    np.testing.assert_allclose(
        gray[:, :, 0],
        pseudo[:, :, 0],
        atol=1,
    )

    assert np.all(pseudo[:, :, 1] == 0)
    assert np.all(pseudo[:, :, 2] == 0)


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("BLUE", (1,)),
        ("GREEN", (2,)),
        ("RED", (3,)),
        ("NIR", (4,)),
        ("RED_EDGE", (5,)),
        ("NATURAL", (3, 2, 1)),
    ],
)
def test_multispectral_band_mapping(mode, expected):
    result = RasterPreviewService._select_band_indexes(
        band_count=5,
        product_type="ORTHOMOSAIC_MULTISPECTRAL",
        display_mode=mode,
    )

    assert result == expected


def test_invalid_palette_is_rejected(multispectral_raster):
    with pytest.raises(InvalidRasterPreviewError):
        RasterPreviewService.render_png(
            source_path=multispectral_raster,
            product_type="ORTHOMOSAIC_MULTISPECTRAL",
            display_mode="BLUE",
            band_palette="INVALID",
        )
