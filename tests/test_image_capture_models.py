import pytest

from sqlalchemy.exc import IntegrityError

from database import SessionLocal
from models import (
    Campaign,
    CampaignStatus,
    ImageAsset,
    ImageBand,
    ImageCapture,
    SensorType,
)


def create_campaign_entity(session):
    campaign = Campaign(
        campaign_code="CP-TEST-0001",
        name="Campaña de prueba",
        status=CampaignStatus.CREATED,
        sensor_type=SensorType.MULTISPECTRAL,
        sensor_model="MicaSense RedEdge-3",
    )

    session.add(campaign)
    session.flush()

    return campaign


def test_multispectral_capture_accepts_five_bands():

    session = SessionLocal()

    try:
        campaign = create_campaign_entity(
            session
        )

        capture = ImageCapture(
            capture_code="CAP-TEST-0001",
            campaign_id=campaign.id,
            sequence=1,
        )

        session.add(capture)
        session.flush()

        bands = [
            ImageBand.BLUE,
            ImageBand.GREEN,
            ImageBand.RED,
            ImageBand.NIR,
            ImageBand.RED_EDGE,
        ]

        for band in bands:
            session.add(
                ImageAsset(
                    capture_id=capture.id,
                    band=band,
                    original_filename=f"{band.value}.tif",
                    storage_path=(
                        f"campaign/1/{band.value}.tif"
                    ),
                )
            )

        session.commit()

        session.refresh(capture)

        assert len(capture.assets) == 5

        assert {
            asset.band
            for asset in capture.assets
        } == set(bands)

    finally:
        session.close()


def test_rgb_capture_accepts_rgb_asset():

    session = SessionLocal()

    try:
        campaign = create_campaign_entity(
            session
        )

        campaign.sensor_type = SensorType.RGB

        capture = ImageCapture(
            capture_code="CAP-TEST-RGB-0001",
            campaign_id=campaign.id,
            sequence=1,
        )

        session.add(capture)
        session.flush()

        asset = ImageAsset(
            capture_id=capture.id,
            band=ImageBand.RGB,
            original_filename="image.jpg",
            storage_path="campaign/rgb/image.jpg",
        )

        session.add(asset)

        session.commit()

        session.refresh(capture)

        assert len(capture.assets) == 1
        assert capture.assets[0].band == ImageBand.RGB

    finally:
        session.close()


def test_duplicate_band_is_rejected():

    session = SessionLocal()

    try:
        campaign = create_campaign_entity(
            session
        )

        capture = ImageCapture(
            capture_code="CAP-TEST-0002",
            campaign_id=campaign.id,
            sequence=1,
        )

        session.add(capture)
        session.flush()

        session.add(
            ImageAsset(
                capture_id=capture.id,
                band=ImageBand.BLUE,
                original_filename="blue_1.tif",
                storage_path="blue_1.tif",
            )
        )

        session.add(
            ImageAsset(
                capture_id=capture.id,
                band=ImageBand.BLUE,
                original_filename="blue_2.tif",
                storage_path="blue_2.tif",
            )
        )

        with pytest.raises(IntegrityError):
            session.commit()

    finally:
        session.rollback()
        session.close()


def test_duplicate_sequence_in_campaign_is_rejected():

    session = SessionLocal()

    try:
        campaign = create_campaign_entity(
            session
        )

        session.add(
            ImageCapture(
                capture_code="CAP-TEST-0003",
                campaign_id=campaign.id,
                sequence=1,
            )
        )

        session.add(
            ImageCapture(
                capture_code="CAP-TEST-0004",
                campaign_id=campaign.id,
                sequence=1,
            )
        )

        with pytest.raises(IntegrityError):
            session.commit()

    finally:
        session.rollback()
        session.close()