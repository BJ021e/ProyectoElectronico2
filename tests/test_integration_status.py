from drone.dji_mission_controller import (
    DJIMissionController,
)
from drone.dji_provider import DJIProvider
from drone.dji_test_backend import DJITestBackend

from services.drone_service import DroneService


def test_integration_not_configured():

    status = (
        DroneService
        .get_integration_status()
    )


    assert (
        status.configured
        is False
    )

    assert (
        status.health
        ==
        "NOT_CONFIGURED"
    )

    assert (
        status.telemetry_available
        is False
    )


def test_simulator_configured_but_offline(
    ready_route
):

    DroneService.configure_simulator(
        ready_route["id"]
    )


    status = (
        DroneService
        .get_integration_status()
    )


    assert status.configured is True

    assert status.provider == "SIMULATOR"

    assert (
        status.transport_connected
        is False
    )

    assert status.health == "OFFLINE"


def test_dji_connected_without_telemetry(
    ready_route
):

    backend = DJITestBackend(
        on_state=(
            DroneService
            ._handle_mission_state
        ),
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

        name="DJI integration status",
    )


    DroneService.connect_operation()


    status = (
        DroneService
        .get_integration_status()
    )


    assert (
        status.transport_connected
        is True
    )

    assert (
        status.aircraft_online
        is True
    )

    assert (
        status.telemetry_available
        is False
    )

    assert (
        status.health
        ==
        "CONNECTED"
    )

def test_dji_telemetry_becomes_online(
    ready_route
):

    backend = DJITestBackend(
        on_state=(
            DroneService
            ._handle_mission_state
        ),
        interval_seconds=0.02,
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

        name="DJI fresh telemetry",
    )


    DroneService.connect_operation()

    DroneService.start_operation()


    status = (
        DroneService
        .get_integration_status(
            stale_after_seconds=5.0
        )
    )


    assert (
        status.telemetry_available
        is True
    )

    assert (
        status.telemetry_fresh
        is True
    )

    assert (
        status.health
        ==
        "ONLINE"
    )