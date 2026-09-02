from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from config import Config


PROJECT_ROOT = Path(__file__).resolve().parent


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