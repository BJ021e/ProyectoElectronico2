"""Estado diagnóstico reportado por la página DJI Cloud Probe."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from ipaddress import ip_address

ROOT = Path(__file__).resolve().parent

DEFAULT_STATE_PATH = (
    ROOT
    / "diagnosticos_smart_controller"
    / "dji_cloud_client_state.json"
)

_WRITE_LOCK = threading.Lock()


ALLOWED_FIELDS = {
    "bridge_present",
    "license_verified",
    "thing_loaded",
    "thing_connected",
}


def utc_now_iso():
    return datetime.now(
        timezone.utc
    ).isoformat()


def empty_state():
    return {
        "updated_at": None,
        "remote_addr": None,
        "bridge_present": None,
        "license_verified": None,
        "thing_loaded": None,
        "thing_connected": None,
    }


def read_client_state(
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

    return result


def update_client_state(
    values,
    *,
    remote_addr=None,
    state_path=None,
):
    if not isinstance(values, dict):
        raise ValueError(
            "values debe ser un objeto."
        )

    path = (
        Path(state_path)
        if state_path is not None
        else DEFAULT_STATE_PATH
    )

    clean = {}

    for key in ALLOWED_FIELDS:
        value = values.get(key)

        if value is None:
            continue

        if not isinstance(value, bool):
            raise ValueError(
                f"{key} debe ser booleano."
            )

        clean[key] = value

    with _WRITE_LOCK:
        state = read_client_state(
            path
        )

        state.update(clean)

        state["updated_at"] = (
            utc_now_iso()
        )

        if isinstance(
            remote_addr,
            str,
        ):
            state["remote_addr"] = (
                remote_addr[:64]
            )

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temp = path.with_suffix(
            ".json.tmp"
        )

        temp.write_text(
            json.dumps(
                state,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        os.replace(
            temp,
            path,
        )

    return state

def summarize_client_state(
    state,
    stale_after_seconds=30,
):
    if not isinstance(state, dict):
        state = empty_state()

    updated_at = state.get(
        "updated_at"
    )

    age_seconds = None

    if updated_at:
        try:
            updated_dt = (
                datetime.fromisoformat(
                    updated_at
                )
            )

            if updated_dt.tzinfo is None:
                updated_dt = (
                    updated_dt.replace(
                        tzinfo=timezone.utc
                    )
                )

            age_seconds = max(
                0.0,
                (
                    datetime.now(
                        timezone.utc
                    )
                    - updated_dt.astimezone(
                        timezone.utc
                    )
                ).total_seconds(),
            )

        except ValueError:
            age_seconds = None

    reported = bool(updated_at)

    fresh = (
        reported
        and age_seconds is not None
        and age_seconds
        <= stale_after_seconds
    )

    remote_addr = state.get(
        "remote_addr"
    )

    origin = "unknown"
    local_test = False
    remote_private = False

    if remote_addr:
        try:
            parsed_ip = ip_address(
                remote_addr
            )

            if parsed_ip.is_loopback:
                origin = "local"
                local_test = True

            elif parsed_ip.is_private:
                origin = "private_remote"
                remote_private = True

        except ValueError:
            pass

    return {
        "reported": reported,
        "fresh": fresh,
        "age_seconds": (
            round(age_seconds, 1)
            if age_seconds is not None
            else None
        ),
        "updated_at": updated_at,
        "remote_addr": (
            state.get(
                "remote_addr"
            )
        ),
        "bridge_present": (
            state.get(
                "bridge_present"
            )
        ),
        "license_verified": (
            state.get(
                "license_verified"
            )
        ),
        "thing_loaded": (
            state.get(
                "thing_loaded"
            )
        ),
        "thing_connected": (
            state.get(
                "thing_connected"
            )
        ),
        "origin": origin,
        "local_test": local_test,
        "remote_private": remote_private,
    }