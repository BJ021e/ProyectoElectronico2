import pytest

from services.campaign_service import (
    CampaignService,
)
from services.capture_service import (
    CaptureService,
    InvalidCaptureError,
)


def create_campaign(
    sensor_type="MULTISPECTRAL",
):
    return CampaignService.create_campaign(
        name="Campaña de prueba",
        sensor_type=sensor_type,
        sensor_model=(
            "MicaSense RedEdge-3"
            if sensor_type == "MULTISPECTRAL"
            else "RGB"
        ),
    )


def test_create_capture():

    campaign = create_campaign()

    capture = CaptureService.create_capture(
        campaign_id=campaign["id"],
        latitude=-12.0600,
        longitude=-77.0300,
        altitude=30,
    )

    assert capture["id"] is not None

    assert capture["sequence"] == 1

    assert capture["capture_code"].endswith(
        "CAP-0001"
    )

    assert capture["status"] == "CREATED"
    assert capture["role"] == "UNKNOWN"

    assert capture["latitude"] == -12.0600

    assert capture["longitude"] == -77.0300

    assert capture["altitude"] == 30.0

    assert capture["assets"] == []

    assert (
        capture["readiness"]["is_complete"]
        is False
    )


@pytest.mark.parametrize("role", ["UNKNOWN", "FLIGHT", "CALIBRATION"])
def test_capture_service_serializes_explicit_role(role):
    campaign = create_campaign()
    capture = CaptureService.create_capture(campaign_id=campaign["id"], role=role)
    assert capture["role"] == role
    assert CaptureService.get_capture(capture["id"])["role"] == role
    assert CaptureService.list_captures(campaign["id"])[0]["role"] == role
    assert capture["status"] == "CREATED"
    assert not capture["readiness"]["is_complete"]


@pytest.mark.parametrize("role", ["PANEL", "", None, 1, {}, "flight"])
def test_capture_service_rejects_invalid_role(role):
    campaign = create_campaign()
    with pytest.raises(InvalidCaptureError, match="UNKNOWN, FLIGHT o CALIBRATION"):
        CaptureService.create_capture(campaign_id=campaign["id"], role=role)
    assert CaptureService.list_captures(campaign["id"]) == []


def test_capture_api_counts_all_roles():
    from InterfazInit import app

    campaign = create_campaign()
    for role in ["FLIGHT", "CALIBRATION", "UNKNOWN", "UNKNOWN"]:
        CaptureService.create_capture(campaign_id=campaign["id"], role=role)
    response = app.test_client().get(f"/api/campaigns/{campaign['id']}/captures")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["count"] == len(payload["captures"]) == 4
    assert payload["role_counts"] == {"FLIGHT": 1, "CALIBRATION": 1, "UNKNOWN": 2}
    assert [c["role"] for c in payload["captures"]] == [
        "FLIGHT", "CALIBRATION", "UNKNOWN", "UNKNOWN",
    ]


def test_capture_sequence_increments_per_campaign():

    campaign_1 = create_campaign()

    first = CaptureService.create_capture(
        campaign_id=campaign_1["id"]
    )

    second = CaptureService.create_capture(
        campaign_id=campaign_1["id"]
    )

    campaign_2 = create_campaign()

    other = CaptureService.create_capture(
        campaign_id=campaign_2["id"]
    )

    assert first["sequence"] == 1
    assert second["sequence"] == 2

    assert other["sequence"] == 1


def test_multispectral_capture_becomes_ready():

    campaign = create_campaign()

    capture = CaptureService.create_capture(
        campaign_id=campaign["id"]
    )

    bands = [
        "BLUE",
        "GREEN",
        "RED",
        "NIR",
        "RED_EDGE",
    ]

    for index, band in enumerate(
        bands,
        start=1,
    ):
        capture = CaptureService.add_asset(
            capture_id=capture["id"],
            band=band,
            original_filename=(
                f"IMG_0001_{index}.tif"
            ),
            storage_path=(
                f"campaign/"
                f"capture/{band}.tif"
            ),
        )

        if band != "RED_EDGE":
            assert (
                capture["status"]
                == "CREATED"
            )

    assert capture["status"] == "READY"

    assert (
        capture["readiness"]["is_complete"]
        is True
    )

    assert (
        capture["readiness"]["missing_bands"]
        == []
    )

    assert len(
        capture["assets"]
    ) == 5


