import os
from dotenv import load_dotenv


# Cargar variables desde el archivo .env
load_dotenv()


def env_bool(name: str, default: bool = False) -> bool:
    """
    Convierte una variable de entorno de texto a booleano.

    Valores considerados True:
    true, 1, yes, y, on
    """
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"true", "1", "yes", "y", "on"}


class Config:
    # Flask
    SECRET_KEY = os.getenv(
        "FLASK_SECRET_KEY",
        "ground_test_super_secret"
    )

    FLASK_HOST = os.getenv(
        "FLASK_HOST",
        "0.0.0.0"
    )

    FLASK_PORT = int(
        os.getenv("FLASK_PORT", "5050")
    )

    FLASK_DEBUG = env_bool(
        "FLASK_DEBUG",
        True
    )

    # Raspberry Pi
    RPI_IP = os.getenv(
        "RPI_IP",
        "172.20.10.3"
    )

    RPI_PORT = int(
        os.getenv("RPI_PORT", "5000")
    )

    RPI_API_URL = f"http://{RPI_IP}:{RPI_PORT}"

    # Acceso
    ACCESS_CODE = os.getenv(
        "ACCESS_CODE",
        "1234"
    )
    
    # Base de datos
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "sqlite:///data/ground_control.db"
    )
    
    # Integración de dron
    DRONE_TELEMETRY_STALE_SECONDS = float(
        os.getenv(
            "DRONE_TELEMETRY_STALE_SECONDS",
            "5.0"
        )
    )
    
    CAMPAIGN_STORAGE_ROOT = os.getenv(
        "CAMPAIGN_STORAGE_ROOT",
        "data/campaigns",
    )
    
    PHOTOGRAMMETRY_BACKEND = os.getenv(
        "PHOTOGRAMMETRY_BACKEND",
        "MOCK",
    ).strip().upper()
    
    MOCK_PHOTOGRAMMETRY_DELAY_SECONDS = float(
        os.getenv(
            "MOCK_PHOTOGRAMMETRY_DELAY_SECONDS",
            "0",
        )
    )
    
    RED_EDGE_STAGING_ROOT = os.getenv(
        "RED_EDGE_STAGING_ROOT",
        "data/rededge_staging",
    )
    
    RED_EDGE_UPLOAD_BATCH_MAX_FILES = int(
        os.getenv(
            "RED_EDGE_UPLOAD_BATCH_MAX_FILES",
            "25",
        )
    )
    
    RED_EDGE_STAGING_MAX_AGE_HOURS = int(
        os.getenv(
            "RED_EDGE_STAGING_MAX_AGE_HOURS",
            "24",
        )
    )