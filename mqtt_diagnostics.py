"""Lectura de los eventos MQTT de diagnóstico de PE2."""

import json
from collections import deque
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent

DEFAULT_LOG_PATH = (
    PROJECT_ROOT
    / "diagnosticos_smart_controller"
    / "mqtt_events.jsonl"
)


def normalize_event(raw):
    """Devolver únicamente metadatos de diagnóstico válidos."""

    if not isinstance(raw, dict):
        return None

    timestamp = raw.get("timestamp")
    topic = raw.get("topic")
    qos = raw.get("qos")
    payload_bytes = raw.get("payload_bytes")
    diagnostic_ok = raw.get("diagnostic_ok")

    if not isinstance(timestamp, str):
        return None

    if (
        not isinstance(topic, str)
        or not topic.startswith("pe2/diagnostico/")
        or len(topic) > 128
    ):
        return None

    if type(qos) is not int or qos not in (0, 1, 2):
        return None

    if (
        type(payload_bytes) is not int
        or not 0 <= payload_bytes <= 4096
    ):
        return None

    if type(diagnostic_ok) is not bool:
        return None

    return {
        "timestamp": timestamp,
        "topic": topic,
        "qos": qos,
        "payload_bytes": payload_bytes,
        "diagnostic_ok": diagnostic_ok,
    }


def read_mqtt_events(log_path=None, limit=10):
    """Leer los últimos eventos válidos del registro JSONL."""

    path = Path(log_path) if log_path else DEFAULT_LOG_PATH

    limit = max(1, min(int(limit), 20))
    recent_events = deque(maxlen=limit)

    if not path.is_file():
        return {
            "source": "mqtt_events_jsonl",
            "log_exists": False,
            "receiver_connected": None,
            "last_event": None,
            "recent_events": [],
        }

    with path.open("r", encoding="utf-8") as file:
        for line in file:
            try:
                raw = json.loads(line)
            except (ValueError, TypeError):
                continue

            event = normalize_event(raw)

            if event is not None:
                recent_events.append(event)

    events = list(recent_events)

    return {
        "source": "mqtt_events_jsonl",
        "log_exists": True,
        "receiver_connected": None,
        "last_event": events[-1] if events else None,
        "recent_events": events,
    }
