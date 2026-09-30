from datetime import (
    datetime,
    timedelta,
    timezone,
)

import pytest

from dji_cloud_client_state import (
    read_client_state,
    summarize_client_state,
    update_client_state,
)


def test_empty_client_state(
    tmp_path,
):
    path = tmp_path / "client.json"

    state = read_client_state(
        path
    )

    assert (
        state["bridge_present"]
        is None
    )

    assert (
        state["license_verified"]
        is None
    )


def test_update_client_state(
    tmp_path,
):
    path = tmp_path / "client.json"

    state = update_client_state(
        {
            "bridge_present": True,
            "license_verified": True,
            "thing_loaded": False,
            "thing_connected": False,
        },
        remote_addr="172.20.10.2",
        state_path=path,
    )

    assert (
        state["bridge_present"]
        is True
    )

    assert (
        state["license_verified"]
        is True
    )

    assert (
        state["remote_addr"]
        == "172.20.10.2"
    )


def test_rejects_non_boolean_state(
    tmp_path,
):
    path = tmp_path / "client.json"

    with pytest.raises(
        ValueError
    ):
        update_client_state(
            {
                "bridge_present":
                    "yes",
            },
            state_path=path,
        )


def test_unknown_fields_are_not_persisted(
    tmp_path,
):
    path = tmp_path / "client.json"

    update_client_state(
        {
            "bridge_present": True,

            # Debe ignorarse.
            "app_key":
                "DO_NOT_STORE",

            "password":
                "DO_NOT_STORE",
        },
        state_path=path,
    )

    text = path.read_text(
        encoding="utf-8"
    )

    assert "DO_NOT_STORE" not in text
    assert "app_key" not in text
    assert "password" not in text


def test_summary_marks_recent_report_fresh(
    tmp_path,
):
    path = tmp_path / "client.json"

    update_client_state(
        {
            "bridge_present": True,
        },
        state_path=path,
    )

    summary = summarize_client_state(
        read_client_state(path),
        stale_after_seconds=30,
    )

    assert summary["reported"] is True
    assert summary["fresh"] is True


def test_summary_marks_old_report_stale():
    old_time = (
        datetime.now(
            timezone.utc
        )
        - timedelta(
            minutes=5
        )
    ).isoformat()

    state = {
        "updated_at": old_time,
        "remote_addr": "172.20.10.2",
        "bridge_present": True,
        "license_verified": True,
        "thing_loaded": True,
        "thing_connected": True,
    }

    summary = summarize_client_state(
        state,
        stale_after_seconds=30,
    )

    assert summary["reported"] is True
    assert summary["fresh"] is False

def test_summary_marks_loopback_as_local_test():
    state = {
        "updated_at": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
        "remote_addr": "127.0.0.1",
        "bridge_present": True,
        "license_verified": False,
        "thing_loaded": False,
        "thing_connected": False,
    }

    summary = summarize_client_state(
        state
    )

    assert summary["origin"] == "local"
    assert summary["local_test"] is True
    assert summary["remote_private"] is False


def test_summary_marks_private_remote():
    state = {
        "updated_at": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
        "remote_addr": "172.20.10.2",
        "bridge_present": True,
        "license_verified": True,
        "thing_loaded": True,
        "thing_connected": True,
    }

    summary = summarize_client_state(
        state
    )

    assert (
        summary["origin"]
        == "private_remote"
    )

    assert (
        summary["local_test"]
        is False
    )

    assert (
        summary["remote_private"]
        is True
    )