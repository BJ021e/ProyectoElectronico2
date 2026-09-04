import pytest

from sqlalchemy.exc import IntegrityError

from database import SessionLocal
from models import (
    Campaign,
    CampaignStatus,
    GeospatialProduct,
    GeospatialProductType,
    ProcessingJob,
    ProcessingJobStatus,
    SensorType,
)


def create_campaign_entity(
    session,
    *,
    code="CP-GEO-TEST-0001",
):

    campaign = Campaign(
        campaign_code=code,
        name="Campaña geoespacial",
        status=CampaignStatus.CREATED,
        sensor_type=SensorType.MULTISPECTRAL,
        sensor_model="MicaSense RedEdge-3",
    )

    session.add(campaign)
    session.flush()

    return campaign


def test_processing_job_can_be_linked_to_campaign():

    session = SessionLocal()

    try:
        campaign = create_campaign_entity(
            session
        )

        job = ProcessingJob(
            job_code="JOB-TEST-0001",
            campaign_id=campaign.id,
            backend="MOCK",
            status=ProcessingJobStatus.PENDING,
        )

        session.add(job)
        session.commit()
        session.refresh(job)

        assert job.id is not None
        assert job.campaign_id == campaign.id
        assert job.backend == "MOCK"

        assert (
            job.status
            == ProcessingJobStatus.PENDING
        )

    finally:
        session.close()


def test_geospatial_product_can_be_linked_to_job():

    session = SessionLocal()

    try:
        campaign = create_campaign_entity(
            session
        )

        job = ProcessingJob(
            job_code="JOB-TEST-0002",
            campaign_id=campaign.id,
            backend="MOCK",
        )

        session.add(job)
        session.flush()

        product = GeospatialProduct(
            product_code="GP-TEST-0001",
            campaign_id=campaign.id,
            processing_job_id=job.id,
            product_type=(
                GeospatialProductType.NDVI
            ),
            name="NDVI de prueba",
            storage_path=(
                "products/ndvi.tif"
            ),
            crs="EPSG:32718",
            epsg=32718,
            width=100,
            height=200,
            band_count=1,
            resolution_x=0.03,
            resolution_y=0.03,
        )

        session.add(product)
        session.commit()
        session.refresh(product)

        assert product.id is not None

        assert (
            product.processing_job_id
            == job.id
        )

        assert (
            product.product_type
            == GeospatialProductType.NDVI
        )

        assert product.epsg == 32718

    finally:
        session.close()


def test_external_product_can_exist_without_job():

    session = SessionLocal()

    try:
        campaign = create_campaign_entity(
            session
        )

        product = GeospatialProduct(
            product_code="GP-TEST-EXT-0001",
            campaign_id=campaign.id,
            processing_job_id=None,
            product_type=(
                GeospatialProductType
                .ORTHOMOSAIC_MULTISPECTRAL
            ),
            name="Ortomosaico externo",
            storage_path=(
                "products/"
                "orthomosaic_external.tif"
            ),
        )

        session.add(product)
        session.commit()
        session.refresh(product)

        assert product.id is not None

        assert (
            product.processing_job_id
            is None
        )

    finally:
        session.close()


def test_campaign_exposes_jobs_and_products():

    session = SessionLocal()

    try:
        campaign = create_campaign_entity(
            session
        )

        job = ProcessingJob(
            job_code="JOB-TEST-0003",
            campaign_id=campaign.id,
            backend="ODM",
        )

        session.add(job)
        session.flush()

        product = GeospatialProduct(
            product_code="GP-TEST-0002",
            campaign_id=campaign.id,
            processing_job_id=job.id,
            product_type=(
                GeospatialProductType.DSM
            ),
            name="DSM",
            storage_path="products/dsm.tif",
        )

        session.add(product)
        session.commit()
        session.refresh(campaign)

        assert len(
            campaign.processing_jobs
        ) == 1

        assert len(
            campaign.geospatial_products
        ) == 1

        assert len(
            job.products
        ) == 1

    finally:
        session.close()


def test_duplicate_product_code_is_rejected():

    session = SessionLocal()

    try:
        campaign = create_campaign_entity(
            session
        )

        first = GeospatialProduct(
            product_code="GP-DUPLICATE",
            campaign_id=campaign.id,
            product_type=(
                GeospatialProductType.NDVI
            ),
            name="NDVI 1",
            storage_path="ndvi_1.tif",
        )

        second = GeospatialProduct(
            product_code="GP-DUPLICATE",
            campaign_id=campaign.id,
            product_type=(
                GeospatialProductType.NDVI
            ),
            name="NDVI 2",
            storage_path="ndvi_2.tif",
        )

        session.add_all(
            [
                first,
                second,
            ]
        )

        with pytest.raises(
            IntegrityError
        ):
            session.commit()

    finally:
        session.rollback()
        session.close()