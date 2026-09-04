from __future__ import annotations

from typing import (
    Protocol,
    runtime_checkable,
)

from geospatial.processing_types import (
    PhotogrammetryRequest,
    ProcessingResult,
)


class PhotogrammetryBackendError(Exception):
    """
    Error producido dentro de un backend de
    fotogrametría.
    """
    pass


class InvalidPhotogrammetryRequestError(
    PhotogrammetryBackendError
):
    """
    La solicitud no posee la información mínima
    necesaria para ejecutar el procesamiento.
    """
    pass


class PhotogrammetryBackendUnavailableError(
    PhotogrammetryBackendError
):
    """
    El backend existe en la aplicación pero no se
    encuentra disponible para ejecutar trabajos.
    """
    pass


@runtime_checkable
class PhotogrammetryBackend(Protocol):
    """
    Contrato común que deberán implementar los motores
    de fotogrametría.

    La aplicación no deberá depender directamente
    de ODM, Pix4D, Metashape u otro motor.
    """

    @property
    def name(self) -> str:
        ...

    def is_available(self) -> bool:
        ...

    def process(
        self,
        request: PhotogrammetryRequest,
    ) -> ProcessingResult:
        ...