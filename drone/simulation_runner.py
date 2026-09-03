from __future__ import annotations

from collections.abc import Callable
from threading import (
    Event,
    RLock,
    Thread,
    current_thread,
)

from drone.simulator import (
    DroneSimulator,
    DroneSimulatorError,
)
from drone.state import DroneState


class SimulationRunnerError(RuntimeError):
    """
    Error de configuración o ejecución del
    mecanismo automático de simulación.
    """

    pass


class SimulationRunner:
    """
    Ejecuta periódicamente un DroneSimulator
    en un thread independiente.

    No conoce Flights, Routes, base de datos
    ni servicios de persistencia.
    """

    def __init__(
        self,
        simulator: DroneSimulator,
        on_state: Callable[
            [DroneState, bool],
            None
        ],
    ) -> None:

        self._simulator = simulator

        self._on_state = on_state

        self._lock = RLock()

        self._thread: Thread | None = None

        self._stop_event = Event()

        self._interval: float = 1.0

        self._last_error: str | None = None


    def _worker(
        self,
        stop_event: Event,
        interval: float,
    ) -> None:
        """
        Hace avanzar periódicamente el simulador
        y comunica cada nuevo estado mediante
        el callback on_state.
        """

        try:

            while True:

                should_stop = (
                    stop_event.wait(
                        interval
                    )
                )


                if should_stop:
                    break


                if not self._simulator.is_running:
                    break


                try:

                    state = (
                        self._simulator.advance()
                    )

                except DroneSimulatorError as exc:

                    with self._lock:

                        self._last_error = (
                            str(exc)
                        )

                    break


                simulator_still_running = (
                    self._simulator.is_running
                )


                try:

                    self._on_state(
                        state,
                        simulator_still_running,
                    )

                except Exception as exc:

                    #Esta excepción procede del callback
                    #de aplicación, no del simulador.

                    with self._lock:

                        self._last_error = (
                            str(exc)
                        )

                    break


                if not simulator_still_running:
                    break


        finally:

            with self._lock:

                if (
                    self._thread
                    is current_thread()
                ):

                    self._thread = None


    def start(
        self,
        interval_seconds: float = 1.0,
    ) -> dict:
        """
        Inicia la ejecución automática.
        """

        try:

            interval_seconds = float(
                interval_seconds
            )

        except (
            TypeError,
            ValueError,
        ) as exc:

            raise SimulationRunnerError(
                "interval_seconds debe ser numérico."
            ) from exc


        if interval_seconds <= 0:

            raise SimulationRunnerError(
                "interval_seconds debe ser mayor que 0."
            )


        with self._lock:

            if not self._simulator.is_running:

                raise SimulationRunnerError(
                    "El simulador debe estar iniciado "
                    "antes de activar el avance automático."
                )


            if (
                self._thread is not None
                and
                self._thread.is_alive()
            ):

                raise SimulationRunnerError(
                    "La simulación automática "
                    "ya está ejecutándose."
                )


            self._interval = (
                interval_seconds
            )

            self._last_error = None

            self._stop_event = Event()


            thread = Thread(
                target=self._worker,
                args=(
                    self._stop_event,
                    self._interval,
                ),
                name="DroneSimulatorWorker",
                daemon=True,
            )


            self._thread = thread


            thread.start()


        return self.status()


    def stop(self) -> dict:
        """
        Detiene únicamente el worker automático.

        No resetea ni modifica la posición actual
        del DroneSimulator.
        """

        with self._lock:

            thread = self._thread

            stop_event = self._stop_event


        if (
            thread is None
            or
            not thread.is_alive()
        ):

            return self.status()


        stop_event.set()


        if thread is not current_thread():

            thread.join(
                timeout=2.0
            )


        return self.status()


    def status(self) -> dict:
        """
        Devuelve el estado actual del runner.
        """

        with self._lock:

            thread = self._thread

            auto_running = (
                thread is not None
                and
                thread.is_alive()
            )


            return {
                "auto_running":
                    auto_running,

                "simulator_running":
                    self._simulator.is_running,

                "interval_seconds":
                    self._interval,

                "last_error":
                    self._last_error,
            }