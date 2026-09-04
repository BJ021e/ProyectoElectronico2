import pytest

from services.campaign_service import (
    CampaignService,
)
from services.capture_service import (
    CaptureService,
    InvalidCaptureError,
)
from services.processing_job_service import (
    InvalidProcessingJobError,
    ProcessingJobService,
)


def create_rgb_campaign():

    return (
        CampaignService.create_campaign(
            name="Campaña lifecycle",
            sensor_type="RGB",
            sensor_model="RGB",
        )
    )


def create_ready_rgb_campaign():

    campaign = create_rgb_campaign()

    capture = (
        CaptureService.create_capture(
            campaign_id=campaign["id"]
        )
    )

    CaptureService.add_asset(
        capture_id=capture["id"],
        band="RGB",
        original_filename="image.jpg",
        storage_path=(
            "tests/image.jpg"
        ),
    )

    return (
        CampaignService.get_campaign(
            campaign["id"]
        )
    )


def test_first_capture_marks_campaign_capturing():

    campaign = create_rgb_campaign()

    assert (
        campaign["status"]
        == "CREATED"
    )

    CaptureService.create_capture(
        campaign_id=campaign["id"]
    )

    updated = (
        CampaignService.get_campaign(
            campaign["id"]
        )
    )

    assert (
        updated["status"]
        == "CAPTURING"
    )


def test_complete_capture_marks_campaign_ready():

    campaign = create_ready_rgb_campaign()

    assert (
        campaign["status"]
        == "READY"
    )


def test_new_capture_returns_ready_campaign_to_capturing():

    campaign = create_ready_rgb_campaign()

    CaptureService.create_capture(
        campaign_id=campaign["id"]
    )

    updated = (
        CampaignService.get_campaign(
            campaign["id"]
        )
    )

    assert (
        updated["status"]
        == "CAPTURING"
    )


def test_deleting_incomplete_capture_restores_ready():

    campaign = create_ready_rgb_campaign()

    incomplete = (
        CaptureService.create_capture(
            campaign_id=campaign["id"]
        )
    )

    assert (
        CampaignService.get_campaign(
            campaign["id"]
        )["status"]
        == "CAPTURING"
    )

    deleted = (
        CaptureService.delete_capture(
            incomplete["id"]
        )
    )

    assert deleted is True

    updated = (
        CampaignService.get_campaign(
            campaign["id"]
        )
    )

    assert (
        updated["status"]
        == "READY"
    )


def test_processing_job_updates_campaign_status():

    campaign = create_ready_rgb_campaign()

    job = (
        ProcessingJobService.create_job(
            campaign_id=campaign["id"],
            backend="MOCK",
        )
    )

    ProcessingJobService.start_job(
        job["id"]
    )

    processing = (
        CampaignService.get_campaign(
            campaign["id"]
        )
    )

    assert (
        processing["status"]
        == "PROCESSING"
    )

    ProcessingJobService.complete_job(
        job["id"]
    )

    completed = (
        CampaignService.get_campaign(
            campaign["id"]
        )
    )

    assert (
        completed["status"]
        == "COMPLETED"
    )


def test_failed_running_job_marks_campaign_error():

    campaign = create_ready_rgb_campaign()

    job = (
        ProcessingJobService.create_job(
            campaign_id=campaign["id"],
            backend="MOCK",
        )
    )

    ProcessingJobService.start_job(
        job["id"]
    )

    ProcessingJobService.fail_job(
        job["id"],
        error_message="Fallo controlado",
    )

    failed = (
        CampaignService.get_campaign(
            campaign["id"]
        )
    )

    assert (
        failed["status"]
        == "ERROR"
    )

    retry = (
        ProcessingJobService.create_job(
            campaign_id=campaign["id"],
            backend="MOCK",
        )
    )

    ProcessingJobService.start_job(
        retry["id"]
    )

    retry_campaign = (
        CampaignService.get_campaign(
            campaign["id"]
        )
    )

    assert (
        retry_campaign["status"]
        == "PROCESSING"
    )


def test_completed_campaign_rejects_new_capture():

    campaign = create_ready_rgb_campaign()

    job = (
        ProcessingJobService.create_job(
            campaign_id=campaign["id"],
            backend="MOCK",
        )
    )

    ProcessingJobService.start_job(
        job["id"]
    )

    ProcessingJobService.complete_job(
        job["id"]
    )

    with pytest.raises(
        InvalidCaptureError
    ):
        CaptureService.create_capture(
            campaign_id=campaign["id"]
        )


def test_created_campaign_cannot_create_processing_job():

    campaign = create_rgb_campaign()

    with pytest.raises(
        InvalidProcessingJobError
    ):
        ProcessingJobService.create_job(
            campaign_id=campaign["id"],
            backend="MOCK",
        )