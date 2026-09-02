from __future__ import annotations

from math import atan2, cos, degrees, radians, sin
from typing import Any

from drone.state import DroneState


class DroneSimulatorError(Exception):
    """
    Error producido durante la operación
    del simulador de dron.
    """

    pass


class DroneSimulator:
    """
    Proveedor de dron simulado.

    Permite cargar una secuencia de waypoints y avanzar
    progresivamente por ellos generando DroneState.

    No depende de DJI, Flask ni SQLAlchemy.
    """

    PROVIDER_NAME = "SIMULATOR"

    def __init__(
        self,
        *,
        default_altitude: float = 30.0,
        default_speed: float = 4.0,
        gps_sats: int = 18,
        initial_battery: float = 100.0,
        step_fraction: float = 0.20,
        battery_drop_per_step: float = 0.05,
    ) -> None:

        if default_altitude < 0:
            raise ValueError(
                "La altitud predeterminada no puede ser negativa."
            )

        if default_speed < 0:
            raise ValueError(
                "La velocidad predeterminada no puede ser negativa."
            )

        if gps_sats < 0:
            raise ValueError(
                "La cantidad de satélites no puede ser negativa."
            )

        if not (0 <= initial_battery <= 100):
            raise ValueError(
                "La batería inicial debe estar entre 0 y 100."
            )

        if not (0 < step_fraction <= 1):
            raise ValueError(
                "step_fraction debe estar entre 0 y 1."
            )

        if battery_drop_per_step < 0:
            raise ValueError(
                "battery_drop_per_step no puede ser negativo."
            )

        self._default_altitude = default_altitude
        self._default_speed = default_speed
        self._gps_sats = gps_sats

        self._initial_battery = initial_battery
        self._battery = initial_battery

        self._step_fraction = step_fraction
        self._battery_drop_per_step = (
            battery_drop_per_step
        )

        self._connected = False
        self._aircraft_online = False
        self._running = False

        self._route: list[dict[str, Any]] = []

        self._segment_index = 0
        self._segment_progress = 0.0

        self._latitude: float | None = None
        self._longitude: float | None = None
        self._altitude: float | None = None
        self._speed: float | None = None
        self._heading: float | None = None

        self._flight_mode: str | None = None


    @property
    def name(self) -> str:
        return self.PROVIDER_NAME


    @property
    def is_running(self) -> bool:
        return self._running


    @property
    def waypoint_count(self) -> int:
        return len(self._route)


    @staticmethod
    def _calculate_bearing(
        start_latitude: float,
        start_longitude: float,
        end_latitude: float,
        end_longitude: float,
    ) -> float:
        """
        Calcula el rumbo inicial aproximado entre
        dos coordenadas geográficas.
        """

        lat1 = radians(start_latitude)
        lat2 = radians(end_latitude)

        delta_lon = radians(
            end_longitude - start_longitude
        )

        x = sin(delta_lon) * cos(lat2)

        y = (
            cos(lat1) * sin(lat2)
            - sin(lat1)
            * cos(lat2)
            * cos(delta_lon)
        )

        bearing = degrees(
            atan2(x, y)
        )

        return (
            bearing + 360
        ) % 360


    @staticmethod
    def _validate_coordinate(
        latitude: float,
        longitude: float,
    ) -> None:

        if not (-90 <= latitude <= 90):
            raise DroneSimulatorError(
                "La latitud debe estar entre -90 y 90."
            )

        if not (-180 <= longitude <= 180):
            raise DroneSimulatorError(
                "La longitud debe estar entre -180 y 180."
            )


    def load_route(
        self,
        waypoints: list[dict],
    ) -> None:
        """
        Carga una ruta previamente definida.

        La ruta debe contener como mínimo
        dos waypoints.
        """

        if len(waypoints) < 2:
            raise DroneSimulatorError(
                "El simulador necesita al menos 2 waypoints."
            )

        normalized: list[dict[str, Any]] = []


        sorted_waypoints = sorted(
            waypoints,
            key=lambda waypoint: waypoint.get(
                "sequence",
                0
            )
        )


        for index, waypoint in enumerate(
            sorted_waypoints,
            start=1
        ):

            try:

                latitude = float(
                    waypoint["latitude"]
                )

                longitude = float(
                    waypoint["longitude"]
                )

            except (
                KeyError,
                TypeError,
                ValueError,
            ) as exc:

                raise DroneSimulatorError(
                    f"Waypoint {index} contiene "
                    "coordenadas inválidas."
                ) from exc


            self._validate_coordinate(
                latitude,
                longitude
            )


            altitude_value = waypoint.get(
                "altitude"
            )

            speed_value = waypoint.get(
                "speed"
            )


            altitude = (
                float(altitude_value)
                if altitude_value is not None
                else self._default_altitude
            )


            speed = (
                float(speed_value)
                if speed_value is not None
                else self._default_speed
            )


            if altitude < 0:
                raise DroneSimulatorError(
                    f"Waypoint {index} tiene "
                    "una altitud inválida."
                )


            if speed < 0:
                raise DroneSimulatorError(
                    f"Waypoint {index} tiene "
                    "una velocidad inválida."
                )


            normalized.append({
                "sequence": waypoint.get(
                    "sequence",
                    index
                ),

                "latitude": latitude,
                "longitude": longitude,
                "altitude": altitude,
                "speed": speed,
            })


        self._route = normalized

        self._segment_index = 0
        self._segment_progress = 0.0


        first = self._route[0]

        second = self._route[1]


        self._latitude = first["latitude"]
        self._longitude = first["longitude"]
        self._altitude = first["altitude"]

        self._speed = 0.0

        self._heading = (
            self._calculate_bearing(
                first["latitude"],
                first["longitude"],
                second["latitude"],
                second["longitude"],
            )
        )


        if self._connected:
            self._flight_mode = "STANDBY"


    def connect(self) -> DroneState:
        """
        Simula que el proveedor y la aeronave
        están disponibles.
        """

        self._connected = True
        self._aircraft_online = True

        self._flight_mode = "STANDBY"

        return self.get_state()


    def disconnect(self) -> DroneState:
        """
        Simula la pérdida o cierre de conexión.
        """

        self._running = False

        self._connected = False
        self._aircraft_online = False

        self._flight_mode = None

        return self.get_state()


    def start(self) -> DroneState:
        """
        Inicia el desplazamiento simulado
        sobre la ruta cargada.
        """

        if not self._connected:
            raise DroneSimulatorError(
                "El simulador no está conectado."
            )

        if not self._aircraft_online:
            raise DroneSimulatorError(
                "La aeronave simulada no está disponible."
            )

        if len(self._route) < 2:
            raise DroneSimulatorError(
                "No existe una ruta válida cargada."
            )

        self._running = True

        self._flight_mode = "AUTO"

        first = self._route[0]

        second = self._route[1]


        self._latitude = first["latitude"]
        self._longitude = first["longitude"]
        self._altitude = first["altitude"]

        self._speed = first["speed"]

        self._heading = (
            self._calculate_bearing(
                first["latitude"],
                first["longitude"],
                second["latitude"],
                second["longitude"],
            )
        )

        return self.get_state()


    def advance(self) -> DroneState:
        """
        Avanza una fracción del segmento actual.

        Cada llamada representa un paso del simulador.
        """

        if not self._running:
            raise DroneSimulatorError(
                "El simulador no está ejecutando una ruta."
            )


        start = self._route[
            self._segment_index
        ]

        end = self._route[
            self._segment_index + 1
        ]


        self._segment_progress += (
            self._step_fraction
        )


        progress = min(
            self._segment_progress,
            1.0
        )


        self._latitude = (
            start["latitude"]
            + (
                end["latitude"]
                - start["latitude"]
            )
            * progress
        )


        self._longitude = (
            start["longitude"]
            + (
                end["longitude"]
                - start["longitude"]
            )
            * progress
        )


        self._altitude = (
            start["altitude"]
            + (
                end["altitude"]
                - start["altitude"]
            )
            * progress
        )


        self._speed = end["speed"]


        self._heading = (
            self._calculate_bearing(
                start["latitude"],
                start["longitude"],
                end["latitude"],
                end["longitude"],
            )
        )


        self._battery = max(
            0.0,
            self._battery
            - self._battery_drop_per_step
        )


        if self._segment_progress >= 1.0:

            self._segment_index += 1

            self._segment_progress = 0.0

        if (
            self._segment_index
            >= len(self._route) - 1
        ):

            self._running = False

            self._speed = 0.0
            self._flight_mode = "HOLD"

            return self.get_state()


        next_start = self._route[
            self._segment_index
        ]

        next_end = self._route[
            self._segment_index + 1
        ]


        self._heading = (
            self._calculate_bearing(
                next_start["latitude"],
                next_start["longitude"],
                next_end["latitude"],
                next_end["longitude"],
            )
        )


        return self.get_state()


    def reset(self) -> DroneState:
        """
        Devuelve el simulador al inicio
        de la ruta cargada.
        """

        self._running = False

        self._segment_index = 0
        self._segment_progress = 0.0

        self._battery = (
            self._initial_battery
        )


        if self._route:

            first = self._route[0]

            self._latitude = (
                first["latitude"]
            )

            self._longitude = (
                first["longitude"]
            )

            self._altitude = (
                first["altitude"]
            )

            self._speed = 0.0


            if len(self._route) >= 2:

                second = self._route[1]

                self._heading = (
                    self._calculate_bearing(
                        first["latitude"],
                        first["longitude"],
                        second["latitude"],
                        second["longitude"],
                    )
                )


        self._flight_mode = (
            "STANDBY"
            if self._connected
            else None
        )

        return self.get_state()


    def get_state(self) -> DroneState:
        """
        Implementación del contrato DroneProvider.
        """

        if not self._aircraft_online:

            return DroneState(
                provider=self.name,
                connected=self._connected,
                aircraft_online=False,
            )


        return DroneState(
            provider=self.name,

            connected=self._connected,
            aircraft_online=self._aircraft_online,

            latitude=self._latitude,
            longitude=self._longitude,

            altitude=self._altitude,
            speed=self._speed,
            heading=self._heading,

            battery=self._battery,
            gps_sats=self._gps_sats,

            flight_mode=self._flight_mode,
        )
        