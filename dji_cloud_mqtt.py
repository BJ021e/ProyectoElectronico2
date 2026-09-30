"""Utilidades de diagnóstico MQTT para DJI Cloud API."""

from __future__ import annotations

import copy
import json
import re
from datetime import datetime, timezone


_SYS_STATUS_RE = re.compile(
    r"^sys/product/(?P<sn>[^/]+)/status$"
)

_THING_RE = re.compile(
    r"^thing/product/(?P<sn>[^/]+)/"
    r"(?P<channel>"
    r"osd|state|events|requests|services_reply"
    r")$"
)


SENSITIVE_KEYS = {
    "device_secret",
    "nonce",
    "password",
    "passwd",
    "token",
    "access_token",
    "refresh_token",
    "app_key",
    "app_license",
    "license",
    "secret",
}


def utc_now_iso():
    return datetime.now(
        timezone.utc
    ).isoformat()


def parse_dji_topic(topic):
    if not isinstance(topic, str):
        return {
            "recognized": False,
            "topic": str(topic),
        }

    match = _SYS_STATUS_RE.fullmatch(topic)

    if match:
        return {
            "recognized": True,
            "family": "sys",
            "channel": "status",
            "device_sn": match.group("sn"),
        }

    match = _THING_RE.fullmatch(topic)

    if match:
        return {
            "recognized": True,
            "family": "thing",
            "channel": match.group("channel"),
            "device_sn": match.group("sn"),
        }

    return {
        "recognized": False,
        "topic": topic,
    }


def decode_json_payload(payload):
    if isinstance(payload, bytes):
        payload = payload.decode(
            "utf-8",
            errors="replace",
        )

    if not isinstance(payload, str):
        return None

    try:
        value = json.loads(payload)

    except json.JSONDecodeError:
        return None

    if not isinstance(value, dict):
        return None

    return value


def redact_sensitive(value):
    if isinstance(value, dict):
        clean = {}

        for key, item in value.items():
            normalized = str(key).lower()

            if normalized in SENSITIVE_KEYS:
                clean[key] = "[REDACTED]"
            else:
                clean[key] = redact_sensitive(
                    item
                )

        return clean

    if isinstance(value, list):
        return [
            redact_sensitive(item)
            for item in value
        ]

    return copy.deepcopy(value)


def build_event_record(
    *,
    topic,
    payload,
    qos=0,
):
    raw_bytes = (
        payload
        if isinstance(payload, bytes)
        else str(payload).encode(
            "utf-8",
            errors="replace",
        )
    )

    topic_info = parse_dji_topic(topic)
    decoded = decode_json_payload(payload)

    record = {
        "received_at": utc_now_iso(),
        "topic": topic,
        "qos": int(qos),
        "payload_bytes": len(raw_bytes),
        "recognized": (
            topic_info.get(
                "recognized",
                False,
            )
        ),
    }

    if topic_info.get("recognized"):
        record.update({
            "family": topic_info.get(
                "family"
            ),
            "channel": topic_info.get(
                "channel"
            ),
            "device_sn": topic_info.get(
                "device_sn"
            ),
        })

    if decoded is None:
        record["json_valid"] = False
        return record

    record["json_valid"] = True

    record["method"] = decoded.get(
        "method"
    )
    record["tid"] = decoded.get("tid")
    record["bid"] = decoded.get("bid")
    record["device_timestamp"] = (
        decoded.get("timestamp")
    )

    record["payload"] = (
        redact_sensitive(decoded)
    )

    return record


def build_topology_reply(
    *,
    topic,
    payload,
):
    topic_info = parse_dji_topic(topic)

    if not (
        topic_info.get("recognized")
        and topic_info.get("family")
        == "sys"
        and topic_info.get("channel")
        == "status"
    ):
        return None

    decoded = decode_json_payload(payload)

    if not decoded:
        return None

    if decoded.get("method") != "update_topo":
        return None

    gateway_sn = topic_info[
        "device_sn"
    ]

    reply_topic = (
        f"sys/product/"
        f"{gateway_sn}/status_reply"
    )

    reply = {
        "tid": decoded.get("tid"),
        "bid": decoded.get("bid"),
        "timestamp": int(
            datetime.now(
                timezone.utc
            ).timestamp() * 1000
        ),
        "method": "update_topo",
        "data": {
            "result": 0,
        },
    }

    return {
        "topic": reply_topic,
        "payload": reply,
    }