from __future__ import annotations

from drone.dji_backend import (
    DJIBackend,
    DJIBackendError,
)
from drone.state import DroneState


class DJIProviderError(RuntimeError):
    """
    Error específico del proveedor DJI utilizado
    por la aplicación.
    """

    pass


class DJIProvider:
    """
    Adapter entre DroneProvider y un backend DJI.

    DJIProvider no conoce el mecanismo real de
    comunicación utilizado debajo.
    """

    def __init__(
        self,
        backend: DJIBackend,
    ) -> None:

        if not isinstance(
            backend,
            DJIBackend
        ):

            raise DJIProviderError(
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


    def connect(
        self
    ) -> DroneState:

        try:

            return self._backend.connect()

        except DJIBackendError as exc:

            raise DJIProviderError(
                "No fue posible conectar "
                f"mediante el backend "
                f"{self._backend.name}: {exc}"
            ) from exc


    def disconnect(
        self
    ) -> DroneState:

        try:

            return self._backend.disconnect()

        except DJIBackendError as exc:

            raise DJIProviderError(
                "No fue posible desconectar "
                f"mediante el backend "
                f"{self._backend.name}: {exc}"
            ) from exc


    def get_state(
        self
    ) -> DroneState:

        try:

            return self._backend.get_state()

        except DJIBackendError as exc:

            raise DJIProviderError(
                "No fue posible obtener "
                f"el estado DJI: {exc}"
            ) from exc