import numpy as np
import pytest
import rasterio

from rasterio.transform import (
    from_origin,
)

from services.spectral_index_service import (
    InvalidSpectralIndexError,
    SpectralIndexService,
)


def write_multispectral_raster(
    path,
):

    transform = from_origin(
        280000,
        8660000,
        0.1,
        0.1,
    )

    values = {
        1: 100,  # BLUE
        2: 200,  # GREEN
        3: 300,  # RED
        4: 700,  # NIR
        5: 400,  # RED_EDGE
    }

    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=16,
        height=12,
        count=5,
        dtype="uint16",
        crs="EPSG:32718",
        transform=transform,
    ) as dataset:

        for (
            band,
            value,
        ) in values.items():

            data = np.full(
                (
                    12,
                    16,
                ),
                value,
                dtype=np.uint16,
            )

            dataset.write(
                data,
                band,
            )


def test_ndvi_array_formula():

    nir = np.array(
        [
            [
                700.0,
            ]
        ],
        dtype=np.float32,
    )

    red = np.array(
        [
            [
                300.0,
            ]
        ],
        dtype=np.float32,
    )

    result = (
        SpectralIndexService
        .calculate_array(
            positive=nir,
            negative=red,
        )
    )

    assert result[
        0,
        0,
    ] == pytest.approx(
        0.4
    )


def test_denominator_zero_becomes_nodata():

    positive = np.array(
        [
            [
                10.0,
            ]
        ],
        dtype=np.float32,
    )

    negative = np.array(
        [
            [
                -10.0,
            ]
        ],
        dtype=np.float32,
    )

    result = (
        SpectralIndexService
        .calculate_array(
            positive=positive,
            negative=negative,
        )
    )

    assert (
        result[
            0,
            0,
        ]
        == SpectralIndexService
        .OUTPUT_NODATA
    )


@pytest.mark.parametrize(
    (
        "index_name",
        "expected",
    ),
    [
        (
            "NDVI",
            (
                700 - 300
            )
            /
            (
                700 + 300
            ),
        ),
        (
            "NDRE",
            (
                700 - 400
            )
            /
            (
                700 + 400
            ),
        ),
        (
            "GNDVI",
            (
                700 - 200
            )
            /
            (
                700 + 200
            ),
        ),
    ],
)
def test_calculate_spectral_index_raster(
    tmp_path,
    index_name,
    expected,
):

    source = (
        tmp_path
        / "multispectral.tif"
    )

    output = (
        tmp_path
        / f"{index_name.lower()}.tif"
    )

    write_multispectral_raster(
        source
    )

    result_path = (
        SpectralIndexService
        .calculate_raster(
            source_path=source,
            output_path=output,
            index_name=index_name,
        )
    )

    assert (
        result_path
        == output.resolve()
    )

    with rasterio.open(
        result_path
    ) as dataset:

        assert dataset.count == 1

        assert (
            dataset.dtypes[0]
            == "float32"
        )

        assert (
            dataset.crs.to_epsg()
            == 32718
        )

        values = dataset.read(
            1
        )

        assert np.allclose(
            values,
            expected,
            atol=1e-6,
        )

        tags = dataset.tags()

        assert (
            tags[
                "SPECTRAL_INDEX"
            ]
            == index_name
        )


def test_invalid_index_is_rejected(
    tmp_path,
):

    source = (
        tmp_path
        / "multispectral.tif"
    )

    write_multispectral_raster(
        source
    )

    with pytest.raises(
        InvalidSpectralIndexError
    ):
        (
            SpectralIndexService
            .calculate_raster(
                source_path=source,
                output_path=(
                    tmp_path
                    / "invalid.tif"
                ),
                index_name="EVI2",
            )
        )