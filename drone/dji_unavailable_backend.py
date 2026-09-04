from __future__ import annotations

from drone.dji_backend import (
    DJIBackendError,
)
from drone.state import DroneState


class DJIUnavailableBackend:
    """
    Backend explícitamente no disponible.

    Permite construir la arquitectura DJI
    sin fingir que existe hardware conectado.
    """

    @property
    def name(
        self
    ) -> str:

        return "UNAVAILABLE"


    def connect(
        self
    ) -> DroneState:

        raise DJIBackendError(
            "No existe una integración DJI "
            "real configurada."
        )


    def disconnect(
        self
    ) -> DroneState:

        return DroneState(
            provider="DJI",
            connected=False,
            aircraft_online=False,
        )


    def get_state(
        self
    ) -> DroneState:

        return DroneState(
            provider="DJI",
            connected=False,
            aircraft_online=False,
        )


    def configure_mission(
        self,
        waypoints: list[dict],
    ) -> None:

        raise DJIBackendError(
            "No existe una integración DJI "
            "real configurada."
        )


    def initialize_mission(
        self
    ) -> DroneState:

        raise DJIBackendError(
            "No existe una integración DJI "
            "real configurada."
        )


    def start_mission(
        self
    ) -> dict:

        raise DJIBackendError(
            "No existe una integración DJI "
            "real configurada."
        )


    def pause_mission(
        self
    ) -> dict:

        raise DJIBackendError(
            "No existe una integración DJI "
            "real configurada."
        )


    def resume_mission(
        self
    ) -> dict:

        raise DJIBackendError(
            "No existe una integración DJI "
            "real configurada."
        )


    def mission_status(
        self
    ) -> dict:

        return {
            "running": False,
            "paused": False,
            "last_error":
                "Integración DJI no configurada.",
        }