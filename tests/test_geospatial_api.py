from pathlib import Path

import cv2
import numpy as np
import time

from config import Config
from InterfazInit import app
from services.campaign_service import (
    CampaignService,
)
from services.capture_service import (
    CaptureService,
)
from services.image_ingestion_service import (
    ImageIngestionService,
)


def client():

    app.config["TESTING"] = True

    return app.test_client()


def create_ready_rgb_campaign(
    tmp_path,
):

    campaign = (
        CampaignService.create_campaign(
            name="Campaña API RGB",
            sensor_type="RGB",
            sensor_model="RGB",
        )
    )

    capture = (
        CaptureService.create_capture(
            campaign_id=campaign["id"]
        )
    )

    source = (
        tmp_path
        / "api_input.jpg"
    )

    image = np.zeros(
        (
            8,
            8,
            3,
        ),
        dtype=np.uint8,
    )

    assert cv2.imwrite(
        str(source),
        image,
    )

    ImageIngestionService.ingest_file(
        capture_id=capture["id"],
        band="RGB",
        source_path=source,
    )

    return campaign


def test_create_and_get_campaign_api():

    response = client().post(
        "/api/campaigns",
        json={
            "name": "Campaña API",
            "sensor_type": "MULTISPECTRAL",
            "sensor_model": (
                "MicaSense RedEdge-3"
            ),
        },
    )

    assert response.status_code == 201

    created = response.get_json()

    response = client().get(
        f"/api/campaigns/"
        f"{created['id']}"
    )

    assert response.status_code == 200

    campaign = response.get_json()

    assert (
        campaign["campaign_code"]
        == created["campaign_code"]
    )


def test_create_campaign_rejects_invalid_sensor():

    response = client().post(
        "/api/campaigns",
        json={
            "name": "Campaña inválida",
            "sensor_type": "THERMAL",
        },
    )

    assert response.status_code == 400

    assert (
        response.get_json()["error"]
        is True
    )


def test_list_campaigns_api():

    CampaignService.create_campaign(
        name="Campaña 1",
        sensor_type="RGB",
    )

    CampaignService.create_campaign(
        name="Campaña 2",
        sensor_type="MULTISPECTRAL",
    )

    response = client().get(
        "/api/campaigns"
    )

    assert response.status_code == 200

    data = response.get_json()

    assert data["count"] == 2

    assert len(
        data["campaigns"]
    ) == 2


def test_campaign_nested_resources_start_empty():

    campaign = (
        CampaignService.create_campaign(
            name="Campaña vacía",
            sensor_type="RGB",
        )
    )

    base = (
        f"/api/campaigns/"
        f"{campaign['id']}"
    )

    captures = client().get(
        base + "/captures"
    ).get_json()

    jobs = client().get(
        base + "/processing-jobs"
    ).get_json()

    products = client().get(
        base + "/products"
    ).get_json()

    assert captures["count"] == 0
    assert jobs["count"] == 0
    assert products["count"] == 0


def test_unknown_campaign_returns_404():

    response = client().get(
        "/api/campaigns/999999"
    )

    assert response.status_code == 404


def test_incomplete_campaign_cannot_process():

    campaign = (
        CampaignService.create_campaign(
            name="Campaña incompleta API",
            sensor_type="MULTISPECTRAL",
        )
    )

    CaptureService.create_capture(
        campaign_id=campaign["id"]
    )

    response = client().post(
        f"/api/campaigns/"
        f"{campaign['id']}/process"
    )

    assert response.status_code == 400

    jobs = client().get(
        f"/api/campaigns/"
        f"{campaign['id']}"
        "/processing-jobs"
    ).get_json()

    assert jobs["count"] == 0

def test_ready_campaign_processes_through_api(
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

    monkeypatch.setattr(
        Config,
        "PHOTOGRAMMETRY_BACKEND",
        "MOCK",
    )

    campaign = (
        create_ready_rgb_campaign(
            tmp_path
        )
    )

    response = client().post(
        f"/api/campaigns/"
        f"{campaign['id']}/process"
    )

    assert response.status_code == 202

    result = response.get_json()

    assert (
        result["accepted"]
        is True
    )

    assert (
        result["job"]["status"]
        == "PENDING"
    )

    job_id = (
        result["job"]["id"]
    )

    deadline = (
        time.monotonic()
        + 5.0
    )

    completed_job = None

    while (
        time.monotonic()
        < deadline
    ):

        jobs_response = client().get(
            f"/api/campaigns/"
            f"{campaign['id']}"
            f"/processing-jobs"
        )

        assert (
            jobs_response.status_code
            == 200
        )

        jobs_payload = (
            jobs_response.get_json()
        )

        jobs = (
            jobs_payload["jobs"]
        )

        current_job = next(
            (
                job
                for job in jobs
                if job["id"] == job_id
            ),
            None,
        )

        if (
            current_job is not None
            and current_job["status"]
            in {
                "COMPLETED",
                "FAILED",
            }
        ):

            completed_job = (
                current_job
            )

            break

        time.sleep(
            0.05
        )

    assert (
        completed_job
        is not None
    ), (
        "El trabajo no alcanzó "
        "un estado terminal."
    )

    assert (
        completed_job["status"]
        == "COMPLETED"
    ), completed_job.get(
        "error_message"
    )

    products_response = client().get(
        f"/api/campaigns/"
        f"{campaign['id']}/products"
    )

    assert (
        products_response.status_code
        == 200
    )

    products_payload = (
        products_response.get_json()
    )

    assert (
        products_payload["count"]
        == 1
    )

    product = (
        products_payload["products"][0]
    )

    assert (
        product["product_type"]
        == "ORTHOMOSAIC_RGB"
    )

    product_response = client().get(
        "/api/geospatial-products/"
        f"{product['id']}"
    )

    assert (
        product_response.status_code
        == 200
    )

    assert (
        product_response.get_json()
        ["product_code"]
        == product["product_code"]
    )
