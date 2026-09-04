from pathlib import Path

import cv2
import numpy as np
import pytest
import rasterio

from rasterio.transform import (
    from_origin,
)

from config import Config
from geospatial import (
    GeneratedRasterProduct,
    MockPhotogrammetryBackend,
    PhotogrammetryBackendError,
    ProcessingResult,
)
from models import (
    GeospatialProductType,
)
from services.campaign_service import (
    CampaignService,
)
from services.capture_service import (
    CaptureService,
)
from services.geospatial_product_service import (
    GeospatialProductService,
)
from services.image_ingestion_service import (
    ImageIngestionService,
)
from services.processing_job_service import (
    ProcessingJobService,
)
from services.processing_service import (
    InvalidCampaignProcessingError,
    ProcessingExecutionError,
    ProcessingService,
)


def configure_storage(
    tmp_path,
    monkeypatch,
):

    storage_root = (
        tmp_path
        / "managed"
    )

    monkeypatch.setattr(
        Config,
        "CAMPAIGN_STORAGE_ROOT",
        str(storage_root),
    )

    return storage_root


def create_test_tiff(
    path: Path,
    *,
    value: int = 1,
):

    data = np.full(
        (
            8,
            8,
        ),
        value,
        dtype=np.uint16,
    )

    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=8,
        height=8,
        count=1,
        dtype="uint16",
    ) as dataset:

        dataset.write(
            data,
            1,
        )


def create_ready_rgb_campaign(
    tmp_path,
):

    campaign = (
        CampaignService.create_campaign(
            name="Campaña RGB processing",
            sensor_type="RGB",
            sensor_model="RGB",
        )
    )

    capture = (
        CaptureService.create_capture(
            campaign_id=campaign["id"]
        )
    )

    source = (
        tmp_path
        / "input.jpg"
    )

    image = np.zeros(
        (
            8,
            8,
            3,
        ),
        dtype=np.uint8,
    )

    assert cv2.imwrite(
        str(source),
        image,
    )

    ImageIngestionService.ingest_file(
        capture_id=capture["id"],
        band="RGB",
        source_path=source,
    )

    return campaign


def create_ready_multispectral_campaign(
    tmp_path,
):

    campaign = (
        CampaignService.create_campaign(
            name="Campaña MS processing",
            sensor_type="MULTISPECTRAL",
            sensor_model="MicaSense RedEdge-3",
        )
    )

    capture = (
        CaptureService.create_capture(
            campaign_id=campaign["id"]
        )
    )

    bands = [
        ("BLUE", 1),
        ("GREEN", 2),
        ("RED", 3),
        ("NIR", 4),
        ("RED_EDGE", 5),
    ]

    for band, index in bands:

        source = (
            tmp_path
            / f"IMG_0001_{index}.tif"
        )

        create_test_tiff(
            source,
            value=index,
        )

        ImageIngestionService.ingest_file(
            capture_id=capture["id"],
            band=band,
            source_path=source,
        )

    return campaign


class UnavailableBackend:

    @property
    def name(self) -> str:
        return "UNAVAILABLE_TEST"

    def is_available(self) -> bool:
        return False

    def process(self, request):
        raise AssertionError(
            "process no debe ejecutarse"
        )


class FailingBackend:

    @property
    def name(self) -> str:
        return "FAILING_TEST"

    def is_available(self) -> bool:
        return True

    def process(self, request):
        raise PhotogrammetryBackendError(
            "Fallo controlado del backend"
        )


class PartialProductBackend:

    @property
    def name(self) -> str:
        return "PARTIAL_TEST"

    def is_available(self) -> bool:
        return True

    def process(self, request):

        output_dir = Path(
            request.output_dir
        )

        valid_path = (
            output_dir
            / "valid_dsm.tif"
        )

        data = np.ones(
            (
                8,
                8,
            ),
            dtype=np.float32,
        )

        with rasterio.open(
            valid_path,
            "w",
            driver="GTiff",
            width=8,
            height=8,
            count=1,
            dtype="float32",
            crs="EPSG:32718",
            transform=from_origin(
                280000.0,
                8668000.0,
                0.05,
                0.05,
            ),
        ) as dataset:

            dataset.write(
                data,
                1,
            )

        missing_path = (
            output_dir
            / "missing_ndvi.tif"
        )

        return ProcessingResult(
            backend=self.name,
            success=True,
            products=(
                GeneratedRasterProduct(
                    product_type=(
                        GeospatialProductType.DSM
                    ),
                    name="DSM válido",
                    path=str(valid_path),
                ),
                GeneratedRasterProduct(
                    product_type=(
                        GeospatialProductType.NDVI
                    ),
                    name="NDVI faltante",
                    path=str(missing_path),
                ),
            ),
        )


