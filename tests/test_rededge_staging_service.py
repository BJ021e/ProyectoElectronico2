from io import BytesIO

import pytest
import json

from config import Config
from services.rededge_staging_service import (
    InvalidRedEdgeStageError,
    RedEdgeStagingService,
    RedEdgeStagingError,
)

from datetime import (
    datetime,
    timedelta,
    timezone,
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
    
def test_cleanup_deletes_expired_stage(
    tmp_path,
    monkeypatch,
):

    configure_staging(
        tmp_path,
        monkeypatch,
    )

    now = datetime(
        2026,
        9,
        4,
        18,
        0,
        tzinfo=timezone.utc,
    )

    token = (
        RedEdgeStagingService
        .create_stage(
            campaign_id=1
        )
    )

    metadata_path = (
        RedEdgeStagingService
        ._metadata_path(
            token
        )
    )

    metadata = json.loads(
        metadata_path.read_text(
            encoding="utf-8"
        )
    )

    metadata["created_at"] = (
        now
        - timedelta(
            hours=25
        )
    ).isoformat()

    metadata_path.write_text(
        json.dumps(
            metadata
        ),
        encoding="utf-8",
    )

    result = (
        RedEdgeStagingService
        .cleanup_expired_stages(
            max_age_hours=24,
            now=now,
        )
    )

    assert (
        result["deleted_count"]
        == 1
    )

    assert token in (
        result["deleted_tokens"]
    )

    assert (
        not metadata_path.parent.exists()
    )


def test_cleanup_keeps_recent_stage(
    tmp_path,
    monkeypatch,
):

    configure_staging(
        tmp_path,
        monkeypatch,
    )

    now = datetime(
        2026,
        9,
        4,
        18,
        0,
        tzinfo=timezone.utc,
    )

    token = (
        RedEdgeStagingService
        .create_stage(
            campaign_id=1
        )
    )

    metadata_path = (
        RedEdgeStagingService
        ._metadata_path(
            token
        )
    )

    metadata = json.loads(
        metadata_path.read_text(
            encoding="utf-8"
        )
    )

    metadata["created_at"] = (
        now
        - timedelta(
            hours=2
        )
    ).isoformat()

    metadata_path.write_text(
        json.dumps(
            metadata
        ),
        encoding="utf-8",
    )

    result = (
        RedEdgeStagingService
        .cleanup_expired_stages(
            max_age_hours=24,
            now=now,
        )
    )

    assert (
        result["deleted_count"]
        == 0
    )

    assert (
        result["kept_count"]
        == 1
    )

    assert (
        metadata_path.parent.exists()
    )


def test_cleanup_does_not_delete_invalid_metadata(
    tmp_path,
    monkeypatch,
):

    root = configure_staging(
        tmp_path,
        monkeypatch,
    )

    token = "a" * 32

    stage_directory = (
        root
        / token
    )

    stage_directory.mkdir(
        parents=True
    )

    metadata_path = (
        stage_directory
        / RedEdgeStagingService
        .METADATA_FILENAME
    )

    metadata_path.write_text(
        "{esto no es json",
        encoding="utf-8",
    )

    now = datetime(
        2026,
        9,
        4,
        18,
        0,
        tzinfo=timezone.utc,
    )

    result = (
        RedEdgeStagingService
        .cleanup_expired_stages(
            max_age_hours=24,
            now=now,
        )
    )

    assert (
        result["deleted_count"]
        == 0
    )

    assert (
        result["invalid_count"]
        == 1
    )

    assert (
        stage_directory.exists()
    )


def test_cleanup_rejects_invalid_max_age(
    tmp_path,
    monkeypatch,
):

    configure_staging(
        tmp_path,
        monkeypatch,
    )

    with pytest.raises(
        RedEdgeStagingError
    ):
        (
            RedEdgeStagingService
            .cleanup_expired_stages(
                max_age_hours=0
            )
        )


def test_create_stage_runs_expired_cleanup(
    tmp_path,
    monkeypatch,
):

    root = configure_staging(
        tmp_path,
        monkeypatch,
    )

    old_token = (
        "b" * 32
    )

    old_directory = (
        root
        / old_token
    )

    old_directory.mkdir(
        parents=True
    )

    old_metadata = {
        "campaign_id": 1,
        "created_at": (
            datetime.now(
                timezone.utc
            )
            - timedelta(
                hours=48
            )
        ).isoformat(),
    }

    (
        old_directory
        / RedEdgeStagingService
        .METADATA_FILENAME
    ).write_text(
        json.dumps(
            old_metadata
        ),
        encoding="utf-8",
    )

    new_token = (
        RedEdgeStagingService
        .create_stage(
            campaign_id=1
        )
    )

    assert (
        not old_directory.exists()
    )

    assert (
        RedEdgeStagingService
        .get_stage_directory(
            token=new_token,
            campaign_id=1,
        )
        .exists()
    )