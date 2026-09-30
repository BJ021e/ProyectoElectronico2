import json

from dji_cloud_mqtt import (
    build_event_record,
    build_topology_reply,
    parse_dji_topic,
)


def test_parse_status_topic():
    result = parse_dji_topic(
        "sys/product/RC123/status"
    )

    assert result == {
        "recognized": True,
        "family": "sys",
        "channel": "status",
        "device_sn": "RC123",
    }


def test_parse_osd_topic():
    result = parse_dji_topic(
        "thing/product/DRONE123/osd"
    )

    assert result["recognized"] is True
    assert result["family"] == "thing"
    assert result["channel"] == "osd"
    assert (
        result["device_sn"]
        == "DRONE123"
    )


def test_unknown_topic():
    result = parse_dji_topic(
        "pe2/diagnostico/test"
    )

    assert result["recognized"] is False


def test_sensitive_fields_are_redacted():
    payload = {
        "tid": "tid-001",
        "bid": "bid-001",
        "method": "update_topo",
        "timestamp": 1234567890000,
        "data": {
            "device_secret": "SECRET_VALUE",
            "nonce": "NONCE_VALUE",
            "sub_devices": [
                {
                    "sn": "AIRCRAFT001",
                    "device_secret": (
                        "AIRCRAFT_SECRET"
                    ),
                    "nonce": (
                        "AIRCRAFT_NONCE"
                    ),
                }
            ],
        },
    }

    result = build_event_record(
        topic=(
            "sys/product/RC001/status"
        ),
        payload=json.dumps(payload),
        qos=1,
    )

    safe = result["payload"]

    assert (
        safe["data"]["device_secret"]
        == "[REDACTED]"
    )

    assert (
        safe["data"]["nonce"]
        == "[REDACTED]"
    )

    assert (
        safe["data"]["sub_devices"][0]
        ["device_secret"]
        == "[REDACTED]"
    )

    assert (
        safe["data"]["sub_devices"][0]
        ["nonce"]
        == "[REDACTED]"
    )


def test_build_topology_reply():
    payload = {
        "tid": "tid-001",
        "bid": "bid-001",
        "method": "update_topo",
        "timestamp": 1234567890000,
        "data": {
            "type": 119,
            "sub_type": 0,
            "device_secret": "secret",
            "nonce": "nonce",
            "sub_devices": [],
        },
    }

    result = build_topology_reply(
        topic=(
            "sys/product/RC001/status"
        ),
        payload=json.dumps(payload),
    )

    assert (
        result["topic"]
        == "sys/product/RC001/status_reply"
    )

    assert (
        result["payload"]["method"]
        == "update_topo"
    )

    assert (
        result["payload"]["data"]["result"]
        == 0
    )


def test_invalid_json_is_detected():
    result = build_event_record(
        topic=(
            "thing/product/ABC/state"
        ),
        payload=b"not-json",
        qos=0,
    )

    assert result["recognized"] is True
    assert result["json_valid"] is False