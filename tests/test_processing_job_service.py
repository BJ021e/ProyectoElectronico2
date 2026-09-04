import pytest

from services.campaign_service import (
    CampaignService,
)
from services.processing_job_service import (
    InvalidProcessingJobError,
    InvalidProcessingJobTransitionError,
    ProcessingJobService,
)


def create_campaign():

    return CampaignService.create_campaign(
        name="Campaña processing job",
        sensor_type="RGB",
    )


def test_create_job_starts_pending():

    campaign = create_campaign()

    job = ProcessingJobService.create_job(
        campaign_id=campaign["id"],
        backend="MOCK",
    )

    assert job["id"] is not None

    assert job["job_code"].startswith(
        "PJ-"
    )

    assert job["status"] == "PENDING"

    assert job["backend"] == "MOCK"

    assert job["started_at"] is None

    assert job["finished_at"] is None


def test_job_can_start_and_complete():

    campaign = create_campaign()

    job = ProcessingJobService.create_job(
        campaign_id=campaign["id"],
        backend="MOCK",
    )

    running = (
        ProcessingJobService.start_job(
            job["id"]
        )
    )

    assert running["status"] == "RUNNING"

    assert running["started_at"] is not None

    completed = (
        ProcessingJobService.complete_job(
            job["id"]
        )
    )

    assert (
        completed["status"]
        == "COMPLETED"
    )

    assert (
        completed["finished_at"]
        is not None
    )

    assert (
        completed["error_message"]
        is None
    )


def test_running_job_can_fail():

    campaign = create_campaign()

    job = ProcessingJobService.create_job(
        campaign_id=campaign["id"],
        backend="MOCK",
    )

    ProcessingJobService.start_job(
        job["id"]
    )

    failed = (
        ProcessingJobService.fail_job(
            job["id"],
            error_message="Fallo de prueba",
        )
    )

    assert failed["status"] == "FAILED"

    assert (
        failed["error_message"]
        == "Fallo de prueba"
    )

    assert (
        failed["finished_at"]
        is not None
    )


def test_pending_job_cannot_complete():

    campaign = create_campaign()

    job = ProcessingJobService.create_job(
        campaign_id=campaign["id"],
        backend="MOCK",
    )

    with pytest.raises(
        InvalidProcessingJobTransitionError
    ):
        ProcessingJobService.complete_job(
            job["id"]
        )


def test_unknown_campaign_is_rejected():

    with pytest.raises(
        InvalidProcessingJobError
    ):
        ProcessingJobService.create_job(
            campaign_id=999999,
            backend="MOCK",
        )


def test_list_jobs_returns_newest_first():

    campaign = create_campaign()

    first = ProcessingJobService.create_job(
        campaign_id=campaign["id"],
        backend="MOCK",
    )

    second = ProcessingJobService.create_job(
        campaign_id=campaign["id"],
        backend="MOCK",
    )

    jobs = ProcessingJobService.list_jobs(
        campaign["id"]
    )

    assert len(jobs) == 2

    assert jobs[0]["id"] == second["id"]

    assert jobs[1]["id"] == first["id"]