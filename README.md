# Hortalizas Drone — PE2

El entorno validado para este repositorio usa **Python 3.12.7**, declarado también en `.python-version`. No se afirma compatibilidad con otras versiones de Python.

## Configuración

Copie `.env.example` a `.env` y complete los valores locales. Las variables consumidas por el proyecto son:

| Grupo | Variables |
| --- | --- |
| Flask y acceso | `FLASK_SECRET_KEY`, `FLASK_HOST`, `FLASK_PORT`, `FLASK_DEBUG`, `ACCESS_CODE` |
| Raspberry Pi | `RPI_IP`, `RPI_PORT`, `DRONE_TELEMETRY_STALE_SECONDS` |
| Persistencia | `DATABASE_URL`, `CAMPAIGN_STORAGE_ROOT` |
| Fotogrametría | `PHOTOGRAMMETRY_BACKEND`, `PROCESSING_ENABLED`, `MOCK_PHOTOGRAMMETRY_DELAY_SECONDS`, `METASHAPE_EXECUTABLE` |
| Importación RedEdge | `RED_EDGE_STAGING_ROOT`, `RED_EDGE_UPLOAD_BATCH_MAX_FILES`, `RED_EDGE_STAGING_MAX_AGE_HOURS` |

`METASHAPE_EXECUTABLE` solo es obligatorio cuando `PHOTOGRAMMETRY_BACKEND=METASHAPE`. `PROCESSING_ENABLED` es un guard operativo de demostración; no es un sistema de autorización.

## Demo PE2

1. Active el entorno: `.\.venv\Scripts\Activate.ps1`.
2. Prepare `.env` para la demo con `FLASK_DEBUG=false` y `PROCESSING_ENABLED=false`.
3. Ejecute `python scripts/preflight.py`.
4. Confirme `READY_FOR_VIEWING YES`.
5. Inicie una única instancia: `python InterfazInit.py`.
6. Abra `http://127.0.0.1:5050`, entre a la campaña 6 y muestre los productos persistidos.
7. No pulse **Procesar campaña** durante la exposición. El botón queda deshabilitado y el endpoint devuelve `409` mientras el guard esté desactivado.

La demo no necesita Metashape instalado si solo visualiza productos ya persistidos.

## Procesamiento Metashape

Para ejecutar reconstrucción real se requiere licencia válida de Metashape, `PHOTOGRAMMETRY_BACKEND=METASHAPE`, `PROCESSING_ENABLED=true`, `METASHAPE_EXECUTABLE` apuntando al ejecutable y un directorio `TEMP/TMP` escribible. Ejecute `python scripts/preflight.py` y continúe solo con `READY_FOR_PROCESSING YES`.

Use una sola instancia Flask y `FLASK_DEBUG=false` para procesamientos largos. El executor de PE2 es local y no ofrece recuperación de jobs tras reinicio.

## Backup y restore

El respaldo geoespacial es la pareja formada por:

```text
data/ground_control.db
data/campaigns/
```

No respalde solo la base de datos.

Para respaldar, detenga Flask, cree una copia consistente con la API `sqlite3.Connection.backup`, copie `data/campaigns/` a la misma carpeta/versionado y conserve ambos artefactos con la misma fecha. Ejemplo de la API:

```python
import sqlite3

source = sqlite3.connect("data/ground_control.db")
target = sqlite3.connect(r"D:\backups\pe2-YYYYMMDD\ground_control.db")
source.backup(target)
target.close()
source.close()
```

Para restaurar, detenga Flask, restaure la base de datos y el árbol `data/campaigns/` del mismo respaldo, compruebe que ambos existen con `python scripts/preflight.py` e inicie la aplicación. No mezcle una base de datos con assets de otro respaldo.
