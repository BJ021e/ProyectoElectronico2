import json

from mqtt_diagnostics import read_mqtt_events


def test_missing_log(tmp_path):
    result = read_mqtt_events(
        tmp_path / "nonexistent.jsonl"
    )

    assert result["log_exists"] is False
    assert result["receiver_connected"] is None
    assert result["last_event"] is None
    assert result["recent_events"] == []


def test_reads_latest_valid_event(tmp_path):
    log_file = tmp_path / "mqtt_events.jsonl"

    events = [
        {
            "timestamp": "2026-09-29T05:00:00+00:00",
            "topic": "pe2/diagnostico/local",
            "qos": 1,
            "payload_bytes": 17,
            "diagnostic_ok": True,
        },
        {
            "timestamp": "2026-09-29T05:09:15+00:00",
            "topic": "pe2/diagnostico/tls",
            "qos": 1,
            "payload_bytes": 15,
            "diagnostic_ok": True,
            "private_data": "NO_DEBE_APARECER",
        },
    ]

    with log_file.open("w", encoding="utf-8") as file:
        for event in events:
            file.write(json.dumps(event) + "\n")

        file.write("registro JSON inválido\n")

    result = read_mqtt_events(log_file)

    assert result["log_exists"] is True
    assert result["receiver_connected"] is None
    assert len(result["recent_events"]) == 2

    assert (
        result["last_event"]["topic"]
        == "pe2/diagnostico/tls"
    )

    assert result["last_event"]["diagnostic_ok"] is True

    assert "private_data" not in result["last_event"]


def test_limits_recent_events(tmp_path):
    log_file = tmp_path / "mqtt_events.jsonl"

    with log_file.open("w", encoding="utf-8") as file:
        for index in range(15):
            event = {
                "timestamp": f"2026-09-29T05:00:{index:02d}+00:00",
                "topic": "pe2/diagnostico/tls",
                "qos": 1,
                "payload_bytes": 15,
                "diagnostic_ok": True,
            }

            file.write(json.dumps(event) + "\n")

    result = read_mqtt_events(log_file, limit=10)

    assert len(result["recent_events"]) == 10
    assert (
        result["last_event"]["timestamp"]
        == "2026-09-29T05:00:14+00:00"
    )

def test_mqtt_diagnostics_page():
    from InterfazInit import app

    client = app.test_client()

    response = client.get("/diagnostics/mqtt")

    assert response.status_code == 200
    assert b"Diagn" in response.data
    assert b"/api/diagnostics/mqtt" in response.data
