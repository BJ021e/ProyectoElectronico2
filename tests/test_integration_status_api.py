from InterfazInit import app

from drone.dji_mission_controller import (
    DJIMissionController,
)
from drone.dji_provider import DJIProvider
from drone.dji_test_backend import DJITestBackend

from services.drone_service import DroneService


def test_integration_status_api_not_configured():

    client = app.test_client()


    response = client.get(
        "/api/drone/operation/integration-status"
    )


    assert response.status_code == 200


    data = response.get_json()


    assert data is not None

    assert data["provider"] is None

    assert data["configured"] is False

    assert (
        data["transport_connected"]
        is False
    )

    assert (
        data["aircraft_online"]
        is False
    )

    assert (
        data["telemetry_available"]
        is False
    )

    assert (
        data["telemetry_fresh"]
        is False
    )

    assert (
        data["health"]
        ==
        "NOT_CONFIGURED"
    )

def test_integration_status_api_connected(
    ready_route
):

    backend = DJITestBackend(
        on_state=(
            DroneService
            ._handle_mission_state
        )
    )


    provider = DJIProvider(
        backend
    )


    controller = DJIMissionController(
        backend
    )


    DroneService.prepare_operation(
        provider=provider,

        mission_controller=controller,

        route_id=ready_route["id"],

        name="DJI API connected",
    )


    DroneService.connect_operation()


    client = app.test_client()


    response = client.get(
        "/api/drone/operation/integration-status"
    )


    assert response.status_code == 200


    data = response.get_json()


    assert data["provider"] == "DJI"

    assert data["configured"] is True

    assert (
        data["transport_connected"]
        is True
    )

    assert (
        data["aircraft_online"]
        is True
    )

    assert (
        data["telemetry_available"]
        is False
    )

    assert (
        data["health"]
        ==
        "CONNECTED"
    )
    
def test_integration_status_api_online(
    ready_route
):

    backend = DJITestBackend(
        on_state=(
            DroneService
            ._handle_mission_state
        ),

        interval_seconds=10.0,
    )


    provider = DJIProvider(
        backend
    )


    controller = DJIMissionController(
        backend
    )


    DroneService.prepare_operation(
        provider=provider,

        mission_controller=controller,

        route_id=ready_route["id"],

        name="DJI API online",
    )


    DroneService.connect_operation()

    DroneService.start_operation()


    client = app.test_client()


    response = client.get(
        "/api/drone/operation/integration-status"
    )


    assert response.status_code == 200


    data = response.get_json()


    assert data["provider"] == "DJI"

    assert data["configured"] is True

    assert (
        data["transport_connected"]
        is True
    )

    assert (
        data["aircraft_online"]
        is True
    )

    assert (
        data["telemetry_available"]
        is True
    )

    assert (
        data["telemetry_fresh"]
        is True
    )

    assert (
        data["last_telemetry_at"]
        is not None
    )

    assert (
        data["telemetry_age_seconds"]
        is not None
    )

    assert (
        data["health"]
        ==
        "ONLINE"
    )
    
def test_integration_status_api_offline_after_transport_loss(
    ready_route
):

    backend = DJITestBackend(
        on_state=(
            DroneService
            ._handle_mission_state
        ),

        interval_seconds=10.0,
    )


    provider = DJIProvider(
        backend
    )


    controller = DJIMissionController(
        backend
    )


    DroneService.prepare_operation(
        provider=provider,

        mission_controller=controller,

        route_id=ready_route["id"],

        name="DJI API outage",
    )


    DroneService.connect_operation()

    DroneService.start_operation()


    backend.simulate_transport_loss()


    client = app.test_client()


    response = client.get(
        "/api/drone/operation/integration-status"
    )


    assert response.status_code == 200


    data = response.get_json()


    assert data["provider"] == "DJI"

    assert (
        data["transport_connected"]
        is False
    )

    assert (
        data["aircraft_online"]
        is False
    )

    assert (
        data["health"]
        ==
        "OFFLINE"
    )