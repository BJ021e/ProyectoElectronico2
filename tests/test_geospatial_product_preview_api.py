from pathlib import Path

from InterfazInit import app

from services.geospatial_product_service import (
    GeospatialProductService,
)

from services.image_ingestion_service import (
    ImageIngestionService,
)

from services.raster_preview_service import (
    InvalidRasterPreviewError,
    RasterPreviewService,
)


def client():

    app.config["TESTING"] = True

    return app.test_client()


def test_product_preview_returns_png(
    monkeypatch,
):

    monkeypatch.setattr(
        GeospatialProductService,
        "get_product",
        lambda product_id: {
            "id": product_id,
            "storage_path": (
                "campaigns/1/"
                "products/mock.tif"
            ),
            "product_type": (
                "ORTHOMOSAIC_RGB"
            ),
        },
    )

    monkeypatch.setattr(
        ImageIngestionService,
        "resolve_managed_path",
        lambda storage_path: Path(
            "mock.tif"
        ),
    )

    png_bytes = (
        b"\x89PNG\r\n\x1a\n"
        b"preview"
    )

    monkeypatch.setattr(
        RasterPreviewService,
        "render_png",
        lambda **kwargs: png_bytes,
    )

    response = client().get(
        (
            "/api/geospatial-products/"
            "10/preview.png"
        )
    )

    assert response.status_code == 200

    assert (
        response.content_type
        == "image/png"
    )

    assert (
        response.data
        == png_bytes
    )


def test_product_preview_returns_404_when_product_does_not_exist(
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
            "999999/preview.png"
        )
    )

    assert response.status_code == 404


def test_product_preview_rejects_invalid_raster(
    monkeypatch,
):

    monkeypatch.setattr(
        GeospatialProductService,
        "get_product",
        lambda product_id: {
            "id": product_id,
            "storage_path": (
                "campaigns/1/"
                "products/invalid.tif"
            ),
            "product_type": (
                "ORTHOMOSAIC_RGB"
            ),
        },
    )

    monkeypatch.setattr(
        ImageIngestionService,
        "resolve_managed_path",
        lambda storage_path: Path(
            "invalid.tif"
        ),
    )

    def raise_invalid_preview(
        **kwargs,
    ):
        raise InvalidRasterPreviewError(
            "Ráster inválido."
        )

    monkeypatch.setattr(
        RasterPreviewService,
        "render_png",
        raise_invalid_preview,
    )

    response = client().get(
        (
            "/api/geospatial-products/"
            "15/preview.png"
        )
    )

    assert response.status_code == 422

    payload = response.get_json()

    assert payload["error"] is True
    
def test_product_preview_passes_display_mode(
    monkeypatch,
):

    monkeypatch.setattr(
        GeospatialProductService,
        "get_product",
        lambda product_id: {
            "id": product_id,
            "storage_path": (
                "campaigns/1/"
                "products/mock.tif"
            ),
            "product_type": (
                "ORTHOMOSAIC_MULTISPECTRAL"
            ),
        },
    )

    monkeypatch.setattr(
        ImageIngestionService,
        "resolve_managed_path",
        lambda storage_path: Path(
            "mock.tif"
        ),
    )

    received = {}

    def render_png(
        **kwargs,
    ):

        received.update(
            kwargs
        )

        return (
            b"\x89PNG\r\n\x1a\n"
            b"preview"
        )

    monkeypatch.setattr(
        RasterPreviewService,
        "render_png",
        render_png,
    )

    response = client().get(
        (
            "/api/geospatial-products/"
            "10/preview.png?mode=nir"
        )
    )

    assert response.status_code == 200

    assert (
        received["display_mode"]
        == "NIR"
    )