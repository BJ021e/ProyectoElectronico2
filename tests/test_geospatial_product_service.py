from pathlib import Path

import numpy as np
import pytest
import rasterio

from rasterio.transform import (
    from_origin,
)

from config import Config
from database import SessionLocal
from models import (
    ProcessingJob,
    ProcessingJobStatus,
)
from services.campaign_service import (
    CampaignService,
)
from services.geospatial_product_service import (
    GeospatialProductService,
    InvalidGeospatialProductError,
)


def create_campaign():

    return CampaignService.create_campaign(
        name="Campaña producto GIS",
        sensor_type="MULTISPECTRAL",
        sensor_model="MicaSense RedEdge-3",
    )


def create_geotiff(
    path: Path,
    *,
    crs="EPSG:32718",
    transform=None,
):

    if transform is None:
        transform = from_origin(
            280000.0,
            8668000.0,
            0.05,
            0.05,
        )

    data = np.arange(
        100,
        dtype=np.float32,
    ).reshape(
        10,
        10,
    )

    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=10,
        height=10,
        count=1,
        dtype="float32",
        crs=crs,
        transform=transform,
        nodata=-9999.0,
    ) as dataset:

        dataset.write(
            data,
            1,
        )


def create_processing_job(
    campaign_id: int,
    *,
    code: str,
):

    session = SessionLocal()

    try:
        job = ProcessingJob(
            job_code=code,
            campaign_id=campaign_id,
            backend="MOCK",
            status=(
                ProcessingJobStatus.COMPLETED
            ),
        )

        session.add(job)
        session.commit()
        session.refresh(job)

        return job.id

    finally:
        session.close()


def test_register_georeferenced_product(
    tmp_path,
    monkeypatch,
):

    storage_root = (
        tmp_path
        / "managed"
    )

    monkeypatch.setattr(
        Config,
        "CAMPAIGN_STORAGE_ROOT",
        str(storage_root),
    )

    source = (
        tmp_path
        / "orthomosaic.tif"
    )

    create_geotiff(
        source
    )

    campaign = create_campaign()

    product = (
        GeospatialProductService
        .register_raster_product(
            campaign_id=campaign["id"],
            product_type=(
                "ORTHOMOSAIC_MULTISPECTRAL"
            ),
            name="Ortomosaico",
            source_path=source,
        )
    )

    assert product["id"] is not None

    assert (
        product["product_code"]
        .startswith("GP-")
    )

    assert (
        product["product_type"]
        == "ORTHOMOSAIC_MULTISPECTRAL"
    )

    assert product["epsg"] == 32718

    assert product["width"] == 10

    assert product["height"] == 10

    assert product["band_count"] == 1

    assert (
        product["resolution"]["x"]
        == pytest.approx(0.05)
    )

    assert (
        product["resolution"]["y"]
        == pytest.approx(0.05)
    )

    assert product["bounds"] is not None

    assert (
        product["bounds_wgs84"]
        is not None
    )

    managed_file = (
        storage_root
        / product["storage_path"]
    )

    assert managed_file.exists()

    assert source.exists()


def test_product_can_be_linked_to_processing_job(
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

    source = (
        tmp_path
        / "ndvi.tif"
    )

    create_geotiff(
        source
    )

    campaign = create_campaign()

    job_id = create_processing_job(
        campaign["id"],
        code="JOB-PRODUCT-0001",
    )

    product = (
        GeospatialProductService
        .register_raster_product(
            campaign_id=campaign["id"],
            processing_job_id=job_id,
            product_type="NDVI",
            name="NDVI",
            source_path=source,
        )
    )

    assert (
        product["processing_job_id"]
        == job_id
    )


def test_processing_job_from_other_campaign_is_rejected(
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

    source = (
        tmp_path
        / "ndvi.tif"
    )

    create_geotiff(
        source
    )

    campaign_1 = create_campaign()

    campaign_2 = (
        CampaignService.create_campaign(
            name="Otra campaña",
            sensor_type="MULTISPECTRAL",
        )
    )

    job_id = create_processing_job(
        campaign_2["id"],
        code="JOB-PRODUCT-OTHER",
    )

    with pytest.raises(
        InvalidGeospatialProductError
    ):
        (
            GeospatialProductService
            .register_raster_product(
                campaign_id=(
                    campaign_1["id"]
                ),
                processing_job_id=job_id,
                product_type="NDVI",
                name="NDVI inválido",
                source_path=source,
            )
        )


def test_non_georeferenced_raster_is_rejected(
    tmp_path,
):

    source = (
        tmp_path
        / "without_crs.tif"
    )

    create_geotiff(
        source,
        crs=None,
    )

    campaign = create_campaign()

    with pytest.raises(
        InvalidGeospatialProductError
    ):
        (
            GeospatialProductService
            .register_raster_product(
                campaign_id=campaign["id"],
                product_type="NDVI",
                name="NDVI",
                source_path=source,
            )
        )


def test_unknown_campaign_is_rejected(
    tmp_path,
):

    source = (
        tmp_path
        / "product.tif"
    )

    create_geotiff(
        source
    )

    with pytest.raises(
        InvalidGeospatialProductError
    ):
        (
            GeospatialProductService
            .register_raster_product(
                campaign_id=999999,
                product_type="NDVI",
                name="NDVI",
                source_path=source,
            )
        )


def test_invalid_product_type_is_rejected(
    tmp_path,
):

    source = (
        tmp_path
        / "product.tif"
    )

    create_geotiff(
        source
    )

    campaign = create_campaign()

    with pytest.raises(
        InvalidGeospatialProductError
    ):
        (
            GeospatialProductService
            .register_raster_product(
                campaign_id=campaign["id"],
                product_type="UNKNOWN",
                name="Producto",
                source_path=source,
            )
        )


def test_get_product(
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

    source = (
        tmp_path
        / "dsm.tif"
    )

    create_geotiff(
        source
    )

    campaign = create_campaign()

    created = (
        GeospatialProductService
        .register_raster_product(
            campaign_id=campaign["id"],
            product_type="DSM",
            name="DSM",
            source_path=source,
        )
    )

    retrieved = (
        GeospatialProductService
        .get_product(
            created["id"]
        )
    )

    assert retrieved is not None

    assert (
        retrieved["product_code"]
        == created["product_code"]
    )


def test_list_products_can_filter_by_type(
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

    campaign = create_campaign()

    ndvi_source = (
        tmp_path
        / "ndvi.tif"
    )

    dsm_source = (
        tmp_path
        / "dsm.tif"
    )

    create_geotiff(
        ndvi_source
    )

    create_geotiff(
        dsm_source
    )

    (
        GeospatialProductService
        .register_raster_product(
            campaign_id=campaign["id"],
            product_type="NDVI",
            name="NDVI",
            source_path=ndvi_source,
        )
    )

    (
        GeospatialProductService
        .register_raster_product(
            campaign_id=campaign["id"],
            product_type="DSM",
            name="DSM",
            source_path=dsm_source,
        )
    )

    products = (
        GeospatialProductService
        .list_products(
            campaign["id"]
        )
    )

    assert len(products) == 2

    ndvi_products = (
        GeospatialProductService
        .list_products(
            campaign["id"],
            product_type="NDVI",
        )
    )

    assert len(
        ndvi_products
    ) == 1

    assert (
        ndvi_products[0]
        ["product_type"]
        == "NDVI"
    )