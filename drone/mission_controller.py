from __future__ import annotations

from typing import Protocol, runtime_checkable

from drone.state import DroneState


class MissionControllerError(RuntimeError):
    """
    Error producido durante el control técnico
    de una misión.
    """

    pass


@runtime_checkable
class MissionController(Protocol):
    """
    Contrato para componentes capaces de controlar
    técnicamente la ejecución de una misión.

    No conoce Flights, base de datos ni persistencia.
    """

    @property
    def name(self) -> str:
        """
        Nombre identificador del controlador.
        """
        ...


    def initialize(self) -> DroneState:
        """
        Inicializa técnicamente la misión y devuelve
        el estado inicial del vehículo.

        No inicia todavía el loop de ejecución.
        """
        ...


    def start(
        self,
        interval_seconds: float = 0.5,
    ) -> dict:
        """
        Inicia la ejecución continua de la misión.
        """
        ...


    def pause(self) -> dict:
        """
        Pausa temporalmente la ejecución.
        """
        ...


    def resume(
        self,
        interval_seconds: float = 0.5,
    ) -> dict:
        """
        Reanuda una misión previamente pausada.
        """
        ...


    def status(self) -> dict:
        """
        Devuelve el estado técnico del controlador.
        """
        ...