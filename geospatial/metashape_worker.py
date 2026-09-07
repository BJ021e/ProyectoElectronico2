from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

import Metashape

CANONICAL_MULTISPECTRAL_BANDS = (
    "BLUE",
    "GREEN",
    "RED",
    "NIR",
    "RED_EDGE",
)

EXPECTED_MULTISPECTRAL_BANDS = (
    CANONICAL_MULTISPECTRAL_BANDS
)

def normalize_metashape_band_name(
    value,
) -> str:

    normalized = (
        str(value or "")
        .strip()
        .upper()
        .replace("-", "")
        .replace("_", "")
        .replace(" ", "")
    )

    aliases = {
        "BLUE": "BLUE",
        "GREEN": "GREEN",
        "RED": "RED",
        "NIR": "NIR",
        "REDEDGE": "RED_EDGE",
    }

    return aliases.get(
        normalized,
        normalized,
    )


def build_canonical_band_mapping(
    chunk,
) -> dict:

    layer_by_band = {}

    for sensor in chunk.sensors:

        layer_index = (
            sensor.layer_index
        )

        if layer_index is None:
            continue

        for raw_band in (
            sensor.bands or []
        ):

            band = (
                normalize_metashape_band_name(
                    raw_band
                )
            )

            if (
                band
                not in
                CANONICAL_MULTISPECTRAL_BANDS
            ):
                continue

            previous = (
                layer_by_band.get(
                    band
                )
            )

            if (
                previous is not None
                and previous
                != layer_index
            ):
                raise ValueError(
                    "Metashape asignó múltiples "
                    "capas a la misma banda "
                    f"{band}: "
                    f"{previous}, "
                    f"{layer_index}."
                )

            layer_by_band[
                band
            ] = int(
                layer_index
            )

    missing = [
        band
        for band
        in CANONICAL_MULTISPECTRAL_BANDS
        if band not in layer_by_band
    ]

    if missing:

        raise ValueError(
            "Metashape no permitió resolver "
            "todas las bandas requeridas. "
            f"Faltantes={missing}."
        )

    export_formula = [
        (
            "B"
            + str(
                layer_by_band[
                    band
                ]
                + 1
            )
        )
        for band
        in CANONICAL_MULTISPECTRAL_BANDS
    ]

    return {
        "canonical_order": list(
            CANONICAL_MULTISPECTRAL_BANDS
        ),
        "metashape_layer_by_band": (
            layer_by_band
        ),
        "export_formula": (
            export_formula
        ),
    }

def write_result(
    result_path: Path,
    payload: dict,
) -> None:

    result_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    result_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> int:

    if len(sys.argv) < 3:

        print(
            "Uso: metashape_worker.py "
            "<manifest.json> <result.json>",
            file=sys.stderr,
        )

        return 2

    manifest_path = (
        Path(sys.argv[1])
        .expanduser()
        .resolve()
    )

    result_path = (
        Path(sys.argv[2])
        .expanduser()
        .resolve()
    )

    try:

        manifest = json.loads(
            manifest_path.read_text(
                encoding="utf-8"
            )
        )

        mode = manifest.get(
            "mode"
        )

        if mode == "probe":

            payload = {
                "success": True,
                "mode": "probe",
                "metashape_version": str(
                    Metashape.app.version
                ),
                "message": (
                    "Comunicación con Metashape "
                    "operativa."
                ),
            }

        elif mode == "inspect_inputs":

            payload = inspect_inputs(
                manifest
            )
            
        elif mode == "align_inputs":

            payload = align_inputs(
                manifest
            )

        else:

            raise ValueError(
                "Modo de worker todavía "
                f"no soportado: {mode!r}."
            )

        write_result(
            result_path,
            payload,
        )

        print(
            "METASHAPE_WORKER_OK"
        )

        return 0

    except Exception as exc:

        payload = {
            "success": False,
            "error_message": str(exc),
            "traceback": traceback.format_exc(),
        }

        try:

            write_result(
                result_path,
                payload,
            )

        except Exception:

            pass

        print(
            f"METASHAPE_WORKER_ERROR: {exc}",
            file=sys.stderr,
        )

        return 1

