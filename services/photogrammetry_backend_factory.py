from __future__ import annotations

from config import Config

from geospatial.metashape_backend import (
    MetashapeBackend,
)

from geospatial import (
    MockPhotogrammetryBackend,
    PhotogrammetryBackend,
)

class PhotogrammetryBackendConfigurationError(
    Exception
):
    """
    El backend de fotogrametría solicitado no existe
    o todavía no está implementado.
    """
    pass


class PhotogrammetryBackendFactory:

    @staticmethod
    def create(
        backend_name: str | None = None,
    ) -> PhotogrammetryBackend:

        selected = (
            backend_name
            if backend_name is not None
            else Config.PHOTOGRAMMETRY_BACKEND
        )

        if (
            not isinstance(selected, str)
            or not selected.strip()
        ):
            raise (
                PhotogrammetryBackendConfigurationError(
                    "No se configuró un backend "
                    "de fotogrametría válido."
                )
            )

        normalized = (
            selected
            .strip()
            .upper()
        )

        if normalized == "MOCK":

            return MockPhotogrammetryBackend(
                delay_seconds=(
                    Config
                    .MOCK_PHOTOGRAMMETRY_DELAY_SECONDS
                )
            )
        
        if normalized == "METASHAPE":

            return MetashapeBackend(
                executable_path=(
                    Config.METASHAPE_EXECUTABLE
                )
            )

        raise PhotogrammetryBackendConfigurationError(
            "Backend de fotogrametría "
            f"no soportado: {normalized}."
        )