from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest
import rasterio

from config import Config
from services.campaign_service import CampaignService
from services.capture_role_backfill_service import (
    CaptureRoleBackfillError,
    CaptureRoleBackfillService,
)
from services.capture_service import CaptureService
from services.image_ingestion_service import ImageIngestionService


BANDS = (("BLUE", 1), ("GREEN", 2), ("RED", 3), ("NIR", 4), ("RED_EDGE", 5))


def create_tiff(path: Path, value: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", width=4, height=4, count=1, dtype="uint16") as dataset:
        dataset.write(np.full((4, 4), value, dtype=np.uint16), 1)


def create_source_group(directory: Path, name: str, values=range(1, 6)) -> dict[str, Path]:
    files = {}
    for (band, index), value in zip(BANDS, values, strict=True):
        path = directory / f"{name}_{index}.tif"
        create_tiff(path, value)
        files[band] = path
    return files


def copy_source_group(source: dict[str, Path], directory: Path, name: str) -> dict[str, Path]:
    files = {}
    for band, index in BANDS:
        target = directory / f"{name}_{index}.tif"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source[band], target)
        files[band] = target
    return files


def create_campaign() -> dict:
    return CampaignService.create_campaign(name="Backfill roles", sensor_type="MULTISPECTRAL")


def persist_capture(campaign: dict, files: dict[str, Path], *, role="UNKNOWN", incomplete=False, **ignored) -> dict:
    capture = CaptureService.create_capture(campaign_id=campaign["id"], role=role, **ignored)
    for band, _ in BANDS[:4 if incomplete else 5]:
        ImageIngestionService.ingest_file(capture_id=capture["id"], band=band, source_path=files[band])
    return CaptureService.get_capture(capture["id"])


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "CAMPAIGN_STORAGE_ROOT", str(tmp_path / "managed"))
    return tmp_path


def test_complete_five_band_match_dry_run_does_not_modify_database(storage):
    source = create_source_group(storage / "declared-set", "unrelated_name")
    campaign = create_campaign()
    different = create_source_group(storage / "unrelated", "other", [6, 7, 8, 9, 10])
    persist_capture(campaign, different)
    capture = persist_capture(campaign, source, altitude=9999)

    report = CaptureRoleBackfillService.analyze(
        campaign_id=campaign["id"], sources={"FLIGHT": storage / "declared-set"},
    )

    assert report["dry_run"] is True
    assert report["safe_to_apply"] is True
    assert report["matching"]["matched_capture_groups"] == 1
    assert report["matching"]["matched_assets"] == 5
    assert report["matching"]["matches"][0]["capture_id"] == capture["id"]
    assert set(report["matching"]["matches"][0]["hashes"]) == {band for band, _ in BANDS}
    assert CaptureService.get_capture(capture["id"])["role"] == "UNKNOWN"


def test_apply_assigns_verified_roles_and_leaves_unincluded_captures_unknown(storage):
    flight = create_source_group(storage / "flight_named_anything", "source_a", [10, 11, 12, 13, 14])
    extra = create_source_group(storage / "not-declared", "source_b", [20, 21, 22, 23, 24])
    campaign = create_campaign()
    assigned = persist_capture(campaign, flight)
    unassigned = persist_capture(campaign, extra)

    report = CaptureRoleBackfillService.apply(
        campaign_id=campaign["id"], sources={"FLIGHT": storage / "flight_named_anything"},
    )

    assert report["safe_to_apply"] is True
    assert report["matching"]["unmatched_db_captures"] == 1
    assert CaptureService.get_capture(assigned["id"])["role"] == "FLIGHT"
    assert CaptureService.get_capture(unassigned["id"])["role"] == "UNKNOWN"


def test_source_group_incomplete_is_rejected(storage):
    source = create_source_group(storage / "source", "partial")
    source["NIR"].unlink()
    campaign = create_campaign()
    with pytest.raises(CaptureRoleBackfillError, match="incompletos"):
        CaptureRoleBackfillService.analyze(campaign_id=campaign["id"], sources={"FLIGHT": storage / "source"})


def test_database_capture_incomplete_is_rejected(storage):
    source = create_source_group(storage / "source", "all")
    campaign = create_campaign()
    persist_capture(campaign, source, incomplete=True)
    with pytest.raises(CaptureRoleBackfillError, match="exactamente cinco bandas"):
        CaptureRoleBackfillService.analyze(campaign_id=campaign["id"], sources={"FLIGHT": storage / "source"})


def test_distinct_content_does_not_match_even_with_same_name_sequence_or_coordinates(storage):
    source = create_source_group(storage / "source", "same_name", [1, 2, 3, 4, 5])
    database_files = create_source_group(storage / "different", "same_name", [6, 7, 8, 9, 10])
    campaign = create_campaign()
    persist_capture(campaign, database_files, latitude=1, longitude=2, altitude=3)
    report = CaptureRoleBackfillService.analyze(campaign_id=campaign["id"], sources={"FLIGHT": storage / "source"})
    assert report["safe_to_apply"] is False
    assert report["matching"]["matched_capture_groups"] == 0
    assert report["matching"]["unmatched_source_groups"] == 1


