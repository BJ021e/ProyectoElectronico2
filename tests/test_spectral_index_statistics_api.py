from pathlib import Path

from InterfazInit import app

from services.geospatial_product_service import (
    GeospatialProductService,
)

from services.image_ingestion_service import (
    ImageIngestionService,
)

from services.spectral_index_visualization_service import (
    SpectralIndexVisualizationService,
)


def client():

    app.config["TESTING"] = True

    return app.test_client()


def test_spectral_statistics_are_returned(
    monkeypatch,
):

    monkeypatch.setattr(
        GeospatialProductService,
        "get_product",
        lambda product_id: {
            "id": product_id,
            "product_type": "NDVI",
            "storage_path": (
                "campaigns/1/"
                "products/ndvi.tif"
            ),
        },
    )

    monkeypatch.setattr(
        ImageIngestionService,
        "resolve_managed_path",
        lambda storage_path: Path(
            "ndvi.tif"
        ),
    )

    monkeypatch.setattr(
        SpectralIndexVisualizationService,
        "calculate_statistics",
        lambda **kwargs: {
            "index": "NDVI",
            "minimum": -0.2,
            "mean": 0.4,
            "maximum": 0.8,
            "valid_pixel_count": 100,
            "range": {
                "minimum": -1.0,
                "maximum": 1.0,
            },
        },
    )

    response = client().get(
        (
            "/api/geospatial-products/"
            "5/statistics"
        )
    )

    assert response.status_code == 200

    payload = response.get_json()

    assert payload["ok"] is True

    assert (
        payload["statistics"][
            "mean"
        ]
        == 0.4
    )

    assert (
        payload["statistics"][
            "index"
        ]
        == "NDVI"
    )


def test_spectral_statistics_reject_non_index_product(
    monkeypatch,
):

    monkeypatch.setattr(
        GeospatialProductService,
        "get_product",
        lambda product_id: {
            "id": product_id,
            "product_type": (
                "ORTHOMOSAIC_MULTISPECTRAL"
            ),
            "storage_path": (
                "campaigns/1/"
                "products/ortho.tif"
            ),
        },
    )

    response = client().get(
        (
            "/api/geospatial-products/"
            "5/statistics"
        )
    )

    assert response.status_code == 400


def test_spectral_statistics_return_404_for_missing_product(
    monkeypatch,
):

    monkeypatch.setattr(
        GeospatialProductService,
        "get_product",
        lambda product_id: None,
    )

    response = client().get(
        (
            "/api/geospatial-products/"
            "999999/statistics"
        )
    )

    assert response.status_code == 404