def test_process_rgb_campaign_end_to_end(
    tmp_path,
    monkeypatch,
):

    storage_root = configure_storage(
        tmp_path,
        monkeypatch,
    )

    campaign = (
        create_ready_rgb_campaign(
            tmp_path
        )
    )

    result = (
        ProcessingService.process_campaign(
            campaign_id=campaign["id"],
            backend=(
                MockPhotogrammetryBackend()
            ),
        )
    )

    assert (
        result["job"]["status"]
        == "COMPLETED"
    )

    assert result["input_file_count"] == 1

    assert len(
        result["products"]
    ) == 1

    product = result["products"][0]

    assert (
        product["product_type"]
        == "ORTHOMOSAIC_RGB"
    )

    assert (
        product["processing_job_id"]
        == result["job"]["id"]
    )

    assert (
        storage_root
        / product["storage_path"]
    ).exists()


def test_process_multispectral_campaign_end_to_end(
    tmp_path,
    monkeypatch,
):

    configure_storage(
        tmp_path,
        monkeypatch,
    )

    campaign = (
        create_ready_multispectral_campaign(
            tmp_path
        )
    )

    result = (
        ProcessingService.process_campaign(
            campaign_id=campaign["id"],
            backend=(
                MockPhotogrammetryBackend()
            ),
        )
    )

    assert (
        result["job"]["status"]
        == "COMPLETED"
    )

    assert result["input_file_count"] == 5

    assert (
        result["products"][0]
        ["product_type"]
        == "ORTHOMOSAIC_MULTISPECTRAL"
    )

    assert (
        result["products"][0]
        ["band_count"]
        == 5
    )


def test_incomplete_campaign_is_rejected_before_job(
    tmp_path,
    monkeypatch,
):

    configure_storage(
        tmp_path,
        monkeypatch,
    )

    campaign = (
        CampaignService.create_campaign(
            name="Campaña incompleta",
            sensor_type="MULTISPECTRAL",
        )
    )

    CaptureService.create_capture(
        campaign_id=campaign["id"]
    )

    with pytest.raises(
        InvalidCampaignProcessingError
    ):
        ProcessingService.process_campaign(
            campaign_id=campaign["id"],
            backend=(
                MockPhotogrammetryBackend()
            ),
        )

    assert (
        ProcessingJobService.list_jobs(
            campaign["id"]
        )
        == []
    )


def test_unavailable_backend_marks_job_failed(
    tmp_path,
    monkeypatch,
):

    configure_storage(
        tmp_path,
        monkeypatch,
    )

    campaign = (
        create_ready_rgb_campaign(
            tmp_path
        )
    )

    with pytest.raises(
        ProcessingExecutionError
    ):
        ProcessingService.process_campaign(
            campaign_id=campaign["id"],
            backend=UnavailableBackend(),
        )

    jobs = (
        ProcessingJobService.list_jobs(
            campaign["id"]
        )
    )

    assert len(jobs) == 1

    assert jobs[0]["status"] == "FAILED"

    assert (
        "no está disponible"
        in jobs[0]["error_message"]
    )


def test_backend_failure_marks_job_failed(
    tmp_path,
    monkeypatch,
):

    configure_storage(
        tmp_path,
        monkeypatch,
    )

    campaign = (
        create_ready_rgb_campaign(
            tmp_path
        )
    )

    with pytest.raises(
        ProcessingExecutionError
    ):
        ProcessingService.process_campaign(
            campaign_id=campaign["id"],
            backend=FailingBackend(),
        )

    jobs = (
        ProcessingJobService.list_jobs(
            campaign["id"]
        )
    )

    assert jobs[0]["status"] == "FAILED"

    assert (
        "Fallo controlado"
        in jobs[0]["error_message"]
    )

    assert (
        GeospatialProductService
        .list_products(
            campaign["id"]
        )
        == []
    )


def test_partial_products_are_rolled_back(
    tmp_path,
    monkeypatch,
):

    storage_root = configure_storage(
        tmp_path,
        monkeypatch,
    )

    campaign = (
        create_ready_rgb_campaign(
            tmp_path
        )
    )

    with pytest.raises(
        ProcessingExecutionError
    ):
        ProcessingService.process_campaign(
            campaign_id=campaign["id"],
            backend=PartialProductBackend(),
        )

    assert (
        GeospatialProductService
        .list_products(
            campaign["id"]
        )
        == []
    )

    jobs = (
        ProcessingJobService.list_jobs(
            campaign["id"]
        )
    )

    assert jobs[0]["status"] == "FAILED"

    products_dir = (
        storage_root
        / campaign["campaign_code"]
        / "products"
    )

    if products_dir.exists():
        assert list(
            products_dir.glob("*.tif")
        ) == []