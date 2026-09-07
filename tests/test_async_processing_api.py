import InterfazInit as app_module


class DummyBackend:

    name = "MOCK"


def test_process_campaign_api_returns_202_without_executing_synchronously(
    monkeypatch,
):

    client = (
        app_module.app.test_client()
    )

    backend = DummyBackend()

    job = {
        "id": 77,
        "job_code": "PJ-TEST-0077",
        "campaign_id": 12,
        "backend": "MOCK",
        "status": "PENDING",
    }

    submitted = {}
    executed = []

    monkeypatch.setattr(
        app_module.CampaignService,
        "get_campaign",
        lambda campaign_id: {
            "id": campaign_id,
        },
    )

    monkeypatch.setattr(
        app_module
        .PhotogrammetryBackendFactory,
        "create",
        lambda: backend,
    )

    monkeypatch.setattr(
        app_module.ProcessingService,
        "prepare_campaign",
        lambda **kwargs: job,
    )

    def fake_execute_job(
        *,
        job_id,
        backend,
    ):

        executed.append(
            (
                job_id,
                backend,
            )
        )

    monkeypatch.setattr(
        app_module.ProcessingService,
        "execute_job",
        fake_execute_job,
    )

    def fake_submit(
        *,
        job_id,
        task,
    ):

        submitted["job_id"] = (
            job_id
        )

        submitted["task"] = (
            task
        )

        return object()

    monkeypatch.setattr(
        app_module.processing_executor,
        "submit",
        fake_submit,
    )

    response = client.post(
        "/api/campaigns/12/process"
    )

    assert response.status_code == 202

    payload = response.get_json()

    assert payload["accepted"] is True

    assert (
        payload["job"]["id"]
        == 77
    )

    assert (
        submitted["job_id"]
        == 77
    )

    # El request HTTP no debe ejecutar
    # fotogrametría directamente.
    assert executed == []

    # Comprobamos que la tarea encolada
    # referencia correctamente el mismo job.
    submitted["task"]()

    assert executed == [
        (
            77,
            backend,
        )
    ]


def test_process_campaign_api_marks_job_failed_if_queue_submission_fails(
    monkeypatch,
):

    client = (
        app_module.app.test_client()
    )

    backend = DummyBackend()

    job = {
        "id": 88,
        "job_code": "PJ-TEST-0088",
        "campaign_id": 15,
        "backend": "MOCK",
        "status": "PENDING",
    }

    failed = []

    monkeypatch.setattr(
        app_module.CampaignService,
        "get_campaign",
        lambda campaign_id: {
            "id": campaign_id,
        },
    )

    monkeypatch.setattr(
        app_module
        .PhotogrammetryBackendFactory,
        "create",
        lambda: backend,
    )

    monkeypatch.setattr(
        app_module.ProcessingService,
        "prepare_campaign",
        lambda **kwargs: job,
    )

    def failing_submit(
        *,
        job_id,
        task,
    ):

        raise RuntimeError(
            "executor unavailable"
        )

    monkeypatch.setattr(
        app_module.processing_executor,
        "submit",
        failing_submit,
    )

    def fake_fail_job(
        job_id,
        *,
        error_message,
    ):

        failed.append(
            (
                job_id,
                error_message,
            )
        )

        return {
            **job,
            "status": "FAILED",
        }

    monkeypatch.setattr(
        app_module.ProcessingJobService,
        "fail_job",
        fake_fail_job,
    )

    response = client.post(
        "/api/campaigns/15/process"
    )

    assert response.status_code == 500

    payload = response.get_json()

    assert payload["error"] is True

    assert len(failed) == 1

    assert failed[0][0] == 88

    assert (
        "executor unavailable"
        in failed[0][1]
    )


def test_process_campaign_api_returns_404_for_missing_campaign(
    monkeypatch,
):

    client = (
        app_module.app.test_client()
    )

    monkeypatch.setattr(
        app_module.CampaignService,
        "get_campaign",
        lambda campaign_id: None,
    )

    response = client.post(
        "/api/campaigns/999999/process"
    )

    assert response.status_code == 404