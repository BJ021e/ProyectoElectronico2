from dji_cloud_state import (
    build_runtime_summary,
    read_dji_cloud_state,
    update_dji_cloud_state,
)

def test_runtime_summary_masks_gateway():
    state = {
        "last_message_at":
            "2026-09-30T08:03:47+00:00",
        "last_family": "thing",
        "last_channel": "state",
        "gateway": {
            "sn": "RC_REAL_123456789"
        },
        "devices": {
            "AIRCRAFT001": {
                "sn": "AIRCRAFT001"
            }
        },
    }

    summary = build_runtime_summary(
        state
    )

    assert (
        summary["gateway_detected"]
        is True
    )

    assert (
        summary["device_count"]
        == 1
    )

    assert (
        summary["gateway_id"]
        != "RC_REAL_123456789"
    )


def test_runtime_summary_marks_simulation():
    state = {
        "gateway": {
            "sn": "RC_SIMULADO_001"
        },
        "devices": {},
    }

    summary = build_runtime_summary(
        state
    )

    assert (
        summary["simulated"]
        is True
    )

def test_empty_state(tmp_path):
    path = tmp_path / "state.json"

    state = read_dji_cloud_state(
        path
    )

    assert state["gateway"] is None
    assert state["devices"] == {}


def test_topology_registers_gateway_and_device(
    tmp_path,
):
    path = tmp_path / "state.json"

    record = {
        "received_at":
            "2026-09-30T10:00:00+00:00",
        "topic":
            "sys/product/RC001/status",
        "recognized": True,
        "family": "sys",
        "channel": "status",
        "device_sn": "RC001",
        "method": "update_topo",
        "payload": {
            "data": {
                "device_secret":
                    "[REDACTED]",
                "nonce":
                    "[REDACTED]",
                "sub_devices": [
                    {
                        "sn": "AIRCRAFT001",
                        "device_secret":
                            "[REDACTED]",
                        "nonce":
                            "[REDACTED]",
                    }
                ],
            },
        },
    }

    state = update_dji_cloud_state(
        record,
        state_path=path,
    )

    assert (
        state["gateway"]["sn"]
        == "RC001"
    )

    assert (
        "AIRCRAFT001"
        in state["devices"]
    )


def test_state_updates_device(
    tmp_path,
):
    path = tmp_path / "state.json"

    record = {
        "received_at":
            "2026-09-30T10:01:00+00:00",
        "topic":
            "thing/product/AIRCRAFT001/state",
        "recognized": True,
        "family": "thing",
        "channel": "state",
        "device_sn": "AIRCRAFT001",
        "method": "property.set",
        "payload": {},
    }

    state = update_dji_cloud_state(
        record,
        state_path=path,
    )

    device = state[
        "devices"
    ]["AIRCRAFT001"]

    assert (
        device["last_channel"]
        == "state"
    )

    assert (
        device["last_method"]
        == "property.set"
    )


def test_state_file_contains_no_secret_values(
    tmp_path,
):
    path = tmp_path / "state.json"

    record = {
        "received_at":
            "2026-09-30T10:00:00+00:00",
        "topic":
            "sys/product/RC001/status",
        "recognized": True,
        "family": "sys",
        "channel": "status",
        "device_sn": "RC001",
        "method": "update_topo",
        "payload": {
            "data": {
                "device_secret":
                    "[REDACTED]",
                "nonce":
                    "[REDACTED]",
                "sub_devices": [],
            },
        },
    }

    update_dji_cloud_state(
        record,
        state_path=path,
    )

    text = path.read_text(
        encoding="utf-8"
    )

    assert (
        "device_secret"
        not in text
    )
    assert "nonce" not in text