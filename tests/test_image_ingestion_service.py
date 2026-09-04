from pathlib import Path

import cv2
import numpy as np
import pytest
import rasterio

from config import Config
from services.campaign_service import (
    CampaignService,
)
from services.capture_service import (
    CaptureService,
)
from services.image_ingestion_service import (
    ImageIngestionError,
    ImageIngestionService,
    InvalidImageFileError,
)


def create_campaign_and_capture(
    sensor_type="MULTISPECTRAL",
):

    campaign = CampaignService.create_campaign(
        name="Campaña ingestión",
        sensor_type=sensor_type,
        sensor_model=(
            "MicaSense RedEdge-3"
            if sensor_type == "MULTISPECTRAL"
            else "RGB"
        ),
    )

    capture = CaptureService.create_capture(
        campaign_id=campaign["id"]
    )

    return campaign, capture


def create_test_tiff(
    path: Path,
) -> None:

    data = np.arange(
        64,
        dtype=np.uint16,
    ).reshape(
        8,
        8,
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


def create_test_rgb(
    path: Path,
) -> None:

    image = np.zeros(
        (
            8,
            8,
            3,
        ),
        dtype=np.uint8,
    )

    success = cv2.imwrite(
        str(path),
        image,
    )

    assert success is True


def test_ingest_multispectral_tiff(
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

    campaign, capture = (
        create_campaign_and_capture()
    )

    source = (
        tmp_path
        / "IMG_0001_1.tif"
    )

    create_test_tiff(source)

    result = (
        ImageIngestionService.ingest_file(
            capture_id=capture["id"],
            band="BLUE",
            source_path=source,
        )
    )

    assert (
        result["asset"]["band"]
        == "BLUE"
    )

    assert (
        result["asset"]["original_filename"]
        == "IMG_0001_1.tif"
    )

    assert (
        result["capture"]["status"]
        == "CREATED"
    )

    assert (
        result["ingestion"]["size_bytes"]
        > 0
    )

    assert len(
        result["ingestion"]["sha256"]
    ) == 64

    managed_file = (
        storage_root
        / result["ingestion"]["storage_path"]
    )

    assert managed_file.exists()

    assert source.exists()


def test_five_bands_make_capture_ready(
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

    _, capture = (
        create_campaign_and_capture()
    )

    mapping = [
        ("BLUE", 1),
        ("GREEN", 2),
        ("RED", 3),
        ("NIR", 4),
        ("RED_EDGE", 5),
    ]

    result = None

    for band, index in mapping:

        source = (
            tmp_path
            / f"IMG_0001_{index}.tif"
        )

        create_test_tiff(
            source
        )

        result = (
            ImageIngestionService.ingest_file(
                capture_id=capture["id"],
                band=band,
                source_path=source,
            )
        )

    assert (
        result["capture"]["status"]
        == "READY"
    )

    assert (
        result["capture"]
        ["readiness"]
        ["is_complete"]
        is True
    )

    assert len(
        result["capture"]["assets"]
    ) == 5


def test_ingest_rgb_image(
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

    _, capture = (
        create_campaign_and_capture(
            sensor_type="RGB"
        )
    )

    source = (
        tmp_path
        / "IMG_0001.jpg"
    )

    create_test_rgb(source)

    result = (
        ImageIngestionService.ingest_file(
            capture_id=capture["id"],
            band="RGB",
            source_path=source,
        )
    )

    assert (
        result["capture"]["status"]
        == "READY"
    )

    assert (
        result["asset"]["band"]
        == "RGB"
    )


def test_missing_source_is_rejected(
    tmp_path,
):

    _, capture = (
        create_campaign_and_capture()
    )

    with pytest.raises(
        InvalidImageFileError
    ):

        ImageIngestionService.ingest_file(
            capture_id=capture["id"],
            band="BLUE",
            source_path=(
                tmp_path
                / "missing.tif"
            ),
        )


def test_invalid_multispectral_extension_is_rejected(
    tmp_path,
):

    _, capture = (
        create_campaign_and_capture()
    )

    source = (
        tmp_path
        / "blue.jpg"
    )

    create_test_rgb(source)

    with pytest.raises(
        InvalidImageFileError
    ):

        ImageIngestionService.ingest_file(
            capture_id=capture["id"],
            band="BLUE",
            source_path=source,
        )


def test_corrupted_tiff_is_rejected(
    tmp_path,
):

    _, capture = (
        create_campaign_and_capture()
    )

    source = (
        tmp_path
        / "corrupted.tif"
    )

    source.write_bytes(
        b"esto no es un TIFF"
    )

    with pytest.raises(
        InvalidImageFileError
    ):

        ImageIngestionService.ingest_file(
            capture_id=capture["id"],
            band="BLUE",
            source_path=source,
        )