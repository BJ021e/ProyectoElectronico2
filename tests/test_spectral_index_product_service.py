import numpy as np
import pytest
import rasterio

from rasterio.transform import (
    from_origin,
)

from config import Config

from services.campaign_service import (
    CampaignService,
)

from services.geospatial_product_service import (
    GeospatialProductService,
)

from services.spectral_index_product_service import (
    InvalidSpectralIndexSourceError,
    SpectralIndexProductAlreadyExistsError,
    SpectralIndexProductService,
)


def create_multispectral_tiff(
    path,
):

    transform = from_origin(
        280000,
        8660000,
        0.1,
        0.1,
    )

    values = {
        1: 100,
        2: 200,
        3: 300,
        4: 700,
        5: 400,
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

            dataset.write(
                np.full(
                    (
                        12,
                        16,
                    ),
                    value,
                    dtype=np.uint16,
                ),
                band,
            )


def create_source_product(
    tmp_path,
    monkeypatch,
):

    monkeypatch.setattr(
        Config,
        "CAMPAIGN_STORAGE_ROOT",
        str(
            tmp_path
            / "managed"
        ),
    )

    campaign = (
        CampaignService
        .create_campaign(
            name=(
                "Campaña índices"
            ),
            sensor_type=(
                "MULTISPECTRAL"
            ),
            sensor_model=(
                "MicaSense RedEdge-3"
            ),
        )
    )

    source = (
        tmp_path
        / "orthomosaic.tif"
    )

    create_multispectral_tiff(
        source
    )

    product = (
        GeospatialProductService
        .register_raster_product(
            campaign_id=(
                campaign["id"]
            ),
            product_type=(
                "ORTHOMOSAIC_MULTISPECTRAL"
            ),
            name=(
                "Ortomosaico Multiespectral"
            ),
            source_path=source,
        )
    )

    return (
        campaign,
        product,
    )


def test_ndvi_is_persisted_as_geospatial_product(
    tmp_path,
    monkeypatch,
):

    (
        campaign,
        source_product,
    ) = create_source_product(
        tmp_path,
        monkeypatch,
    )

    ndvi = (
        SpectralIndexProductService
        .generate_index(
            source_product_id=(
                source_product["id"]
            ),
            index_name="NDVI",
        )
    )

    assert (
        ndvi["campaign_id"]
        == campaign["id"]
    )

    assert (
        (
            ndvi.get(
                "product_type"
            )
            or ndvi.get(
                "type"
            )
        )
        == "NDVI"
    )

    assert (
        ndvi["band_count"]
        == 1
    )

    assert (
        ndvi["epsg"]
        == 32718
    )

    products = (
        GeospatialProductService
        .list_products(
            campaign["id"]
        )
    )

    product_types = {
        (
            product.get(
                "product_type"
            )
            or product.get(
                "type"
            )
        )
        for product in products
    }

    assert (
        "ORTHOMOSAIC_MULTISPECTRAL"
        in product_types
    )

    assert (
        "NDVI"
        in product_types
    )


@pytest.mark.parametrize(
    "index_name",
    [
        "NDVI",
        "NDRE",
        "GNDVI",
    ],
)
def test_supported_indices_become_products(
    tmp_path,
    monkeypatch,
    index_name,
):

    (
        _,
        source_product,
    ) = create_source_product(
        tmp_path,
        monkeypatch,
    )

    result = (
        SpectralIndexProductService
        .generate_index(
            source_product_id=(
                source_product["id"]
            ),
            index_name=index_name,
        )
    )

    result_type = (
        result.get(
            "product_type"
        )
        or result.get(
            "type"
        )
    )

    assert (
        result_type
        == index_name
    )


def test_same_index_is_not_generated_twice(
    tmp_path,
    monkeypatch,
):

    (
        _,
        source_product,
    ) = create_source_product(
        tmp_path,
        monkeypatch,
    )

    (
        SpectralIndexProductService
        .generate_index(
            source_product_id=(
                source_product["id"]
            ),
            index_name="NDVI",
        )
    )

    with pytest.raises(
        SpectralIndexProductAlreadyExistsError
    ):
        (
            SpectralIndexProductService
            .generate_index(
                source_product_id=(
                    source_product["id"]
                ),
                index_name="NDVI",
            )
        )


def test_non_multispectral_product_is_rejected(
    tmp_path,
    monkeypatch,
):

    monkeypatch.setattr(
        Config,
        "CAMPAIGN_STORAGE_ROOT",
        str(
            tmp_path
            / "managed"
        ),
    )

    campaign = (
        CampaignService
        .create_campaign(
            name="Campaña RGB",
            sensor_type="RGB",
        )
    )

    source = (
        tmp_path
        / "rgb.tif"
    )

    transform = from_origin(
        280000,
        8660000,
        0.1,
        0.1,
    )

    with rasterio.open(
        source,
        "w",
        driver="GTiff",
        width=8,
        height=8,
        count=3,
        dtype="uint8",
        crs="EPSG:32718",
        transform=transform,
    ) as dataset:

        for band in range(
            1,
            4,
        ):
            dataset.write(
                np.full(
                    (
                        8,
                        8,
                    ),
                    100,
                    dtype=np.uint8,
                ),
                band,
            )

    rgb_product = (
        GeospatialProductService
        .register_raster_product(
            campaign_id=(
                campaign["id"]
            ),
            product_type=(
                "ORTHOMOSAIC_RGB"
            ),
            name="RGB",
            source_path=source,
        )
    )

    with pytest.raises(
        InvalidSpectralIndexSourceError
    ):
        (
            SpectralIndexProductService
            .generate_index(
                source_product_id=(
                    rgb_product["id"]
                ),
                index_name="NDVI",
            )
        )