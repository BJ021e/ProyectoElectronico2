from InterfazInit import app

from services.spectral_index_product_service import (
    InvalidSpectralIndexSourceError,
    SpectralIndexProductAlreadyExistsError,
    SpectralIndexProductError,
    SpectralIndexProductService,
)


def client():

    app.config["TESTING"] = True

    return app.test_client()


def test_generate_spectral_index_returns_created(
    monkeypatch,
):

    monkeypatch.setattr(
        SpectralIndexProductService,
        "generate_index",
        lambda **kwargs: {
            "id": 50,
            "campaign_id": 1,
            "product_type": "NDVI",
            "name": "NDVI",
        },
    )

    response = client().post(
        (
            "/api/geospatial-products/"
            "10/spectral-indices/NDVI"
        )
    )

    assert response.status_code == 201

    payload = response.get_json()

    assert payload["ok"] is True

    assert (
        payload["product"][
            "product_type"
        ]
        == "NDVI"
    )


def test_generate_spectral_index_returns_conflict_when_duplicate(
    monkeypatch,
):

    def raise_duplicate(
        **kwargs,
    ):
        raise (
            SpectralIndexProductAlreadyExistsError(
                "NDVI ya existe."
            )
        )

    monkeypatch.setattr(
        SpectralIndexProductService,
        "generate_index",
        raise_duplicate,
    )

    response = client().post(
        (
            "/api/geospatial-products/"
            "10/spectral-indices/NDVI"
        )
    )

    assert response.status_code == 409

    payload = response.get_json()

    assert payload["ok"] is False


def test_generate_spectral_index_rejects_invalid_source(
    monkeypatch,
):

    def raise_invalid(
        **kwargs,
    ):
        raise InvalidSpectralIndexSourceError(
            "Fuente inválida."
        )

    monkeypatch.setattr(
        SpectralIndexProductService,
        "generate_index",
        raise_invalid,
    )

    response = client().post(
        (
            "/api/geospatial-products/"
            "20/spectral-indices/NDRE"
        )
    )

    assert response.status_code == 400


def test_generate_spectral_index_handles_processing_error(
    monkeypatch,
):

    def raise_error(
        **kwargs,
    ):
        raise SpectralIndexProductError(
            "Error calculando índice."
        )

    monkeypatch.setattr(
        SpectralIndexProductService,
        "generate_index",
        raise_error,
    )

    response = client().post(
        (
            "/api/geospatial-products/"
            "20/spectral-indices/GNDVI"
        )
    )

    assert response.status_code == 422