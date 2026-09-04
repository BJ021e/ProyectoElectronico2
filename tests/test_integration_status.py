from drone.dji_mission_controller import (
    DJIMissionController,
)
from drone.dji_provider import DJIProvider
from drone.dji_test_backend import DJITestBackend

from services.drone_service import DroneService

from datetime import timedelta
from services.flight_service import FlightService

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
    
def test_dji_telemetry_becomes_stale(
    ready_route,
    monkeypatch,
):

    backend = DJITestBackend(
        on_state=(
            DroneService
            ._handle_mission_state
        ),

        #
        # Muy largo para evitar que el worker
        # produzca nuevos puntos durante el test.
        #
        interval_seconds=10.0,
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

        name="DJI stale telemetry",
    )


    flight_id = int(
        result["flight"]["id"]
    )


    DroneService.connect_operation()

    DroneService.start_operation()


    fresh = (
        DroneService
        .get_integration_status(
            stale_after_seconds=5.0
        )
    )


    assert fresh.telemetry_available is True
    assert fresh.telemetry_fresh is True
    assert fresh.health == "ONLINE"

    assert fresh.last_telemetry_at is not None


    fake_now = (
        fresh.last_telemetry_at
        +
        timedelta(
            seconds=10
        )
    )


    monkeypatch.setattr(
        DroneService,
        "_utcnow",
        staticmethod(
            lambda: fake_now
        ),
    )


    stale = (
        DroneService
        .get_integration_status(
            stale_after_seconds=5.0
        )
    )


    assert stale.transport_connected is True
    assert stale.aircraft_online is True

    assert stale.telemetry_available is True
    assert stale.telemetry_fresh is False

    assert stale.telemetry_age_seconds == 10.0

    assert stale.health == "DEGRADED"


    #
    # Freshness degradada NO cambia
    # el lifecycle del Flight.
    #
    assert (
        FlightService
        .get_flight(
            flight_id
        )["status"]
        ==
        "ACTIVE"
    )
    
def test_connection_loss_does_not_cancel_flight(
    ready_route
):

    backend = DJITestBackend(
        on_state=(
            DroneService
            ._handle_mission_state
        ),
        interval_seconds=1.0,
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

        name="DJI connection loss",
    )


    flight_id = int(
        result["flight"]["id"]
    )


    DroneService.connect_operation()

    DroneService.start_operation()


    assert (
        FlightService
        .get_flight(
            flight_id
        )["status"]
        ==
        "ACTIVE"
    )


    backend.simulate_transport_loss()


    integration = (
        DroneService
        .get_integration_status()
    )


    assert (
        integration.transport_connected
        is False
    )

    assert (
        integration.aircraft_online
        is False
    )

    assert (
        integration.health
        ==
        "OFFLINE"
    )


    #
    # La caída técnica no equivale
    # a cancelar la misión.
    #
    assert (
        FlightService
        .get_flight(
            flight_id
        )["status"]
        ==
        "ACTIVE"
    )

def test_connection_recovery_resynchronizes_completed_mission(
    ready_route
):

    from tests.helpers import wait_until


    backend = DJITestBackend(
        on_state=(
            DroneService
            ._handle_mission_state
        ),
        interval_seconds=0.05,
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

        name="DJI transport recovery",
    )


    flight_id = int(
        result["flight"]["id"]
    )


    DroneService.connect_operation()

    DroneService.start_operation()


    #
    # Cortamos comunicación casi inmediatamente.
    #
    backend.simulate_transport_loss()


    assert (
        DroneService
        .get_integration_status()
        .health
        ==
        "OFFLINE"
    )


    #
    # La misión interna continúa aunque nosotros
    # no recibimos nuevos callbacks.
    #
    wait_until(
        lambda:
            backend
            .mission_status()[
                "running"
            ]
            is False,
        timeout=2.0,
    )


    #
    # Desde la perspectiva de nuestra aplicación
    # aún no sabemos que terminó.
    #
    assert (
        FlightService
        .get_flight(
            flight_id
        )["status"]
        ==
        "ACTIVE"
    )


    #
    # Recuperamos comunicación.
    # Se sincroniza el último estado.
    #
    backend.simulate_transport_recovery()


    wait_until(
        lambda:
            FlightService
            .get_flight(
                flight_id
            )["status"]
            ==
            "COMPLETED",
        timeout=2.0,
    )


    integration = (
        DroneService
        .get_integration_status()
    )


    state = (
        DroneService
        .get_state()
    )


    assert (
        FlightService
        .get_flight(
            flight_id
        )["status"]
        ==
        "COMPLETED"
    )


    assert (
        integration.transport_connected
        is True
    )

    assert (
        integration.aircraft_online
        is True
    )

    assert (
        integration.health
        ==
        "ONLINE"
    )


    assert (
        state.flight_mode
        ==
        "HOLD"
    )

    assert (
        state.speed
        ==
        0.0
    )