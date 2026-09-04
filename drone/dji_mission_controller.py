from __future__ import annotations

from drone.dji_backend import (
    DJIBackend,
    DJIBackendError,
)
from drone.mission_controller import (
    MissionControllerError,
)
from drone.state import DroneState


class DJIMissionController:
    """
    Adapter entre MissionController y un backend DJI.

    No conoce FlightService, TelemetryService,
    Flask ni persistencia.
    """

    def __init__(
        self,
        backend: DJIBackend,
    ) -> None:

        if not isinstance(
            backend,
            DJIBackend
        ):

            raise MissionControllerError(
                "El backend no cumple "
                "el contrato DJIBackend."
            )

        self._backend = backend


    @property
    def name(
        self
    ) -> str:

        return "DJI"


    @property
    def backend_name(
        self
    ) -> str:

        return self._backend.name

    def configure(
        self,
        waypoints: list[dict],
    ) -> None:
        """
        Configura la misión mediante el backend DJI.
        """

        try:

            self._backend.configure_mission(
                waypoints
            )

        except DJIBackendError as exc:

            raise MissionControllerError(
                "No fue posible configurar "
                f"la misión DJI mediante "
                f"{self._backend.name}: {exc}"
            ) from exc
    
    def initialize(
        self
    ) -> DroneState:
        """
        Prepara técnicamente la misión DJI.
        """

        try:

            return (
                self._backend.initialize_mission()
            )

        except DJIBackendError as exc:

            raise MissionControllerError(
                "No fue posible inicializar "
                f"la misión DJI mediante "
                f"{self._backend.name}: {exc}"
            ) from exc


    def start(
        self,
        interval_seconds: float = 0.5,
    ) -> dict:
        """
        Inicia la misión DJI.

        interval_seconds forma parte del contrato
        MissionController, pero no necesariamente
        tiene significado para DJI.
        """

        _ = interval_seconds

        try:

            return (
                self._backend.start_mission()
            )

        except DJIBackendError as exc:

            raise MissionControllerError(
                "No fue posible iniciar "
                f"la misión DJI: {exc}"
            ) from exc


    def pause(
        self
    ) -> dict:

        try:

            return (
                self._backend.pause_mission()
            )

        except DJIBackendError as exc:

            raise MissionControllerError(
                "No fue posible pausar "
                f"la misión DJI: {exc}"
            ) from exc


    def resume(
        self,
        interval_seconds: float = 0.5,
    ) -> dict:

        _ = interval_seconds

        try:

            return (
                self._backend.resume_mission()
            )

        except DJIBackendError as exc:

            raise MissionControllerError(
                "No fue posible reanudar "
                f"la misión DJI: {exc}"
            ) from exc


    def status(
        self
    ) -> dict:

        try:

            return (
                self._backend.mission_status()
            )

        except DJIBackendError as exc:

            raise MissionControllerError(
                "No fue posible consultar "
                f"el estado de la misión DJI: {exc}"
            ) from exc