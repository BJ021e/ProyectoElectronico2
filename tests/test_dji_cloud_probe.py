
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

def test_dji_cloud_probe_has_thing_diagnostics():
    app.config["TESTING"] = True

    response = app.test_client().get(
        "/dji-cloud"
    )

    assert response.status_code == 200

    html = response.get_data(
        as_text=True
    )

    assert (
        "platformLoadComponent"
        in html
    )

    assert (
        "platformIsComponentLoaded"
        in html
    )

    assert (
        "thingGetConnectState"
        in html
    )

    assert (
        "pe2ThingConnectCallback"
        in html
    )

    assert (
        "pilot2_cloud"
        in html
    )

    assert (
        "window.location.hostname"
        in html
    )

    assert (
        "thingGetConfigs"
        not in html
    )

    assert (
        'platformIsComponentLoaded('
        in html
    )

    assert (
        'thingGetConnectState()'
        in html
    )

    assert (
        "report.thing_loaded"
        in html
    )

    assert (
        "report.thing_connected"
        in html
    )

def test_dji_cloud_probe_does_not_embed_dji_credentials():
    app.config["TESTING"] = True

    response = app.test_client().get(
        "/dji-cloud"
    )

    html = response.get_data(
        as_text=True
    )

    assert (
        "DJI_CLOUD_APP_KEY"
        not in html
    )

    assert (
        "DJI_CLOUD_APP_LICENSE"
        not in html
    )