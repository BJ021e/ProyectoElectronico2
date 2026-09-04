from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


# ---------------------------------------------------------
# Base de datos exclusiva para pytest
# ---------------------------------------------------------

_TEST_DIRECTORY = Path(
    tempfile.mkdtemp(
        prefix="hortalizas_drone_tests_"
    )
)

_TEST_DATABASE = (
    _TEST_DIRECTORY
    / "test_ground_control.db"
)


#
# Debe establecerse ANTES de importar database,
# services o models.
#
os.environ["DATABASE_URL"] = (
    f"sqlite:///{_TEST_DATABASE.as_posix()}"
)


# ---------------------------------------------------------
# Imports posteriores a DATABASE_URL
# ---------------------------------------------------------

from database import (
    Base,
    engine,
    init_database,
)

from services.drone_service import DroneService
from services.route_service import RouteService


# ---------------------------------------------------------
# Limpieza del runtime DroneService
# ---------------------------------------------------------

def _reset_drone_runtime() -> None:
    """
    Detiene cualquier runtime técnico pendiente
    y limpia el estado global de DroneService.

    Se utiliza exclusivamente en tests.
    """

    runner = (
        DroneService._simulation_runner
    )


    if runner is not None:

        try:

            runner.stop()

        except Exception:

            pass


    provider = (
        DroneService._provider
    )


    if provider is not None:

        try:

            provider.disconnect()

        except Exception:

            pass


    with DroneService._lock:

        DroneService._provider = None

        DroneService._mission_controller = None

        DroneService._simulation_runner = None

        DroneService._active_route_id = None

        DroneService._active_flight_id = None


# ---------------------------------------------------------
# Entorno limpio para cada test
# ---------------------------------------------------------

@pytest.fixture(
    autouse=True
)
def clean_test_environment():

    _reset_drone_runtime()


    Base.metadata.drop_all(
        bind=engine
    )

    init_database()


    yield


    #
    # Primero detenemos threads/backends.
    #
    _reset_drone_runtime()


    #
    # Después eliminamos los datos del test.
    #
    Base.metadata.drop_all(
        bind=engine
    )


# ---------------------------------------------------------
# Route READY reutilizable
# ---------------------------------------------------------

@pytest.fixture
def ready_route() -> dict:
    """
    Crea una Route READY con seis waypoints.

    No depende de ninguna Route existente
    en la base de desarrollo.
    """

    route = RouteService.create_route(
        name="Ruta E2E pytest",
        description=(
            "Ruta temporal generada "
            "automáticamente por pytest."
        ),
    )


    route_id = int(
        route["id"]
    )


    waypoints = [
        {
            "latitude": -12.0600,
            "longitude": -77.0300,
            "altitude": 30.0,
            "speed": 4.0,
        },
        {
            "latitude": -12.0600,
            "longitude": -77.0290,
            "altitude": 30.0,
            "speed": 4.0,
        },
        {
            "latitude": -12.0604,
            "longitude": -77.0290,
            "altitude": 30.0,
            "speed": 4.0,
        },
        {
            "latitude": -12.0604,
            "longitude": -77.0300,
            "altitude": 30.0,
            "speed": 4.0,
        },
        {
            "latitude": -12.0608,
            "longitude": -77.0300,
            "altitude": 30.0,
            "speed": 4.0,
        },
        {
            "latitude": -12.0609,
            "longitude": -77.0305,
            "altitude": 30.0,
            "speed": 4.0,
        },
    ]


    for sequence, waypoint in enumerate(
        waypoints,
        start=1,
    ):

        RouteService.add_waypoint(
            route_id=route_id,

            sequence=sequence,

            latitude=(
                waypoint["latitude"]
            ),

            longitude=(
                waypoint["longitude"]
            ),

            altitude=(
                waypoint["altitude"]
            ),

            speed=(
                waypoint["speed"]
            ),
        )


    ready = RouteService.publish_route(
        route_id
    )


    assert ready["status"] == "READY"

    assert (
        ready["waypoint_count"]
        ==
        6
    )


    return ready