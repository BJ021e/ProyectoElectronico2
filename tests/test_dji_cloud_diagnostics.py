from dji_cloud_diagnostics import (
    read_dji_cloud_status,
    record_dji_cloud_contact,
)


def test_missing_dji_cloud_status(tmp_path):
    result = read_dji_cloud_status(
        tmp_path / "missing.json"
    )

    assert result["last_contact_at"] is None
    assert result["last_event"] is None
    assert result["last_ping_at"] is None


def test_records_page_open(tmp_path):
    path = tmp_path / "dji.json"

    result = record_dji_cloud_contact(
        event_type="page_open",
        remote_addr="192.168.1.20",
        status_path=path,
    )

    assert result["last_event"] == "page_open"
    assert result["last_page_open_at"] is not None
    assert result["last_contact_at"] is not None
    assert (
        result["last_remote_addr"]
        == "192.168.1.20"
    )


def test_records_ping_without_losing_page_open(
    tmp_path,
):
    path = tmp_path / "dji.json"

    first = record_dji_cloud_contact(
        event_type="page_open",
        remote_addr="192.168.1.20",
        status_path=path,
    )

    result = record_dji_cloud_contact(
        event_type="ping",
        remote_addr="192.168.1.20",
        client_request_id="probe-test-001",
        user_agent="PE2-Test-Client/1.0",
        status_path=path,
    )

    assert result["last_event"] == "ping"

    assert (
        result["last_page_open_at"]
        == first["last_page_open_at"]
    )

    assert result["last_ping_at"] is not None

    assert (
        result["last_user_agent"]
        == "PE2-Test-Client/1.0"
    )

    assert (
        result["last_client_request_id"]
        == "probe-test-001"
    )

def test_local_contact_does_not_replace_remote_contact(
    tmp_path,
):
    path = tmp_path / "dji.json"

    remote = record_dji_cloud_contact(
        event_type="ping",
        remote_addr="172.20.10.2",
        client_request_id="pilot2-001",
        user_agent="dji-open-platform",
        status_path=path,
    )

    assert (
        remote[
            "last_remote_addr_observed"
        ]
        == "172.20.10.2"
    )

    record_dji_cloud_contact(
        event_type="page_open",
        remote_addr="127.0.0.1",
        user_agent="Local-Test",
        status_path=path,
    )

    final = read_dji_cloud_status(
        path
    )

    assert (
        final["last_remote_addr"]
        == "127.0.0.1"
    )

    assert (
        final[
            "last_remote_addr_observed"
        ]
        == "172.20.10.2"
    )

    assert (
        final[
            "last_remote_user_agent"
        ]
        == "dji-open-platform"
    )

def test_loopback_only_has_no_remote_contact(
    tmp_path,
):
    path = tmp_path / "dji.json"

    result = record_dji_cloud_contact(
        event_type="ping",
        remote_addr="127.0.0.1",
        status_path=path,
    )

    assert (
        result[
            "last_remote_contact_at"
        ]
        is None
    )