def test_multispectral_readiness_reports_missing_bands():

    campaign = create_campaign()

    capture = CaptureService.create_capture(
        campaign_id=campaign["id"]
    )

    CaptureService.add_asset(
        capture_id=capture["id"],
        band="BLUE",
        original_filename="blue.tif",
        storage_path="blue.tif",
    )

    CaptureService.add_asset(
        capture_id=capture["id"],
        band="RED",
        original_filename="red.tif",
        storage_path="red.tif",
    )

    capture = CaptureService.validate_capture(
        capture["id"]
    )

    assert (
        capture["readiness"]["is_complete"]
        is False
    )

    assert (
        capture["readiness"]["present_bands"]
        == [
            "BLUE",
            "RED",
        ]
    )

    assert (
        capture["readiness"]["missing_bands"]
        == [
            "GREEN",
            "NIR",
            "RED_EDGE",
        ]
    )


def test_rgb_capture_becomes_ready_with_rgb_asset():

    campaign = create_campaign(
        sensor_type="RGB"
    )

    capture = CaptureService.create_capture(
        campaign_id=campaign["id"]
    )

    capture = CaptureService.add_asset(
        capture_id=capture["id"],
        band="RGB",
        original_filename="IMG_0001.jpg",
        storage_path="rgb/IMG_0001.jpg",
    )

    assert capture["status"] == "READY"

    assert (
        capture["readiness"]["is_complete"]
        is True
    )

    assert (
        capture["readiness"]["expected_bands"]
        == ["RGB"]
    )


def test_incompatible_band_is_rejected():

    campaign = create_campaign()

    capture = CaptureService.create_capture(
        campaign_id=campaign["id"]
    )

    with pytest.raises(
        InvalidCaptureError
    ):
        CaptureService.add_asset(
            capture_id=capture["id"],
            band="RGB",
            original_filename="image.jpg",
            storage_path="image.jpg",
        )


def test_duplicate_band_is_rejected():

    campaign = create_campaign()

    capture = CaptureService.create_capture(
        campaign_id=campaign["id"]
    )

    CaptureService.add_asset(
        capture_id=capture["id"],
        band="BLUE",
        original_filename="blue.tif",
        storage_path="blue.tif",
    )

    with pytest.raises(
        InvalidCaptureError
    ):
        CaptureService.add_asset(
            capture_id=capture["id"],
            band="BLUE",
            original_filename="blue_2.tif",
            storage_path="blue_2.tif",
        )


def test_unknown_campaign_is_rejected():

    with pytest.raises(
        InvalidCaptureError
    ):
        CaptureService.create_capture(
            campaign_id=999999
        )


def test_invalid_coordinates_are_rejected():

    campaign = create_campaign()

    with pytest.raises(
        InvalidCaptureError
    ):
        CaptureService.create_capture(
            campaign_id=campaign["id"],
            latitude=91,
        )

    with pytest.raises(
        InvalidCaptureError
    ):
        CaptureService.create_capture(
            campaign_id=campaign["id"],
            longitude=-181,
        )


def test_get_and_list_captures():

    campaign = create_campaign()

    first = CaptureService.create_capture(
        campaign_id=campaign["id"]
    )

    second = CaptureService.create_capture(
        campaign_id=campaign["id"]
    )

    retrieved = CaptureService.get_capture(
        first["id"]
    )

    assert retrieved is not None

    assert (
        retrieved["id"]
        == first["id"]
    )

    captures = CaptureService.list_captures(
        campaign["id"]
    )

    assert len(captures) == 2

    assert captures[0]["id"] == first["id"]

    assert captures[1]["id"] == second["id"]
