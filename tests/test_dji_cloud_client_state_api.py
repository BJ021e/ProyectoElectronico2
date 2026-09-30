import InterfazInit as app_module


def test_client_state_accepts_private_client(
    monkeypatch,
    tmp_path,
):
    import dji_cloud_client_state

    monkeypatch.setattr(
        dji_cloud_client_state,
        "DEFAULT_STATE_PATH",
        tmp_path / "client.json",
    )

    client = (
        app_module.app.test_client()
    )

    response = client.post(
        "/api/dji-cloud/client-state",
        json={
            "bridge_present": True,
            "license_verified": False,
        },
        environ_base={
            "REMOTE_ADDR":
                "172.20.10.2",
        },
    )

    assert response.status_code == 200

    data = response.get_json()

    assert data["ok"] is True

    assert (
        data["state"][
            "bridge_present"
        ]
        is True
    )


def test_client_state_rejects_public_client():
    client = (
        app_module.app.test_client()
    )

    response = client.post(
        "/api/dji-cloud/client-state",
        json={
            "bridge_present": True,
        },
        environ_base={
            "REMOTE_ADDR":
                "8.8.8.8",
        },
    )

    assert response.status_code == 403


def test_client_state_rejects_invalid_boolean():
    client = (
        app_module.app.test_client()
    )

    response = client.post(
        "/api/dji-cloud/client-state",
        json={
            "bridge_present": "yes",
        },
        environ_base={
            "REMOTE_ADDR":
                "127.0.0.1",
        },
    )

    assert response.status_code == 400