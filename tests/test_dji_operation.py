from drone.dji_mission_controller import (
    DJIMissionController,
)
from drone.dji_provider import DJIProvider
from drone.dji_test_backend import DJITestBackend

from services.drone_service import DroneService
from services.flight_service import FlightService
from services.telemetry_service import TelemetryService

from tests.helpers import wait_until


def test_dji_operation_completes(
    ready_route
):

    backend = DJITestBackend(
        on_state=(
            DroneService
            ._handle_mission_state
        ),
        interval_seconds=0.01,
    )


    provider = DJIProvider(
        backend
    )


    controller = DJIMissionController(
        backend
    )


    result = DroneService.prepare_operation(
        provider=provider,

        mission_controller=controller,

        route_id=ready_route["id"],

        name="E2E DJI pytest",
    )


    flight_id = int(
        result["flight"]["id"]
    )


    assert (
        result["provider"]
        ==
        "DJI"
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


    final_state = (
        DroneService
        .get_state()
    )


    assert (
        flight["status"]
        ==
        "COMPLETED"
    )


    #
    # DJITestBackend emite exactamente
    # un estado por waypoint.
    #
    assert (
        len(telemetry)
        ==
        6
    )


    assert (
        mission["controller"]
        ==
        "DJI"
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


    assert (
        final_state.provider
        ==
        "DJI"
    )

    assert (
        final_state.latitude
        ==
        -12.0609
    )

    assert (
        final_state.longitude
        ==
        -77.0305
    )

    assert (
        final_state.speed
        ==
        0.0
    )

    assert (
        final_state.flight_mode
        ==
        "HOLD"
    )
    
def test_dji_operation_pause_resume(
    ready_route
):

    backend = DJITestBackend(
        on_state=(
            DroneService
            ._handle_mission_state
        ),
        interval_seconds=0.08,
    )


    provider = DJIProvider(
        backend
    )


    controller = DJIMissionController(
        backend
    )


    result = DroneService.prepare_operation(
        provider=provider,

        mission_controller=controller,

        route_id=ready_route["id"],

        name="DJI pause resume pytest",
    )


    flight_id = int(
        result["flight"]["id"]
    )


    DroneService.connect_operation()

    DroneService.start_operation()


    #
    # Esperamos hasta recibir por lo menos
    # un punto posterior al estado inicial.
    #
    wait_until(
        lambda:
            len(
                TelemetryService
                .get_flight_points(
                    flight_id
                )
            )
            >=
            2,
        timeout=2.0,
    )


    DroneService.pause_operation()


    paused_status = (
        DroneService
        .get_mission_status()
    )


    paused_count = len(
        TelemetryService
        .get_flight_points(
            flight_id
        )
    )


    assert (
        paused_status["running"]
        is False
    )

    assert (
        paused_status["paused"]
        is True
    )


    #
    # Damos tiempo suficiente para demostrar
    # que la telemetría no continúa avanzando.
    #
    import time

    time.sleep(
        0.20
    )


    count_after_wait = len(
        TelemetryService
        .get_flight_points(
            flight_id
        )
    )


    assert (
        count_after_wait
        ==
        paused_count
    )


    DroneService.resume_operation()


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


    final_points = (
        TelemetryService
        .get_flight_points(
            flight_id
        )
    )


    final_status = (
        DroneService
        .get_mission_status()
    )


    assert (
        len(final_points)
        ==
        6
    )

    assert (
        final_status["running"]
        is False
    )

    assert (
        final_status["paused"]
        is False
    )

    assert (
        final_status["last_error"]
        is None
    )