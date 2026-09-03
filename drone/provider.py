from __future__ import annotations

from typing import Protocol, runtime_checkable

from drone.state import DroneState


@runtime_checkable
class DroneProvider(Protocol):
    """
    Contrato que debe cumplir cualquier fuente
    de datos de dron utilizada por la aplicación.
    """

    @property
    def name(self) -> str:
        """
        Nombre identificador del proveedor.
        """
        ...


    def get_state(self) -> DroneState:
        """
        Devuelve el estado más reciente del dron
        utilizando el formato normalizado DroneState.
        """
        ...
    
    def connect(self) -> DroneState:
        """
        Establece la conexión lógica con el proveedor
        y devuelve su estado normalizado.
        """
        ...


    def disconnect(self) -> DroneState:
        """
        Cierra la conexión lógica con el proveedor
        y devuelve su estado normalizado.
        """
        ...