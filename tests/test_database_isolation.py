from pathlib import Path

from database import (
    DATABASE_URL,
    PROJECT_ROOT,
)


def test_database_is_not_development_database():
    development_database = (
        PROJECT_ROOT
        / "data"
        / "ground_control.db"
    ).resolve()

    assert DATABASE_URL.startswith(
        "sqlite:///"
    )


    configured_path = Path(
        DATABASE_URL.removeprefix(
            "sqlite:///"
        )
    ).resolve()


    assert (
        configured_path
        !=
        development_database
    )


def test_database_name_is_test_database():
    assert (
        "test_ground_control.db"
        in DATABASE_URL
    )