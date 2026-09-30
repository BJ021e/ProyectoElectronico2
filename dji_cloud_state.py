"""Estado persistente y seguro de DJI Cloud MQTT."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent

DEFAULT_STATE_PATH = (
    ROOT
    / "diagnosticos_smart_controller"
    / "dji_cloud_runtime_status.json"
)

_WRITE_LOCK = threading.Lock()

DEFAULT_RECEIVER_STATUS_PATH = (
    ROOT
    / "diagnosticos_smart_controller"
    / "dji_cloud_mqtt_receiver_status.json"
)

def utc_now_iso():
    return datetime.now(
        timezone.utc
    ).isoformat()


def empty_state():
    return {
        "updated_at": None,
        "last_message_at": None,
        "last_topic": None,
        "last_family": None,
        "last_channel": None,
        "gateway": None,
        "devices": {},
    }


def read_dji_cloud_state(
    state_path=None,
):
    path = (
        Path(state_path)
        if state_path is not None
        else DEFAULT_STATE_PATH
    )

    if not path.is_file():
        return empty_state()

    try:
        value = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except (
        OSError,
        json.JSONDecodeError,
    ):
        return empty_state()

    if not isinstance(value, dict):
        return empty_state()

    result = empty_state()
    result.update(value)

    if not isinstance(
        result.get("devices"),
        dict,
    ):
        result["devices"] = {}

    return result


def _save_state(
    state,
    path,
):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_path = path.with_suffix(
        ".json.tmp"
    )

    temp_path.write_text(
        json.dumps(
            state,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    os.replace(
        temp_path,
        path,
    )


def update_dji_cloud_state(
    record,
    *,
    state_path=None,
):
    path = (
        Path(state_path)
        if state_path is not None
        else DEFAULT_STATE_PATH
    )

    if not isinstance(record, dict):
        raise ValueError(
            "record debe ser un diccionario."
        )

    now = utc_now_iso()

    with _WRITE_LOCK:
        state = read_dji_cloud_state(
            path
        )

        state["updated_at"] = now
        state["last_message_at"] = (
            record.get("received_at")
            or now
        )
        state["last_topic"] = (
            record.get("topic")
        )
        state["last_family"] = (
            record.get("family")
        )
        state["last_channel"] = (
            record.get("channel")
        )

        device_sn = record.get(
            "device_sn"
        )

        family = record.get(
            "family"
        )

        channel = record.get(
            "channel"
        )

        if (
            family == "sys"
            and channel == "status"
            and device_sn
        ):
            state["gateway"] = {
                "sn": device_sn,
                "last_seen_at": (
                    record.get(
                        "received_at"
                    )
                    or now
                ),
            }

            payload = record.get(
                "payload",
                {},
            )

            data = (
                payload.get("data", {})
                if isinstance(
                    payload,
                    dict,
                )
                else {}
            )

            sub_devices = data.get(
                "sub_devices",
                [],
            )

            if isinstance(
                sub_devices,
                list,
            ):
                for item in sub_devices:
                    if not isinstance(
                        item,
                        dict,
                    ):
                        continue

                    sn = item.get("sn")

                    if not sn:
                        continue

                    previous = (
                        state["devices"]
                        .get(
                            sn,
                            {},
                        )
                    )

                    state["devices"][sn] = {
                        **previous,
                        "sn": sn,
                        "source": (
                            "topology"
                        ),
                        "last_seen_at": (
                            record.get(
                                "received_at"
                            )
                            or now
                        ),
                    }

        elif (
            family == "thing"
            and device_sn
        ):
            previous = (
                state["devices"]
                .get(
                    device_sn,
                    {},
                )
            )

            state["devices"][
                device_sn
            ] = {
                **previous,
                "sn": device_sn,
                "last_channel": (
                    channel
                ),
                "last_method": (
                    record.get(
                        "method"
                    )
                ),
                "last_seen_at": (
                    record.get(
                        "received_at"
                    )
                    or now
                ),
            }

        _save_state(
            state,
            path,
        )

    return state

def _mask_identifier(value):
    if not value:
        return None

    value = str(value)

    if len(value) <= 6:
        return "***"

    return (
        value[:3]
        + "***"
        + value[-3:]
    )


def build_runtime_summary(state):
    if not isinstance(state, dict):
        state = empty_state()

    gateway = state.get("gateway")

    gateway_sn = (
        gateway.get("sn")
        if isinstance(gateway, dict)
        else None
    )

    devices = state.get(
        "devices",
        {},
    )

    if not isinstance(devices, dict):
        devices = {}

    simulated = bool(
        gateway_sn
        and "SIMULADO" in gateway_sn.upper()
    )

    return {
        "available": True,
        "gateway_detected": (
            gateway_sn is not None
        ),
        "gateway_id": (
            _mask_identifier(
                gateway_sn
            )
        ),
        "device_count": len(devices),
        "last_message_at": (
            state.get(
                "last_message_at"
            )
        ),
        "last_family": (
            state.get(
                "last_family"
            )
        ),
        "last_channel": (
            state.get(
                "last_channel"
            )
        ),
        "simulated": simulated,
    }

def read_dji_cloud_receiver_status(
    status_path=None,
):
    path = (
        Path(status_path)
        if status_path is not None
        else DEFAULT_RECEIVER_STATUS_PATH
    )

    if not path.is_file():
        return {
            "state": "unknown",
            "last_heartbeat_at": None,
        }

    try:
        value = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except (
        OSError,
        json.JSONDecodeError,
    ):
        return {
            "state": "unknown",
            "last_heartbeat_at": None,
        }

    if not isinstance(value, dict):
        return {
            "state": "unknown",
            "last_heartbeat_at": None,
        }

    return value

def summarize_receiver_status(
    status,
    stale_after_seconds=20,
):
    if not isinstance(status, dict):
        status = {}

    raw_state = status.get(
        "state",
        "unknown",
    )

    heartbeat = status.get(
        "last_heartbeat_at"
    )

    age_seconds = None

    if heartbeat:
        try:
            heartbeat_dt = (
                datetime.fromisoformat(
                    heartbeat
                )
            )

            if heartbeat_dt.tzinfo is None:
                heartbeat_dt = (
                    heartbeat_dt.replace(
                        tzinfo=timezone.utc
                    )
                )

            age_seconds = max(
                0.0,
                (
                    datetime.now(
                        timezone.utc
                    )
                    - heartbeat_dt.astimezone(
                        timezone.utc
                    )
                ).total_seconds(),
            )

        except ValueError:
            age_seconds = None

    effective_state = raw_state

    if raw_state == "connected":
        if (
            age_seconds is None
            or age_seconds
            > stale_after_seconds
        ):
            effective_state = "stale"

    return {
        "state": effective_state,
        "reported_state": raw_state,
        "last_heartbeat_at": heartbeat,
        "heartbeat_age_seconds": (
            round(age_seconds, 1)
            if age_seconds is not None
            else None
        ),
    }