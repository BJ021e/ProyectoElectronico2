import io
import json

import numpy as np
import rasterio
import pytest

from rasterio.io import MemoryFile
from werkzeug.datastructures import (
    MultiDict,
)

from config import Config
from InterfazInit import app
from services.campaign_service import (
    CampaignService,
)


def client():

    app.config["TESTING"] = True

    return app.test_client()


def create_campaign(
    sensor_type="MULTISPECTRAL",
):

    return (
        CampaignService.create_campaign(
            name="Campaña batch RedEdge",
            sensor_type=sensor_type,
            sensor_model=(
                "MicaSense RedEdge-3"
                if sensor_type
                == "MULTISPECTRAL"
                else "RGB"
            ),
        )
    )


def create_tiff_bytes(
    value,
):

    data = np.full(
        (
            8,
            8,
        ),
        value,
        dtype=np.uint16,
    )

    with MemoryFile() as memory_file:

        with memory_file.open(
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

        return memory_file.read()


def create_stage(
    campaign_id,
):

    response = client().post(
        (
            f"/api/campaigns/"
            f"{campaign_id}/"
            "rededge/staging"
        )
    )

    assert (
        response.status_code
        == 201
    )

    return (
        response.get_json()[
            "staging_token"
        ]
    )


def upload_files(
    campaign_id,
    token,
    indexes,
):

    data = MultiDict()

    relative_paths = [
        (
            "001SET/"
            f"IMG_0001_{index}.tif"
        )
        for index in indexes
    ]

    data.add(
        "relative_paths",
        json.dumps(
            relative_paths
        ),
    )

    for index in indexes:

        data.add(
            "files",
            (
                io.BytesIO(
                    create_tiff_bytes(
                        index
                    )
                ),
                (
                    f"IMG_0001_"
                    f"{index}.tif"
                ),
            ),
        )

    return client().post(
        (
            f"/api/campaigns/"
            f"{campaign_id}/"
            "rededge/staging/"
            f"{token}/files"
        ),
        data=data,
        content_type=(
            "multipart/form-data"
        ),
    )


@pytest.mark.parametrize("role", [None, "FLIGHT", "CALIBRATION"])
def test_batch_import_persists_declared_role(tmp_path, monkeypatch, role):
    monkeypatch.setattr(Config, "RED_EDGE_STAGING_ROOT", str(tmp_path / "staging"))
    monkeypatch.setattr(Config, "CAMPAIGN_STORAGE_ROOT", str(tmp_path / "managed"))
    campaign = create_campaign()
    token = create_stage(campaign["id"])
    assert upload_files(campaign["id"], token, [1, 2]).status_code == 201
    assert upload_files(campaign["id"], token, [3, 4, 5]).status_code == 201
    payload = {"staging_token": token}
    if role is not None:
        payload["capture_role"] = role
    response = client().post(
        f"/api/campaigns/{campaign['id']}/rededge/import", json=payload,
    )
    assert response.status_code == 201, response.get_json()
    expected = role or "UNKNOWN"
    assert response.get_json()["imported_captures"][0]["capture"]["role"] == expected
    captures = client().get(f"/api/campaigns/{campaign['id']}/captures").get_json()
    assert captures["count"] == 1
    assert captures["captures"][0]["role"] == expected
    assert captures["role_counts"][expected] == 1
    assert not (tmp_path / "staging" / token).exists()


@pytest.mark.parametrize("role", ["PANEL", None, 1, {}])
def test_batch_import_rejects_invalid_role(tmp_path, monkeypatch, role):
    monkeypatch.setattr(Config, "RED_EDGE_STAGING_ROOT", str(tmp_path / "staging"))
    campaign = create_campaign()
    token = create_stage(campaign["id"])
    response = client().post(
        f"/api/campaigns/{campaign['id']}/rededge/import",
        json={"staging_token": token, "capture_role": role},
    )
    assert response.status_code == 400
    assert "capture_role" in response.get_json()["msg"]
    assert (tmp_path / "staging" / token).exists()
    assert client().get(f"/api/campaigns/{campaign['id']}/captures").get_json()["count"] == 0


def test_create_stage_api(
    tmp_path,
    monkeypatch,
):

    monkeypatch.setattr(
        Config,
        "RED_EDGE_STAGING_ROOT",
        str(
            tmp_path
            / "staging"
        ),
    )

    campaign = create_campaign()

    token = create_stage(
        campaign["id"]
    )

    assert len(token) == 32


def test_rgb_campaign_cannot_create_rededge_stage():

    campaign = create_campaign(
        "RGB"
    )

    response = client().post(
        (
            f"/api/campaigns/"
            f"{campaign['id']}/"
            "rededge/staging"
        )
    )

    assert response.status_code == 400


def test_rededge_files_can_be_uploaded_in_batches(
    tmp_path,
    monkeypatch,
):

    monkeypatch.setattr(
        Config,
        "RED_EDGE_STAGING_ROOT",
        str(
            tmp_path
            / "staging"
        ),
    )

    campaign = create_campaign()

    token = create_stage(
        campaign["id"]
    )

    first = upload_files(
        campaign["id"],
        token,
        [1, 2],
    )

    second = upload_files(
        campaign["id"],
        token,
        [3, 4, 5],
    )

    assert first.status_code == 201
    assert second.status_code == 201

    assert (
        first.get_json()[
            "stored_count"
        ]
        == 2
    )

    assert (
        second.get_json()[
            "stored_count"
        ]
        == 3
    )

    response = client().post(
        (
            f"/api/campaigns/"
            f"{campaign['id']}/"
            "rededge/staging/"
            f"{token}/inspect"
        )
    )

    assert response.status_code == 200

    inspection = (
        response.get_json()[
            "inspection"
        ]
    )

    assert (
        inspection["group_count"]
        == 1
    )

    assert (
        inspection["complete_count"]
        == 1
    )

    assert (
        inspection["incomplete_count"]
        == 0
    )


def test_batch_rejects_mismatched_paths(
    tmp_path,
    monkeypatch,
):

    monkeypatch.setattr(
        Config,
        "RED_EDGE_STAGING_ROOT",
        str(
            tmp_path
            / "staging"
        ),
    )

    campaign = create_campaign()

    token = create_stage(
        campaign["id"]
    )

    data = MultiDict()

    data.add(
        "relative_paths",
        json.dumps(
            [
                "001SET/IMG_0001_1.tif",
            ]
        ),
    )

    data.add(
        "files",
        (
            io.BytesIO(
                create_tiff_bytes(1)
            ),
            "IMG_0001_1.tif",
        ),
    )

    data.add(
        "files",
        (
            io.BytesIO(
                create_tiff_bytes(2)
            ),
            "IMG_0001_2.tif",
        ),
    )

    response = client().post(
        (
            f"/api/campaigns/"
            f"{campaign['id']}/"
            "rededge/staging/"
            f"{token}/files"
        ),
        data=data,
        content_type=(
            "multipart/form-data"
        ),
    )

    assert response.status_code == 400
