import pytest

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError

from database import ensure_capture_role_schema


def test_legacy_capture_role_evolution_is_additive_and_idempotent(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}")
    with engine.begin() as connection:
        connection.exec_driver_sql("""
            CREATE TABLE image_captures (
                id INTEGER PRIMARY KEY,
                capture_code VARCHAR(70) NOT NULL UNIQUE,
                campaign_id INTEGER NOT NULL,
                sequence INTEGER NOT NULL,
                status VARCHAR(20) NOT NULL,
                captured_at DATETIME,
                latitude FLOAT, longitude FLOAT, altitude FLOAT,
                created_at DATETIME NOT NULL,
                UNIQUE (campaign_id, sequence)
            )
        """)
        connection.exec_driver_sql("""
            INSERT INTO image_captures VALUES
            (42, 'CAP-legacy', 9, 3, 'READY', '2020-01-01', 1, 2, 3, '2021-01-01')
        """)
        connection.exec_driver_sql("""
            CREATE TABLE image_assets (
                id INTEGER PRIMARY KEY, capture_id INTEGER REFERENCES image_captures(id),
                storage_path TEXT
            )
        """)
        connection.exec_driver_sql("INSERT INTO image_assets VALUES (8, 42, 'unchanged.tif')")
        original = connection.exec_driver_sql("SELECT * FROM image_captures").all()
        assets = connection.exec_driver_sql("SELECT * FROM image_assets").all()

    ensure_capture_role_schema(engine)
    ensure_capture_role_schema(engine)

    with engine.begin() as connection:
        rows = connection.exec_driver_sql("SELECT * FROM image_captures").all()
        assert [tuple(row[:-1]) for row in rows] == [tuple(row) for row in original]
        assert rows[0][-1] == "UNKNOWN"
        assert connection.exec_driver_sql("SELECT * FROM image_assets").all() == assets
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        connection.exec_driver_sql("""
            INSERT INTO image_captures (id, capture_code, campaign_id, sequence, status, created_at)
            VALUES (43, 'CAP-new', 9, 4, 'CREATED', '2022-01-01')
        """)
        assert connection.exec_driver_sql("SELECT role FROM image_captures WHERE id=43").scalar_one() == "UNKNOWN"
        connection.exec_driver_sql("UPDATE image_captures SET role='CALIBRATION' WHERE id=42")

    ensure_capture_role_schema(engine)
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT role FROM image_captures WHERE id=42").scalar_one() == "CALIBRATION"
        with pytest.raises(IntegrityError):
            connection.exec_driver_sql("UPDATE image_captures SET role='PANEL'")
    engine.dispose()
