from __future__ import annotations

from threading import RLock

from drone.state import DroneState


class DJIProviderError(RuntimeError):
    """
    Error específico de la integración
    con un proveedor DJI.
    """

    pass


class DJIProvider:
    """
    Proveedor para una futura integración
    con hardware DJI real.

    En esta etapa todavía no existe un backend
    de comunicación DJI configurado.

    Por ello:

    - get_state() puede informar que el proveedor
      está desconectado;
    - connect() rechaza explícitamente la conexión;
    - no se generan datos de telemetría artificiales.
    """

    def __init__(
        self
    ) -> None:

        self._lock = RLock()

        self._connected = False

        self._aircraft_online = False


    @property
    def name(
        self
    ) -> str:

        return "DJI"


    def connect(
        self
    ) -> DroneState:
        """
        Intenta establecer conexión con DJI.

        Actualmente no existe un backend DJI real,
        por lo que la operación se rechaza
        explícitamente.
        """

        raise DJIProviderError(
            "DJIProvider todavía no tiene "
            "un backend DJI configurado."
        )


    def disconnect(
        self
    ) -> DroneState:
        """
        Deja al proveedor en estado desconectado.

        Esta operación es segura incluso si todavía
        no existe hardware DJI conectado.
        """

        with self._lock:

            self._connected = False

            self._aircraft_online = False


        return self.get_state()


    def get_state(
        self
    ) -> DroneState:
        """
        Devuelve el último estado conocido.

        Mientras no exista integración DJI real,
        los valores de telemetría permanecen None.
        """

        with self._lock:

            connected = (
                self._connected
            )

            aircraft_online = (
                self._aircraft_online
            )


        return DroneState(
            provider=self.name,

            connected=connected,

            aircraft_online=aircraft_online,

            latitude=None,
            longitude=None,

            altitude=None,
            speed=None,
            heading=None,

            battery=None,
            gps_sats=None,

            flight_mode=None,
        )