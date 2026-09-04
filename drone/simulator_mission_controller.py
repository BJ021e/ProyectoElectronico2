from __future__ import annotations

from drone.mission_controller import (
    MissionControllerError,
)
from drone.simulation_runner import (
    SimulationRunner,
    SimulationRunnerError,
)
from drone.simulator import (
    DroneSimulator,
    DroneSimulatorError,
)
from drone.state import DroneState


class SimulatorMissionController:
    """
    Controlador técnico de misiones para
    DroneSimulator.

    Coordina:

    - estado interno del DroneSimulator;
    - SimulationRunner.

    No conoce FlightService, TelemetryService
    ni persistencia.
    """

    def __init__(
        self,
        simulator: DroneSimulator,
        runner: SimulationRunner,
    ) -> None:

        self._simulator = simulator

        self._runner = runner


    @property
    def name(self) -> str:

        return "SIMULATOR"

    def configure(
        self,
        waypoints: list[dict],
    ) -> None:
        """
        Configura técnicamente la ruta
        que ejecutará el simulador.
        """

        try:

            self._simulator.load_route(
                waypoints
            )

        except DroneSimulatorError as exc:

            raise MissionControllerError(
                "No fue posible configurar "
                f"la misión simulada: {exc}"
            ) from exc
    
    def initialize(
        self
    ) -> DroneState:
        """
        Inicializa técnicamente la misión simulada.

        Todavía no inicia el worker periódico.
        """

        try:

            return self._simulator.start()

        except DroneSimulatorError as exc:

            raise MissionControllerError(
                f"No fue posible iniciar "
                f"la misión simulada: {exc}"
            ) from exc


    def start(
        self,
        interval_seconds: float = 0.5,
    ) -> dict:
        """
        Inicia la ejecución periódica
        del simulador.
        """

        try:

            return self._runner.start(
                interval_seconds
            )

        except SimulationRunnerError as exc:

            raise MissionControllerError(
                str(exc)
            ) from exc


    def pause(
        self
    ) -> dict:
        """
        Detiene temporalmente el worker.

        No modifica la posición ni resetea
        el DroneSimulator.
        """

        return self._runner.stop()


    def resume(
        self,
        interval_seconds: float = 0.5,
    ) -> dict:
        """
        Reanuda la ejecución automática.
        """

        runtime = (
            self._runner.status()
        )


        if runtime["auto_running"]:

            raise MissionControllerError(
                "La misión ya se encuentra ejecutándose."
            )


        if not runtime["simulator_running"]:

            raise MissionControllerError(
                "La misión simulada ya no "
                "se encuentra en ejecución."
            )


        try:

            return self._runner.start(
                interval_seconds
            )

        except SimulationRunnerError as exc:

            raise MissionControllerError(
                str(exc)
            ) from exc


    def status(
        self
    ) -> dict:
        """
        Devuelve el estado de misión normalizado.

        Los detalles internos de SimulationRunner
        no se exponen fuera del controlador.
        """

        runtime = (
            self._runner.status()
        )


        running = bool(
            runtime.get(
                "auto_running",
                False
            )
        )


        execution_active = bool(
            runtime.get(
                "simulator_running",
                False
            )
        )


        paused = (
            execution_active
            and
            not running
        )


        return {
            "running":
                running,

            "paused":
                paused,

            "last_error":
                runtime.get(
                    "last_error"
                ),
        }