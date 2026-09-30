import InterfazInit as app_module


def test_dji_cloud_readiness_accepts_loopback(
    monkeypatch,
):
    import dji_cloud_state

    monkeypatch.setattr(
        dji_cloud_state,
        "read_dji_cloud_state",
        lambda: {},
    )

    monkeypatch.setattr(
        dji_cloud_state,
        "build_runtime_summary",
        lambda state: {
            "gateway_detected": True,
            "gateway_id":
                "RC_***001",
            "simulated": True,
            "device_count": 1,
            "last_message_at":
                "2026-09-30T08:03:47+00:00",
            "last_channel": "state",
        },
    )

    monkeypatch.setattr(
        dji_cloud_state,
        "read_dji_cloud_receiver_status",
        lambda: {},
    )

    monkeypatch.setattr(
        dji_cloud_state,
        "summarize_receiver_status",
        lambda state: {
            "state": "connected",
            "heartbeat_age_seconds": 2.0,
        },
    )

    client = (
        app_module.app.test_client()
    )

    response = client.get(
        "/api/dji-cloud/readiness",
        environ_base={
            "REMOTE_ADDR":
                "127.0.0.1",
        },
    )

    assert response.status_code == 200

    data = response.get_json()

    assert data["ok"] is True

    assert (
        data["mqtt"]["port"]
        == 1884
    )

    assert (
        data["mqtt"][
            "receiver_state"
        ]
        == "connected"
    )

    assert (
        data["gateway"][
            "detected"
        ]
        is True
    )

    assert (
        data["gateway"][
            "simulated"
        ]
        is True
    )

    assert (
        data["gateway"][
            "real_observed"
        ]
        is False
    )


def test_dji_cloud_readiness_rejects_public_ip():
    client = (
        app_module.app.test_client()
    )

    response = client.get(
        "/api/dji-cloud/readiness",
        environ_base={
            "REMOTE_ADDR":
                "8.8.8.8",
        },
    )

    assert response.status_code == 403