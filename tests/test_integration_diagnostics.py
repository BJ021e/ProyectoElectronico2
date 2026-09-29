import InterfazInit as app_module
import mqtt_diagnostics


class DummyIntegrationStatus:

    def to_dict(self):
        return {
            "configured": False,
            "provider": None,
            "transport_connected": False,
            "aircraft_online": False,
            "telemetry_available": False,
            "telemetry_fresh": False,
            "health": "NOT_CONFIGURED",
            "last_error": None,
        }


def authorized_client():
    client = app_module.app.test_client()

    with client.session_transaction() as sess:
        sess["mqtt_diag_access"] = True

    return client


def test_integration_diagnostics_requires_login():
    client = app_module.app.test_client()

    response = client.get(
        "/api/diagnostics/integration"
    )

    assert response.status_code == 401


def test_integration_diagnostics_rejects_remote():
    client = authorized_client()

    response = client.get(
        "/api/diagnostics/integration",
        environ_base={
            "REMOTE_ADDR": "192.168.1.12"
        },
    )

    assert response.status_code == 403


def test_integration_diagnostics_combines_sources(
    monkeypatch,
):
    client = authorized_client()

    monkeypatch.setattr(
        mqtt_diagnostics,
        "read_mqtt_events",
        lambda: {
            "log_exists": True,
            "last_event": {
                "timestamp":
                    "2026-09-29T07:00:00+00:00",
                "topic":
                    "pe2/diagnostico/tls",
                "qos": 1,
                "payload_bytes": 15,
                "diagnostic_ok": True,
            },
            "recent_events": [],
        },
    )

    monkeypatch.setattr(
        mqtt_diagnostics,
        "read_receiver_status",
        lambda: {
            "state": "connected",
            "connected": True,
            "last_heartbeat_at":
                "2026-09-29T07:00:05+00:00",
        },
    )

    monkeypatch.setattr(
        app_module.DroneService,
        "get_integration_status",
        lambda: DummyIntegrationStatus(),
    )

    response = client.get(
        "/api/diagnostics/integration"
    )

    assert response.status_code == 200

    data = response.get_json()

    assert (
        data["source"]
        == "pe2-integration-diagnostics"
    )

    assert (
        data["mqtt"]["receiver"]["state"]
        == "connected"
    )

    assert (
        data["mqtt"]["last_event"]
        ["diagnostic_ok"]
        is True
    )

    assert (
        data["dji_backend"]["available"]
        is True
    )

    assert (
        data["dji_backend"]
        ["status"]["health"]
        == "NOT_CONFIGURED"
    )

    assert (
        data["dji_cloud_probe"]
        ["contact_tracking"]
        is True
    )