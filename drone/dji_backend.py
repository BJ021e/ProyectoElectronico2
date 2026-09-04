from __future__ import annotations

from typing import Protocol, runtime_checkable

from drone.state import DroneState


class DJIBackendError(RuntimeError):
    """
    Error producido por una implementación
    concreta del backend DJI.
    """

    pass


@runtime_checkable
class DJIBackend(Protocol):
    """
    Contrato entre la aplicación y el mecanismo
    concreto utilizado para comunicarse con DJI.

    Este contrato no conoce:

    - Flask;
    - FlightService;
    - TelemetryService;
    - SQLAlchemy;
    - base de datos.

    Una implementación futura podrá utilizar
    Cloud API, un bridge, OSDK u otro mecanismo.
    """

    @property
    def name(self) -> str:
        """
        Identifica la implementación concreta
        del backend.
        """
        ...


    def connect(self) -> DroneState:
        """
        Establece la comunicación con el sistema DJI
        y devuelve el estado normalizado inicial.
        """
        ...


    def disconnect(self) -> DroneState:
        """
        Cierra la comunicación con DJI y devuelve
        el estado normalizado resultante.
        """
        ...


    def get_state(self) -> DroneState:
        """
        Obtiene el estado más reciente de la aeronave
        en formato DroneState.
        """
        ...


    def configure_mission(
        self,
        waypoints: list[dict],
    ) -> None:
        """
        Configura o carga la misión que posteriormente
        será ejecutada por la aeronave.

        La representación definitiva hacia DJI
        será responsabilidad de la implementación.
        """
        ...


    def initialize_mission(self) -> DroneState:
        """
        Realiza la preparación técnica necesaria
        inmediatamente antes de ejecutar la misión.

        Devuelve el estado actual de la aeronave.
        """
        ...


    def start_mission(self) -> dict:
        """
        Ordena iniciar la misión configurada.
        """
        ...


    def pause_mission(self) -> dict:
        """
        Solicita la pausa de la misión actual.
        """
        ...


    def resume_mission(self) -> dict:
        """
        Solicita reanudar una misión pausada.
        """
        ...


    def mission_status(self) -> dict:
        """
        Devuelve el estado técnico de ejecución
        de la misión.
        """
        ...