import pytest

from config import Config
from geospatial import (
    MockPhotogrammetryBackend,
)
from services.photogrammetry_backend_factory import (
    PhotogrammetryBackendConfigurationError,
    PhotogrammetryBackendFactory,
)


def test_factory_creates_mock_backend(
    monkeypatch,
):

    monkeypatch.setattr(
        Config,
        "PHOTOGRAMMETRY_BACKEND",
        "MOCK",
    )

    backend = (
        PhotogrammetryBackendFactory
        .create()
    )

    assert isinstance(
        backend,
        MockPhotogrammetryBackend,
    )

    assert backend.name == "MOCK"


def test_factory_rejects_unknown_backend():

    with pytest.raises(
        PhotogrammetryBackendConfigurationError
    ):
        (
            PhotogrammetryBackendFactory
            .create(
                "UNKNOWN"
            )
        )