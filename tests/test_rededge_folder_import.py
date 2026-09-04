from pathlib import Path

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
from services.rededge_import_service import (
    IncompleteRedEdgeFolderError,
    InvalidRedEdgeCampaignError,
    InvalidRedEdgeFolderError,
    RedEdgeImportExecutionError,
    RedEdgeImportService,
)


def create_campaign(
    sensor_type="MULTISPECTRAL",
):

    return CampaignService.create_campaign(
        name="Campaña importación",
        sensor_type=sensor_type,
        sensor_model=(
            "MicaSense RedEdge-3"
            if sensor_type == "MULTISPECTRAL"
            else "RGB"
        ),
    )


def create_tiff(
    path: Path,
    *,
    value: int = 1,
):

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

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


def create_group(
    directory: Path,
    base_name: str,
    bands=(1, 2, 3, 4, 5),
):

    for band_index in bands:

        create_tiff(
            (
                directory
                / (
                    f"{base_name}_"
                    f"{band_index}.tif"
                )
            ),
            value=band_index,
        )


def test_import_complete_rededge_group(
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

    source = (
        tmp_path
        / "source"
    )

    create_group(
        source,
        "IMG_0001",
    )

    campaign = create_campaign()

    result = (
        RedEdgeImportService.import_folder(
            campaign_id=campaign["id"],
            source_dir=source,
        )
    )

    assert result["detected_count"] == 1
    assert result["imported_count"] == 1
    assert result["skipped_count"] == 0

    imported = (
        result["imported_captures"][0]
    )

    capture = imported["capture"]

    assert (
        imported["source_key"]
        == "IMG_0001"
    )

    assert capture["status"] == "READY"

    assert len(
        capture["assets"]
    ) == 5

    assert (
        capture["readiness"]
        ["is_complete"]
        is True
    )

    capture_directory = (
        storage_root
        / campaign["campaign_code"]
        / "captures"
        / "0001"
    )

    assert (
        capture_directory
        / "BLUE.tif"
    ).exists()

    assert (
        capture_directory
        / "GREEN.tif"
    ).exists()

    assert (
        capture_directory
        / "RED.tif"
    ).exists()

    assert (
        capture_directory
        / "NIR.tif"
    ).exists()

    assert (
        capture_directory
        / "RED_EDGE.tif"
    ).exists()


def test_import_multiple_groups_preserves_sequence(
    tmp_path,
    monkeypatch,
):

    monkeypatch.setattr(
        Config,
        "CAMPAIGN_STORAGE_ROOT",
        str(
            tmp_path
            / "managed"
        ),
    )

    source = (
        tmp_path
        / "source"
    )

    create_group(
        source / "001SET",
        "IMG_0001",
    )

    create_group(
        source / "001SET",
        "IMG_0002",
    )

    create_group(
        source / "002SET",
        "IMG_0001",
    )

    campaign = create_campaign()

    result = (
        RedEdgeImportService.import_folder(
            campaign_id=campaign["id"],
            source_dir=source,
        )
    )

    assert result["imported_count"] == 3

    assert [
        item["source_key"]
        for item
        in result["imported_captures"]
    ] == [
        "001SET/IMG_0001",
        "001SET/IMG_0002",
        "002SET/IMG_0001",
    ]

    assert [
        item["capture"]["sequence"]
        for item
        in result["imported_captures"]
    ] == [
        1,
        2,
        3,
    ]


def test_strict_import_rejects_incomplete_folder(
    tmp_path,
    monkeypatch,
):

    monkeypatch.setattr(
        Config,
        "CAMPAIGN_STORAGE_ROOT",
        str(
            tmp_path
            / "managed"
        ),
    )

    source = (
        tmp_path
        / "source"
    )

    create_group(
        source,
        "IMG_0001",
    )

    create_group(
        source,
        "IMG_0002",
        bands=(1, 2, 3),
    )

    campaign = create_campaign()

    with pytest.raises(
        IncompleteRedEdgeFolderError
    ):
        RedEdgeImportService.import_folder(
            campaign_id=campaign["id"],
            source_dir=source,
        )

    captures = (
        CaptureService.list_captures(
            campaign["id"]
        )
    )

    assert captures == []


def test_skip_incomplete_imports_only_complete_groups(
    tmp_path,
    monkeypatch,
):

    monkeypatch.setattr(
        Config,
        "CAMPAIGN_STORAGE_ROOT",
        str(
            tmp_path
            / "managed"
        ),
    )

    source = (
        tmp_path
        / "source"
    )

    create_group(
        source,
        "IMG_0001",
    )

    create_group(
        source,
        "IMG_0002",
        bands=(1, 2, 3),
    )

    campaign = create_campaign()

    result = (
        RedEdgeImportService.import_folder(
            campaign_id=campaign["id"],
            source_dir=source,
            skip_incomplete=True,
        )
    )

    assert result["detected_count"] == 2
    assert result["imported_count"] == 1
    assert result["skipped_count"] == 1

    assert (
        result["skipped_groups"][0]
        ["source_key"]
        == "IMG_0002"
    )

    assert (
        result["skipped_groups"][0]
        ["missing_bands"]
        == [
            "NIR",
            "RED_EDGE",
        ]
    )


def test_rededge_import_rejects_rgb_campaign(
    tmp_path,
):

    source = (
        tmp_path
        / "source"
    )

    create_group(
        source,
        "IMG_0001",
    )

    campaign = create_campaign(
        sensor_type="RGB"
    )

    with pytest.raises(
        InvalidRedEdgeCampaignError
    ):
        RedEdgeImportService.import_folder(
            campaign_id=campaign["id"],
            source_dir=source,
        )


def test_import_rejects_folder_without_rededge_groups(
    tmp_path,
):

    source = (
        tmp_path
        / "source"
    )

    source.mkdir()

    (
        source
        / "README.txt"
    ).write_text(
        "sin imágenes",
        encoding="utf-8",
    )

    campaign = create_campaign()

    with pytest.raises(
        InvalidRedEdgeFolderError
    ):
        RedEdgeImportService.import_folder(
            campaign_id=campaign["id"],
            source_dir=source,
        )


def test_failed_ingestion_rolls_back_capture_and_files(
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

    source = (
        tmp_path
        / "source"
    )

    create_group(
        source,
        "IMG_0001",
    )

    # El escáner seguirá reconociendo el nombre
    # como banda NIR, pero Rasterio no podrá abrirlo.
    corrupted = (
        source
        / "IMG_0001_4.tif"
    )

    corrupted.write_bytes(
        b"TIFF corrupto"
    )

    campaign = create_campaign()

    with pytest.raises(
        RedEdgeImportExecutionError
    ):
        RedEdgeImportService.import_folder(
            campaign_id=campaign["id"],
            source_dir=source,
        )

    captures = (
        CaptureService.list_captures(
            campaign["id"]
        )
    )

    assert captures == []

    capture_directory = (
        storage_root
        / campaign["campaign_code"]
        / "captures"
        / "0001"
    )

    assert (
        capture_directory.exists()
        is False
    )