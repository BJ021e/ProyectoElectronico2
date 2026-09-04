from io import BytesIO

import pytest

from config import Config
from services.rededge_staging_service import (
    InvalidRedEdgeStageError,
    RedEdgeStagingService,
)


def configure_staging(
    tmp_path,
    monkeypatch,
):

    root = (
        tmp_path
        / "staging"
    )

    monkeypatch.setattr(
        Config,
        "RED_EDGE_STAGING_ROOT",
        str(root),
    )

    return root


def test_stage_can_store_relative_file(
    tmp_path,
    monkeypatch,
):

    configure_staging(
        tmp_path,
        monkeypatch,
    )

    token = (
        RedEdgeStagingService
        .create_stage(
            campaign_id=1
        )
    )

    stored = (
        RedEdgeStagingService
        .stage_file(
            token=token,
            campaign_id=1,
            relative_path=(
                "001SET/IMG_0001_1.tif"
            ),
            source_stream=(
                BytesIO(
                    b"contenido"
                )
            ),
        )
    )

    assert stored.exists()

    assert (
        stored.read_bytes()
        == b"contenido"
    )


def test_stage_rejects_path_traversal(
    tmp_path,
    monkeypatch,
):

    configure_staging(
        tmp_path,
        monkeypatch,
    )

    token = (
        RedEdgeStagingService
        .create_stage(
            campaign_id=1
        )
    )

    with pytest.raises(
        InvalidRedEdgeStageError
    ):
        (
            RedEdgeStagingService
            .stage_file(
                token=token,
                campaign_id=1,
                relative_path=(
                    "../../database.db"
                ),
                source_stream=(
                    BytesIO(b"x")
                ),
            )
        )


def test_stage_belongs_to_campaign(
    tmp_path,
    monkeypatch,
):

    configure_staging(
        tmp_path,
        monkeypatch,
    )

    token = (
        RedEdgeStagingService
        .create_stage(
            campaign_id=1
        )
    )

    with pytest.raises(
        InvalidRedEdgeStageError
    ):
        (
            RedEdgeStagingService
            .get_stage_directory(
                token=token,
                campaign_id=2,
            )
        )


def test_stage_can_be_deleted(
    tmp_path,
    monkeypatch,
):

    configure_staging(
        tmp_path,
        monkeypatch,
    )

    token = (
        RedEdgeStagingService
        .create_stage(
            campaign_id=1
        )
    )

    directory = (
        RedEdgeStagingService
        .get_stage_directory(
            token=token,
            campaign_id=1,
        )
    )

    assert directory.exists()

    deleted = (
        RedEdgeStagingService
        .delete_stage(
            token=token,
            campaign_id=1,
        )
    )

    assert deleted is True

    assert (
        not directory.exists()
    )