def inspect_inputs(
    manifest: dict,
) -> dict:

    capture_groups = (
        manifest.get(
            "capture_groups"
        )
        or []
    )

    if not capture_groups:
        raise ValueError(
            "No se recibieron grupos "
            "de captura."
        )

    filenames = []
    filegroups = []

    expected = set(
        EXPECTED_MULTISPECTRAL_BANDS
    )

    for group in capture_groups:

        capture_code = (
            group.get(
                "capture_code"
            )
        )

        assets = (
            group.get(
                "assets"
            )
            or []
        )

        by_band = {}

        for asset in assets:

            band = str(
                asset.get(
                    "band",
                    "",
                )
            ).strip().upper()

            path = str(
                asset.get(
                    "path",
                    "",
                )
            ).strip()

            if not band or not path:
                raise ValueError(
                    "Asset inválido en "
                    f"{capture_code}."
                )

            if band in by_band:
                raise ValueError(
                    "Banda duplicada "
                    f"{band} en "
                    f"{capture_code}."
                )

            by_band[band] = path

        received = set(
            by_band
        )

        if received != expected:

            missing = sorted(
                expected - received
            )

            extra = sorted(
                received - expected
            )

            raise ValueError(
                "Captura multiespectral "
                f"incompleta: "
                f"{capture_code}. "
                f"Faltantes={missing}; "
                f"extras={extra}."
            )

        ordered_files = [
            by_band[band]
            for band
            in EXPECTED_MULTISPECTRAL_BANDS
        ]

        for path in ordered_files:

            if not Path(
                path
            ).is_file():

                raise ValueError(
                    "Archivo inexistente: "
                    f"{path}"
                )

        filenames.extend(
            ordered_files
        )

        filegroups.append(
            len(
                ordered_files
            )
        )

    doc = Metashape.Document()

    chunk = doc.addChunk()

    chunk.addPhotos(
        filenames=filenames,
        filegroups=filegroups,
        layout=(
            Metashape
            .MultiplaneLayout
        ),
    )
    
    band_mapping = (
        build_canonical_band_mapping(
            chunk
        )
    )

    sensors = []

    for sensor in chunk.sensors:

        master = sensor.master

        sensors.append({
            "key": sensor.key,
            "label": sensor.label,
            "layer_index": (
                sensor.layer_index
            ),
            "bands": list(
                sensor.bands
            ),
            "master_key": (
                master.key
                if master is not None
                else None
            ),
        })

    cameras = []

    for camera in chunk.cameras:

        cameras.append({
            "key": camera.key,
            "label": camera.label,
            "layer_index": (
                camera.layer_index
            ),
            "sensor_key": (
                camera.sensor.key
                if camera.sensor
                is not None
                else None
            ),
            "master_key": (
                camera.master.key
                if camera.master
                is not None
                else None
            ),
        })

    return {
        "success": True,
        "mode": "inspect_inputs",
        "metashape_version": str(
            Metashape.app.version
        ),
        "capture_group_count": len(
            capture_groups
        ),
        "input_file_count": len(
            filenames
        ),
        "filegroups": filegroups,
        "camera_count": len(
            chunk.cameras
        ),
        "sensor_count": len(
            chunk.sensors
        ),
        "sensors": sensors,
        "cameras": cameras,
        
        "band_mapping": (
            band_mapping
        ),
        
    }
    
def align_inputs(
    manifest: dict,
) -> dict:

    # Primero reutilizamos toda la validación
    # multiespectral que ya quedó comprobada.
    inspection = inspect_inputs(
        manifest
    )

    capture_groups = (
        manifest.get(
            "capture_groups"
        )
        or []
    )

    filenames = []
    filegroups = []

    for group in capture_groups:

        assets = (
            group.get(
                "assets"
            )
            or []
        )

        by_band = {
            str(
                asset.get(
                    "band",
                    ""
                )
            ).strip().upper():
            str(
                asset.get(
                    "path",
                    ""
                )
            ).strip()
            for asset in assets
        }

        ordered_files = [
            by_band[band]
            for band
            in CANONICAL_MULTISPECTRAL_BANDS
        ]

        filenames.extend(
            ordered_files
        )

        filegroups.append(
            len(
                ordered_files
            )
        )

    doc = Metashape.Document()

    chunk = doc.addChunk()

    chunk.addPhotos(
        filenames=filenames,
        filegroups=filegroups,
        layout=(
            Metashape
            .MultiplaneLayout
        ),
    )

    print(
        "METASHAPE_MATCH_PHOTOS_START"
    )

    chunk.matchPhotos(
        downscale=1,
        generic_preselection=True,
        reference_preselection=True,
        filter_stationary_points=True,
        keypoint_limit=40000,
        tiepoint_limit=4000,
    )

    print(
        "METASHAPE_MATCH_PHOTOS_DONE"
    )

    print(
        "METASHAPE_ALIGN_CAMERAS_START"
    )

    chunk.alignCameras()

    print(
        "METASHAPE_ALIGN_CAMERAS_DONE"
    )

    tie_point_count = 0

    if chunk.tie_points is not None:

        points = (
            chunk.tie_points.points
        )

        if points is not None:

            tie_point_count = len(
                points
            )

    master_cameras = [
        camera
        for camera in chunk.cameras
        if (
            camera.master is not None
            and camera.master.key
            == camera.key
        )
    ]

    aligned_cameras = [
        camera
        for camera in chunk.cameras
        if camera.transform is not None
    ]

    aligned_master_cameras = [
        camera
        for camera in master_cameras
        if camera.transform is not None
    ]

    camera_status = []

    for camera in chunk.cameras:

        camera_status.append({
            "key": camera.key,
            "label": camera.label,
            "layer_index": (
                camera.layer_index
            ),
            "master_key": (
                camera.master.key
                if camera.master
                is not None
                else None
            ),
            "aligned": (
                camera.transform
                is not None
            ),
        })

    return {
        "success": True,
        "mode": "align_inputs",
        "metashape_version": str(
            Metashape.app.version
        ),
        "capture_group_count": (
            inspection[
                "capture_group_count"
            ]
        ),
        "input_file_count": (
            inspection[
                "input_file_count"
            ]
        ),
        "filegroups": (
            inspection[
                "filegroups"
            ]
        ),
        "band_mapping": (
            inspection[
                "band_mapping"
            ]
        ),
        "tie_point_count": (
            tie_point_count
        ),
        "camera_count": len(
            chunk.cameras
        ),
        "master_camera_count": len(
            master_cameras
        ),
        "aligned_camera_count": len(
            aligned_cameras
        ),
        "aligned_master_camera_count": len(
            aligned_master_cameras
        ),
        "cameras": (
            camera_status
        ),
    }


if __name__ == "__main__":
    raise SystemExit(
        main()
    )