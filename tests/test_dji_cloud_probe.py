
from InterfazInit import app


def test_dji_cloud_probe_page():
    app.config["TESTING"] = True

    response = app.test_client().get(
        "/dji-cloud"
    )

    assert response.status_code == 200
    assert b"DJI Cloud Probe" in response.data


def test_dji_cloud_ping_post():
    app.config["TESTING"] = True

    response = app.test_client().post(
        "/api/dji-cloud/ping",
        json={
            "source": "pytest",
            "client_request_id": "test-001",
        },
    )

    assert response.status_code == 200

    data = response.get_json()

    assert data["ok"] is True
    assert data["client_request_id"] == "test-001"
    assert len(data["request_id"]) == 12


def test_dji_cloud_probe_has_bridge_diagnostics():
    app.config["TESTING"] = True

    response = app.test_client().get("/dji-cloud")

    assert response.status_code == 200

    html = response.get_data(as_text=True)

    for marker in (
        "checkDjiBridge",
        "platformVerifyLicense",
        "platformLoadComponent",
        "platformSetWorkspaceId",
        "platformSetInformation",
    ):
        assert marker in html
