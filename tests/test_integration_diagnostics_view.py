
import InterfazInit as app_module


def test_integration_page_requires_login():
    client = app_module.app.test_client()

    response = client.get(
        "/diagnostics/integration"
    )

    assert response.status_code == 302

    assert "/diagnostics/login" in (
        response.headers["Location"]
    )


def test_integration_page_requires_localhost():
    client = app_module.app.test_client()

    with client.session_transaction() as sess:
        sess["mqtt_diag_access"] = True

    response = client.get(
        "/diagnostics/integration",
        environ_base={
            "REMOTE_ADDR": "192.168.1.12"
        },
    )

    assert response.status_code == 403


def test_integration_page_authenticated():
    client = app_module.app.test_client()

    with client.session_transaction() as sess:
        sess["mqtt_diag_access"] = True

    response = client.get(
        "/diagnostics/integration"
    )

    assert response.status_code == 200

    assert (
        b"/api/diagnostics/integration"
        in response.data
    )

    assert (
        b"Historial MQTT"
        in response.data
    )
