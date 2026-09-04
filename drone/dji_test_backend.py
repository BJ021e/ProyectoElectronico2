from __future__ import annotations

from collections.abc import Callable
from threading import (
    Event,
    RLock,
    Thread,
    current_thread,
)

from drone.dji_backend import DJIBackendError
from drone.state import DroneState


class DJITestBackend:
    """
    Test double del contrato DJIBackend.

    Su única finalidad es comprobar que la rama
    arquitectónica DJI funciona de extremo a extremo
    sin utilizar DroneSimulator ni hardware real.

    No debe utilizarse como integración DJI real.
    """

    def __init__(
        self,
        *,
        on_state: Callable[
            [DroneState, bool],
            None,
        ] | None = None,
        interval_seconds: float = 0.05,
    ) -> None:

        interval_seconds = float(
            interval_seconds
        )

        if interval_seconds <= 0:

            raise ValueError(
                "interval_seconds debe "
                "ser mayor que 0."
            )


        self._lock = RLock()

        self._on_state = on_state

        self._interval_seconds = (
            interval_seconds
        )


        self._connected = False

        self._aircraft_online = False


        self._waypoints: list[dict] = []

        self._index: int | None = None


        self._running = False

        self._paused = False

        self._last_error: str | None = None


        self._thread: Thread | None = None

        self._stop_event = Event()


        self._state = DroneState(
            provider="DJI",
            connected=False,
            aircraft_online=False,
        )


    @property
    def name(
        self
    ) -> str:

        return "TEST_DOUBLE"


    def connect(
        self
    ) -> DroneState:

        with self._lock:

            self._connected = True

            self._aircraft_online = True


            self._state = DroneState(
                provider="DJI",
                connected=True,
                aircraft_online=True,
            )


            return self._state


    def disconnect(
        self
    ) -> DroneState:

        self._stop_worker()


        with self._lock:

            self._connected = False

            self._aircraft_online = False

            self._running = False

            self._paused = False


            self._state = DroneState(
                provider="DJI",
                connected=False,
                aircraft_online=False,
            )


            return self._state


    def get_state(
        self
    ) -> DroneState:

        with self._lock:

            return self._state


    def configure_mission(
        self,
        waypoints: list[dict],
    ) -> None:

        if not waypoints:

            raise DJIBackendError(
                "La misión de prueba "
                "no contiene waypoints."
            )


        normalized = []


        for waypoint in waypoints:

            if (
                "latitude" not in waypoint
                or
                "longitude" not in waypoint
            ):

                raise DJIBackendError(
                    "Cada waypoint debe contener "
                    "latitude y longitude."
                )


            normalized.append(
                dict(waypoint)
            )


        normalized.sort(
            key=lambda waypoint:
                waypoint.get(
                    "sequence",
                    0,
                )
        )


        with self._lock:

            if (
                self._running
                or
                self._paused
            ):

                raise DJIBackendError(
                    "No se puede reemplazar "
                    "una misión en ejecución."
                )


            self._waypoints = normalized

            self._index = None

            self._last_error = None


    def initialize_mission(
        self
    ) -> DroneState:

        with self._lock:

            if not self._connected:

                raise DJIBackendError(
                    "El backend DJI de prueba "
                    "no está conectado."
                )


            if not self._waypoints:

                raise DJIBackendError(
                    "No existe una misión "
                    "configurada."
                )


            self._index = 0

            self._running = False

            self._paused = False


            self._state = (
                self._build_waypoint_state(
                    index=0,
                    final=False,
                )
            )


            return self._state


    def start_mission(
        self
    ) -> dict:

        with self._lock:

            self._validate_execution_ready()


            if self._running:

                raise DJIBackendError(
                    "La misión de prueba "
                    "ya está ejecutándose."
                )


            if (
                self._index is None
            ):

                raise DJIBackendError(
                    "La misión todavía "
                    "no fue inicializada."
                )


            #
            # Caso excepcional: ruta de un waypoint.
            #
            if len(self._waypoints) == 1:

                self._state = (
                    self._build_waypoint_state(
                        index=0,
                        final=True,
                    )
                )

                callback = self._on_state

                state = self._state

            else:

                callback = None

                state = None


                self._running = True

                self._paused = False

                self._last_error = None


                self._start_worker_locked()


        if (
            callback is not None
            and
            state is not None
        ):

            callback(
                state,
                False,
            )


        return self.mission_status()


    def pause_mission(
        self
    ) -> dict:

        with self._lock:

            if not self._running:

                raise DJIBackendError(
                    "La misión DJI de prueba "
                    "no está ejecutándose."
                )


            self._running = False

            self._paused = True


        self._stop_worker()


        return self.mission_status()


    def resume_mission(
        self
    ) -> dict:

        with self._lock:

            if not self._paused:

                raise DJIBackendError(
                    "La misión DJI de prueba "
                    "no está pausada."
                )


            self._validate_execution_ready()


            self._paused = False

            self._running = True

            self._last_error = None


            self._start_worker_locked()


        return self.mission_status()


    def mission_status(
        self
    ) -> dict:

        with self._lock:

            return {
                "running":
                    self._running,

                "paused":
                    self._paused,

                "last_error":
                    self._last_error,
            }

    def _copy_state_with_connectivity(
        self,
        *,
        connected: bool,
        aircraft_online: bool,
    ) -> DroneState:

        state = self._state


        return DroneState(
            provider="DJI",

            connected=connected,

            aircraft_online=aircraft_online,

            latitude=state.latitude,

            longitude=state.longitude,

            altitude=state.altitude,

            speed=state.speed,

            heading=state.heading,

            battery=state.battery,

            gps_sats=state.gps_sats,

            flight_mode=state.flight_mode,

            #
            # No es telemetría nueva.
            # Conservamos su timestamp.
            #
            recorded_at=state.recorded_at,
        )
        
    def simulate_transport_loss(
        self
    ) -> None:
        """
        Simula una pérdida inesperada del transporte.

        La misión técnica puede continuar internamente,
        pero dejan de emitirse estados hacia la aplicación.
        """

        with self._lock:

            if not self._connected:

                raise DJIBackendError(
                    "El transporte DJI de prueba "
                    "ya está desconectado."
                )


            self._connected = False

            self._aircraft_online = False


            self._state = (
                self._copy_state_with_connectivity(
                    connected=False,
                    aircraft_online=False,
                )
            )
    
    def simulate_transport_recovery(
        self
    ) -> None:
        """
        Recupera el transporte y sincroniza con la
        aplicación el último estado conocido.
        """

        with self._lock:

            if self._connected:

                raise DJIBackendError(
                    "El transporte DJI de prueba "
                    "ya está conectado."
                )


            self._connected = True

            self._aircraft_online = True


            self._state = (
                self._copy_state_with_connectivity(
                    connected=True,
                    aircraft_online=True,
                )
            )


            state = self._state

            callback = self._on_state

            mission_running = (
                self._running
            )


            has_telemetry = (
                state.latitude is not None
                and
                state.longitude is not None
            )


        #
        # Sincronización fuera del lock.
        #
        if (
            callback is not None
            and
            has_telemetry
        ):

            callback(
                state,
                mission_running,
            )
                
    def _validate_execution_ready(
        self
    ) -> None:

        if not self._connected:

            raise DJIBackendError(
                "El backend DJI de prueba "
                "no está conectado."
            )


        if not self._waypoints:

            raise DJIBackendError(
                "No existe una misión "
                "configurada."
            )


    def _start_worker_locked(
        self
    ) -> None:

        self._stop_event = Event()


        thread = Thread(
            target=self._worker,
            args=(
                self._stop_event,
            ),
            name="DJITestBackendWorker",
            daemon=True,
        )


        self._thread = thread


        thread.start()


    def _stop_worker(
        self
    ) -> None:

        with self._lock:

            thread = self._thread

            stop_event = self._stop_event


        stop_event.set()


        if (
            thread is not None
            and
            thread is not current_thread()
        ):

            thread.join(
                timeout=2.0
            )


    def _worker(
        self,
        stop_event: Event,
    ) -> None:

        try:

            while True:

                if stop_event.wait(
                    self._interval_seconds
                ):

                    break


                with self._lock:

                    if not self._running:

                        break


                    if self._index is None:

                        raise DJIBackendError(
                            "La misión no fue "
                            "inicializada."
                        )


                    next_index = (
                        self._index + 1
                    )


                    if (
                        next_index
                        >=
                        len(self._waypoints)
                    ):

                        break


                    self._index = (
                        next_index
                    )


                    final = (
                        next_index
                        ==
                        len(self._waypoints) - 1
                    )


                    if final:

                        self._running = False

                        self._paused = False


                    state = (
                        self._build_waypoint_state(
                            index=next_index,
                            final=final,
                        )
                    )


                    self._state = state

                    callback = (
                        self._on_state
                    )
                    
                    transport_connected = (
                        self._connected
                    )


                if (
                    callback is not None
                    and
                    transport_connected
                ):

                    callback(
                        state,
                        not final,
                    )


                if final:

                    break


        except Exception as exc:

            with self._lock:

                self._running = False

                self._paused = False

                self._last_error = str(
                    exc
                )


        finally:

            with self._lock:

                if (
                    self._thread
                    is current_thread()
                ):

                    self._thread = None


    def _build_waypoint_state(
        self,
        *,
        index: int,
        final: bool,
    ) -> DroneState:

        waypoint = (
            self._waypoints[index]
        )


        speed = (
            0.0
            if final
            else float(
                waypoint.get(
                    "speed"
                )
                or 0.0
            )
        )


        heading_value = (
            waypoint.get(
                "heading"
            )
        )


        heading = (
            None
            if heading_value is None
            else float(
                heading_value
            )
        )


        return DroneState(
            provider="DJI",

            connected=self._connected,

            aircraft_online=(
                self._aircraft_online
            ),

            latitude=float(
                waypoint["latitude"]
            ),

            longitude=float(
                waypoint["longitude"]
            ),

            altitude=float(
                waypoint.get(
                    "altitude"
                )
                or 0.0
            ),

            speed=speed,

            heading=heading,

            battery=100.0,

            gps_sats=None,

            flight_mode=(
                "HOLD"
                if final
                else "AUTO"
            ),
        )