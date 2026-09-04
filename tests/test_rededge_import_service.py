from pathlib import Path

import pytest

from services.rededge_import_service import (
    InvalidRedEdgeFolderError,
    RedEdgeImportService,
)


def create_rededge_group(
    directory: Path,
    base_name: str,
    bands=(1, 2, 3, 4, 5),
):

    directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    for band_index in bands:

        path = (
            directory
            / f"{base_name}_{band_index}.tif"
        )

        path.write_bytes(
            b"test"
        )


def test_complete_rededge_group_is_detected(
    tmp_path,
):

    create_rededge_group(
        tmp_path,
        "IMG_0001",
    )

    result = (
        RedEdgeImportService.inspect_folder(
            tmp_path
        )
    )

    assert result["group_count"] == 1

    assert (
        result["complete_count"]
        == 1
    )

    assert (
        result["incomplete_count"]
        == 0
    )

    group = result["groups"][0]

    assert group["source_key"] == "IMG_0001"

    assert group["is_complete"] is True

    assert group["present_bands"] == [
        "BLUE",
        "GREEN",
        "RED",
        "NIR",
        "RED_EDGE",
    ]

    assert group["missing_bands"] == []


def test_incomplete_group_reports_missing_bands(
    tmp_path,
):

    create_rededge_group(
        tmp_path,
        "IMG_0001",
        bands=(1, 3, 4),
    )

    result = (
        RedEdgeImportService.inspect_folder(
            tmp_path
        )
    )

    group = result["groups"][0]

    assert (
        group["is_complete"]
        is False
    )

    assert (
        group["present_bands"]
        == [
            "BLUE",
            "RED",
            "NIR",
        ]
    )

    assert (
        group["missing_bands"]
        == [
            "GREEN",
            "RED_EDGE",
        ]
    )

    assert (
        result["incomplete_count"]
        == 1
    )


def test_groups_in_different_sets_are_independent(
    tmp_path,
):

    create_rededge_group(
        tmp_path / "001SET",
        "IMG_0001",
    )

    create_rededge_group(
        tmp_path / "002SET",
        "IMG_0001",
    )

    result = (
        RedEdgeImportService.inspect_folder(
            tmp_path
        )
    )

    assert result["group_count"] == 2

    assert (
        result["complete_count"]
        == 2
    )

    assert [
        group["source_key"]
        for group in result["groups"]
    ] == [
        "001SET/IMG_0001",
        "002SET/IMG_0001",
    ]


def test_unrelated_files_are_ignored(
    tmp_path,
):

    create_rededge_group(
        tmp_path,
        "IMG_0001",
    )

    (
        tmp_path
        / "README.txt"
    ).write_text(
        "archivo auxiliar",
        encoding="utf-8",
    )

    (
        tmp_path
        / "preview.jpg"
    ).write_bytes(
        b"preview"
    )

    result = (
        RedEdgeImportService.inspect_folder(
            tmp_path
        )
    )

    assert result["group_count"] == 1

    assert sorted(
        result["ignored_files"]
    ) == [
        "README.txt",
        "preview.jpg",
    ]


def test_duplicate_band_is_rejected(
    tmp_path,
):

    (
        tmp_path
        / "IMG_0001_1.tif"
    ).write_bytes(
        b"first"
    )

    (
        tmp_path
        / "IMG_0001_1.tiff"
    ).write_bytes(
        b"second"
    )

    with pytest.raises(
        InvalidRedEdgeFolderError
    ):
        RedEdgeImportService.inspect_folder(
            tmp_path
        )


def test_unknown_folder_returns_no_groups(
    tmp_path,
):

    (
        tmp_path
        / "photo.jpg"
    ).write_bytes(
        b"test"
    )

    result = (
        RedEdgeImportService.inspect_folder(
            tmp_path
        )
    )

    assert result["group_count"] == 0

    assert result["groups"] == []

    assert result["ignored_files"] == [
        "photo.jpg"
    ]