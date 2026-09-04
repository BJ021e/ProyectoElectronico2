from services.drone_service import DroneService
from services.flight_service import FlightService
from services.telemetry_service import TelemetryService

from tests.helpers import wait_until


def test_simulator_operation_completes(
    ready_route
):

    result = (
        DroneService.prepare_simulated_flight(
            ready_route["id"],
            name="E2E SIMULATOR pytest",
        )
    )


    flight_id = int(
        result["flight"]["id"]
    )


    assert (
        result["provider"]
        ==
        "SIMULATOR"
    )


    DroneService.connect_operation()


    DroneService.start_operation(
        0.01
    )


    wait_until(
        lambda:
            FlightService
            .get_flight(
                flight_id
            )["status"]
            ==
            "COMPLETED",
        timeout=3.0,
    )


    flight = FlightService.get_flight(
        flight_id
    )


    telemetry = (
        TelemetryService
        .get_flight_points(
            flight_id
        )
    )


    mission = (
        DroneService
        .get_mission_status()
    )


    assert (
        flight["status"]
        ==
        "COMPLETED"
    )

    assert len(telemetry) > 1


    assert (
        mission["controller"]
        ==
        "SIMULATOR"
    )

    assert (
        mission["running"]
        is False
    )

    assert (
        mission["paused"]
        is False
    )

    assert (
        mission["last_error"]
        is None
    )