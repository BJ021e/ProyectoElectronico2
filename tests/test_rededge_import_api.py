import io
import json

import numpy as np
import rasterio

from rasterio.io import MemoryFile
from werkzeug.datastructures import (
    MultiDict,
)

from config import Config
from InterfazInit import app
from services.campaign_service import (
    CampaignService,
)
from services.capture_service import (
    CaptureService,
)


def client():

    app.config["TESTING"] = True

    return app.test_client()


def create_campaign(
    sensor_type="MULTISPECTRAL",
):

    return CampaignService.create_campaign(
        name="Campaña API RedEdge",
        sensor_type=sensor_type,
        sensor_model=(
            "MicaSense RedEdge-3"
            if sensor_type
            == "MULTISPECTRAL"
            else "RGB"
        ),
    )


def create_tiff_bytes(
    value: int,
) -> bytes:

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


def build_complete_upload():

    relative_paths = [
        (
            f"001SET/"
            f"IMG_0001_{index}.tif"
        )
        for index in range(
            1,
            6,
        )
    ]

    data = MultiDict()

    data.add(
        "relative_paths",
        json.dumps(
            relative_paths
        ),
    )

    for index in range(
        1,
        6,
    ):

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

    return data


def test_inspect_complete_rededge_upload(
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

    response = client().post(
        (
            f"/api/campaigns/"
            f"{campaign['id']}/"
            "rededge/inspect"
        ),
        data=build_complete_upload(),
        content_type=(
            "multipart/form-data"
        ),
    )

    assert response.status_code == 201

    payload = response.get_json()

    assert (
        payload["uploaded_file_count"]
        == 5
    )

    assert (
        payload["inspection"]
        ["group_count"]
        == 1
    )

    assert (
        payload["inspection"]
        ["complete_count"]
        == 1
    )

    assert (
        payload["inspection"]
        ["incomplete_count"]
        == 0
    )

    assert payload[
        "staging_token"
    ]


def test_complete_stage_can_be_imported(
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

    monkeypatch.setattr(
        Config,
        "CAMPAIGN_STORAGE_ROOT",
        str(
            tmp_path
            / "managed"
        ),
    )

    campaign = create_campaign()

    inspect_response = client().post(
        (
            f"/api/campaigns/"
            f"{campaign['id']}/"
            "rededge/inspect"
        ),
        data=build_complete_upload(),
        content_type=(
            "multipart/form-data"
        ),
    )

    token = (
        inspect_response
        .get_json()[
            "staging_token"
        ]
    )

    import_response = client().post(
        (
            f"/api/campaigns/"
            f"{campaign['id']}/"
            "rededge/import"
        ),
        json={
            "staging_token": token,
            "skip_incomplete": False,
        },
    )

    assert (
        import_response.status_code
        == 201
    )

    result = (
        import_response.get_json()
    )

    assert (
        result["imported_count"]
        == 1
    )

    captures = (
        CaptureService.list_captures(
            campaign["id"]
        )
    )

    assert len(captures) == 1

    assert (
        captures[0]["status"]
        == "READY"
    )

    assert (
        len(
            captures[0]["assets"]
        )
        == 5
    )


def test_rededge_upload_rejects_rgb_campaign(
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

    campaign = create_campaign(
        "RGB"
    )

    response = client().post(
        (
            f"/api/campaigns/"
            f"{campaign['id']}/"
            "rededge/inspect"
        ),
        data=build_complete_upload(),
        content_type=(
            "multipart/form-data"
        ),
    )

    assert response.status_code == 400


def test_rededge_upload_rejects_mismatched_paths(
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

    data = MultiDict()

    data.add(
        "relative_paths",
        json.dumps(
            [
                "IMG_0001_1.tif",
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
            "rededge/inspect"
        ),
        data=data,
        content_type=(
            "multipart/form-data"
        ),
    )

    assert response.status_code == 400