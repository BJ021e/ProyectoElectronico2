import pytest

from models import SensorType

from services.campaign_service import (
    CampaignService,
    InvalidCampaignError,
)
from services.flight_service import FlightService


def test_create_multispectral_campaign():

    campaign = CampaignService.create_campaign(
        name="Campaña RedEdge inicial",
        sensor_type=SensorType.MULTISPECTRAL,
        sensor_model="MicaSense RedEdge-3",
    )

    assert campaign["id"] is not None

    assert campaign["campaign_code"].startswith(
        "CP-"
    )

    assert (
        campaign["name"]
        == "Campaña RedEdge inicial"
    )

    assert (
        campaign["status"]
        == "CREATED"
    )

    assert (
        campaign["sensor_type"]
        == "MULTISPECTRAL"
    )

    assert (
        campaign["sensor_model"]
        == "MicaSense RedEdge-3"
    )

    assert campaign["flight_id"] is None


def test_create_rgb_campaign():

    campaign = CampaignService.create_campaign(
        name="Campaña RGB",
        sensor_type="RGB",
        sensor_model="RGB",
    )

    assert (
        campaign["sensor_type"]
        == "RGB"
    )


def test_campaign_can_be_linked_to_flight():

    flight = FlightService.create_flight(
        name="Vuelo para campaña"
    )

    campaign = CampaignService.create_campaign(
        name="Campaña vinculada",
        sensor_type="MULTISPECTRAL",
        sensor_model="MicaSense RedEdge-3",
        flight_id=flight["id"],
    )

    assert (
        campaign["flight_id"]
        == flight["id"]
    )


def test_campaign_rejects_unknown_flight():

    with pytest.raises(
        InvalidCampaignError
    ):
        CampaignService.create_campaign(
            name="Campaña inválida",
            sensor_type="MULTISPECTRAL",
            flight_id=999999,
        )


def test_campaign_rejects_invalid_sensor_type():

    with pytest.raises(
        InvalidCampaignError
    ):
        CampaignService.create_campaign(
            name="Campaña inválida",
            sensor_type="THERMAL",
        )


def test_campaign_rejects_empty_name():

    with pytest.raises(
        InvalidCampaignError
    ):
        CampaignService.create_campaign(
            name="   ",
            sensor_type="RGB",
        )


def test_get_campaign():

    created = CampaignService.create_campaign(
        name="Campaña consultable",
        sensor_type="MULTISPECTRAL",
    )

    campaign = CampaignService.get_campaign(
        created["id"]
    )

    assert campaign is not None

    assert (
        campaign["id"]
        == created["id"]
    )

    assert (
        campaign["campaign_code"]
        == created["campaign_code"]
    )


def test_get_unknown_campaign_returns_none():

    assert (
        CampaignService.get_campaign(
            999999
        )
        is None
    )


def test_list_campaigns_returns_newest_first():

    first = CampaignService.create_campaign(
        name="Campaña 1",
        sensor_type="RGB",
    )

    second = CampaignService.create_campaign(
        name="Campaña 2",
        sensor_type="MULTISPECTRAL",
    )

    campaigns = CampaignService.list_campaigns()

    assert len(campaigns) == 2

    assert (
        campaigns[0]["id"]
        == second["id"]
    )

    assert (
        campaigns[1]["id"]
        == first["id"]
    )