from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import Config


PROJECT_ROOT = Path(__file__).resolve().parent

class Base(DeclarativeBase):
    pass

def _prepare_database_url(database_url: str) -> str:
    """
    Normaliza la URL de SQLite para que la base de datos se cree
    de forma consistente dentro del proyecto.
    """
    sqlite_prefix = "sqlite:///"

    if not database_url.startswith(sqlite_prefix):
        return database_url

    raw_path = database_url[len(sqlite_prefix):]
    db_path = Path(raw_path)

    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path

    db_path.parent.mkdir(parents=True, exist_ok=True)

    return f"sqlite:///{db_path.as_posix()}"


DATABASE_URL = _prepare_database_url(Config.DATABASE_URL)


engine = create_engine(
    DATABASE_URL,
    future=True
)

if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(
        dbapi_connection,
        connection_record
    ):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False
)


def test_database_connection() -> bool:
    """
    Comprueba que SQLAlchemy puede conectarse correctamente
    a la base de datos configurada.
    """
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))

    return True

def ensure_capture_role_schema(bind=None) -> None:
    """Añade el rol a SQLite existente sin reconstruir tablas ni clasificar datos."""
    bind = engine if bind is None else bind
    if bind.dialect.name != "sqlite":
        return

    with bind.connect() as connection:
        # Serializa comprobación y DDL entre inicializadores concurrentes.
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            columns = connection.exec_driver_sql(
                "PRAGMA table_info(image_captures)"
            ).mappings().all()
            if columns and not any(column["name"] == "role" for column in columns):
                connection.exec_driver_sql(
                    "ALTER TABLE image_captures ADD COLUMN role VARCHAR(20) "
                    "NOT NULL DEFAULT 'UNKNOWN' CONSTRAINT capture_role "
                    "CHECK (role IN ('UNKNOWN', 'FLIGHT', 'CALIBRATION'))"
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def init_database() -> None:
    """
    Crea las tablas registradas en los modelos SQLAlchemy
    que todavía no existan.
    """
    import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    ensure_capture_role_schema()
