"""Lectura de los eventos MQTT de diagnóstico de PE2."""

import json
from collections import deque
from pathlib import Path

from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parent

DEFAULT_LOG_PATH = (
    PROJECT_ROOT
    / "diagnosticos_smart_controller"
    / "mqtt_events.jsonl"
)

DEFAULT_STATUS_PATH = (
    PROJECT_ROOT
    / "diagnosticos_smart_controller"
    / "mqtt_receiver_status.json"
)

def read_receiver_status(
    status_path=None,
    *,
    now=None,
    timeout_seconds=15,
):
    """Consultar el último heartbeat del receptor."""

    path = (
        Path(status_path)
        if status_path is not None
        else DEFAULT_STATUS_PATH
    )

    unknown = {
        "state": "unknown",
        "connected": None,
        "last_heartbeat_at": None,
    }

    if not path.is_file():
        return unknown

    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        timestamp = data["timestamp"]

        if (
            not isinstance(timestamp, str)
            or type(data["process_running"]) is not bool
            or type(data["broker_connected"]) is not bool
            or type(data["subscribed"]) is not bool
        ):
            return unknown

        heartbeat_at = datetime.fromisoformat(
            timestamp.replace("Z", "+00:00")
        )

        if heartbeat_at.tzinfo is None:
            return unknown

    except (OSError, ValueError, TypeError, KeyError):
        return unknown

    current_time = now or datetime.now(timezone.utc)

    age_seconds = (
        current_time - heartbeat_at
    ).total_seconds()

    if (
        age_seconds < -5
        or age_seconds > timeout_seconds
    ):
        state = "stale"
        connected = False

    elif not data["process_running"]:
        state = "stopped"
        connected = False

    elif (
        data["broker_connected"]
        and data["subscribed"]
    ):
        state = "connected"
        connected = True

    else:
        state = "disconnected"
        connected = False

    return {
        "state": state,
        "connected": connected,
        "last_heartbeat_at": timestamp,
    }

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