def test_duplicate_content_in_source_is_ambiguous(storage):
    first = create_source_group(storage / "source", "first")
    copy_source_group(first, storage / "source", "second")
    campaign = create_campaign()
    persist_capture(campaign, first)
    report = CaptureRoleBackfillService.analyze(campaign_id=campaign["id"], sources={"FLIGHT": storage / "source"})
    assert report["safe_to_apply"] is False
    assert report["matching"]["ambiguous_groups"] == 1


def test_duplicate_database_content_is_ambiguous(storage):
    source = create_source_group(storage / "source", "one")
    campaign = create_campaign()
    persist_capture(campaign, source)
    persist_capture(campaign, source)
    report = CaptureRoleBackfillService.analyze(campaign_id=campaign["id"], sources={"FLIGHT": storage / "source"})
    assert report["safe_to_apply"] is False
    assert report["matching"]["ambiguous_groups"] == 1


def test_two_roles_cannot_assign_the_same_capture(storage):
    flight = create_source_group(storage / "flight", "a")
    copy_source_group(flight, storage / "calibration", "b")
    campaign = create_campaign()
    persist_capture(campaign, flight)
    report = CaptureRoleBackfillService.analyze(
        campaign_id=campaign["id"],
        sources={"FLIGHT": storage / "flight", "CALIBRATION": storage / "calibration"},
    )
    assert report["safe_to_apply"] is False
    assert report["matching"]["conflicts"] == 1
    assert report["matching"]["conflict_details"][0]["reason"] == "source_roles_conflict"


def test_persisted_incompatible_role_is_conflict_and_already_assigned_is_idempotent(storage):
    source = create_source_group(storage / "source", "a")
    campaign = create_campaign()
    capture = persist_capture(campaign, source, role="FLIGHT")
    conflict = CaptureRoleBackfillService.analyze(
        campaign_id=campaign["id"], sources={"CALIBRATION": storage / "source"},
    )
    assert conflict["safe_to_apply"] is False
    assert conflict["matching"]["conflicts"] == 1
    assert conflict["matching"]["conflict_details"][0]["persisted_role"] == "FLIGHT"
    same = CaptureRoleBackfillService.analyze(
        campaign_id=campaign["id"], sources={"FLIGHT": storage / "source"},
    )
    assert same["safe_to_apply"] is True
    assert same["matching"]["already_assigned"] == 1
    assert same["matching"]["matches"] == []
    assert CaptureService.get_capture(capture["id"])["role"] == "FLIGHT"


def test_apply_is_all_or_nothing_on_conflict(storage):
    flight = create_source_group(storage / "flight", "a", [1, 2, 3, 4, 5])
    calibration = create_source_group(storage / "calibration", "b", [6, 7, 8, 9, 10])
    campaign = create_campaign()
    first = persist_capture(campaign, flight)
    second = persist_capture(campaign, calibration, role="FLIGHT")
    with pytest.raises(CaptureRoleBackfillError, match="conflictos"):
        CaptureRoleBackfillService.apply(
            campaign_id=campaign["id"],
            sources={"FLIGHT": storage / "flight", "CALIBRATION": storage / "calibration"},
        )
    assert CaptureService.get_capture(first["id"])["role"] == "UNKNOWN"
    assert CaptureService.get_capture(second["id"])["role"] == "FLIGHT"


def test_flight_and_calibration_can_coexist(storage):
    flight = create_source_group(storage / "flight", "a", [1, 2, 3, 4, 5])
    calibration = create_source_group(storage / "calibration", "b", [6, 7, 8, 9, 10])
    campaign = create_campaign()
    first = persist_capture(campaign, flight)
    second = persist_capture(campaign, calibration)
    report = CaptureRoleBackfillService.apply(
        campaign_id=campaign["id"],
        sources={"FLIGHT": storage / "flight", "CALIBRATION": storage / "calibration"},
    )
    assert report["planned_role_counts_after"] == {"UNKNOWN": 0, "FLIGHT": 1, "CALIBRATION": 1}
    assert CaptureService.get_capture(first["id"])["role"] == "FLIGHT"
    assert CaptureService.get_capture(second["id"])["role"] == "CALIBRATION"


@pytest.mark.parametrize("sources", [{"UNKNOWN": "missing"}, {"PANEL": "missing"}])
def test_source_role_must_be_explicit_and_supported(storage, sources):
    campaign = create_campaign()
    resolved = {role: storage / value for role, value in sources.items()}
    with pytest.raises(CaptureRoleBackfillError):
        CaptureRoleBackfillService.analyze(campaign_id=campaign["id"], sources=resolved)


def test_campaign_and_source_directory_must_exist(storage):
    with pytest.raises(CaptureRoleBackfillError, match="source directory no existe"):
        CaptureRoleBackfillService.analyze(campaign_id=999, sources={"FLIGHT": storage / "missing"})
    source = create_source_group(storage / "source", "one")
    with pytest.raises(CaptureRoleBackfillError, match="campaña con ID 999 no existe"):
        CaptureRoleBackfillService.analyze(campaign_id=999, sources={"FLIGHT": storage / "source"})
