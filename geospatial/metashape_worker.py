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

        elif mode == "inspect_reflectance":

            payload = inspect_reflectance(
                manifest
            )

        elif mode == "process":

            payload = process_photogrammetry(
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
        downscale=2,
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

def inspect_reflectance(
    manifest: dict,
) -> dict:

    capture_groups = (
        manifest.get("capture_groups")
        or []
    )

    if not capture_groups:
        raise ValueError(
            "No se recibieron grupos de captura."
        )

    filenames = []
    filegroups = []

    expected = set(
        CANONICAL_MULTISPECTRAL_BANDS
    )

    for group in capture_groups:

        capture_code = group.get(
            "capture_code"
        )

        assets = (
            group.get("assets")
            or []
        )

        by_band = {}

        for asset in assets:

            band = str(
                asset.get("band", "")
            ).strip().upper()

            path = str(
                asset.get("path", "")
            ).strip()

            if not band or not path:
                raise ValueError(
                    f"Asset inválido en "
                    f"{capture_code}."
                )

            if band in by_band:
                raise ValueError(
                    f"Banda duplicada {band} "
                    f"en {capture_code}."
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
                f"incompleta: {capture_code}. "
                f"Faltantes={missing}; "
                f"extras={extra}."
            )

        ordered_files = [
            by_band[band]
            for band
            in CANONICAL_MULTISPECTRAL_BANDS
        ]

        for path in ordered_files:

            if not Path(path).is_file():
                raise ValueError(
                    f"Archivo inexistente: "
                    f"{path}"
                )

        filenames.extend(
            ordered_files
        )

        filegroups.append(
            len(ordered_files)
        )

    doc = Metashape.Document()

    chunk = doc.addChunk()

    chunk.addPhotos(
        filenames=filenames,
        filegroups=filegroups,
        layout=Metashape.MultiplaneLayout,
    )

    print(
        "METASHAPE_REFLECTANCE_PANEL_SEARCH_START"
    )

    chunk.locateReflectancePanels()

    print(
        "METASHAPE_REFLECTANCE_PANEL_SEARCH_DONE"
    )

    camera_groups = []

    for group in chunk.camera_groups:

        camera_groups.append({
            "key": group.key,
            "label": group.label,
            "type": str(group.type),
        })

    calibration_cameras = [
        camera
        for camera in chunk.cameras
        if (
            camera.group is not None
            and str(
                camera.group.label
            ).strip().lower()
            == "calibration images"
        )
    ]

    calibration_master_keys = sorted({
        camera.master.key
        if camera.master is not None
        else camera.key
        for camera in calibration_cameras
    })

    perform_calibration = bool(
        manifest.get(
            "perform_calibration",
            False,
        )
    )

    sensitivity_before = None
    sensitivity_after = None

    sensor_status = []

    for sensor in chunk.sensors:

        sensor_status.append({
            "key": sensor.key,
            "label": sensor.label,
            "layer_index": sensor.layer_index,
            "bands": list(
                sensor.bands
            ),
            "normalize_sensitivity": bool(
                sensor.normalize_sensitivity
            ),
            "sensitivity": list(
                sensor.sensitivity
            ),
        })


    if perform_calibration:

        if not calibration_cameras:
            raise ValueError(
                "No se detectaron imágenes "
                "de panel de reflectancia."
            )

        missing_panel_calibration = []

        for camera in calibration_cameras:

            metadata = dict(
                camera.meta or {}
            )

            if (
                "ReflectancePanel/Calibration"
                not in metadata
            ):
                missing_panel_calibration.append(
                    camera.key
                )

        if missing_panel_calibration:
            raise ValueError(
                "Existen imágenes de panel "
                "sin coeficiente de calibración: "
                f"{missing_panel_calibration}"
            )

        sensitivity_before = {
            str(sensor.key): list(
                sensor.sensitivity
            )
            for sensor in chunk.sensors
        }

        for sensor in chunk.sensors:
            sensor.normalize_sensitivity = True

        print(
            "METASHAPE_REFLECTANCE_CALIBRATION_START"
        )

        chunk.calibrateReflectance(
            use_reflectance_panels=True,
            use_sun_sensor=False,
        )

        print(
            "METASHAPE_REFLECTANCE_CALIBRATION_DONE"
        )

        sensitivity_after = {
            str(sensor.key): list(
                sensor.sensitivity
            )
            for sensor in chunk.sensors
        }

    calibration_camera_details = []

    for camera in calibration_cameras:

        calibration_camera_details.append({
            "key": camera.key,
            "label": camera.label,
            "layer_index": (
                camera.layer_index
            ),
            "master_key": (
                camera.master.key
                if camera.master is not None
                else None
            ),
            "enabled": bool(
                camera.enabled
            ),
            "group": (
                camera.group.label
                if camera.group is not None
                else None
            ),
        })

    calibration_enabled_count = sum(
        1
        for camera in calibration_cameras
        if camera.enabled
    )

    calibration_disabled_count = (
        len(calibration_cameras)
        - calibration_enabled_count
    )

    panel_calibration_metadata = []

    for camera in calibration_cameras:

        meta = dict(
            camera.meta or {}
        )

        relevant_meta = {
            str(key): str(value)
            for key, value in meta.items()
            if (
                "reflectance" in str(key).lower()
                or "panel" in str(key).lower()
                or "irradiance" in str(key).lower()
                or "sun" in str(key).lower()
            )
        }

        panel_calibration_metadata.append({
            "key": camera.key,
            "label": camera.label,
            "layer_index": camera.layer_index,
            "master_key": (
                camera.master.key
                if camera.master is not None
                else None
            ),
            "enabled": bool(
                camera.enabled
            ),
            "meta": relevant_meta,
        })

    sensor_status = []

    for sensor in chunk.sensors:

        sensor_status.append({
            "key": sensor.key,
            "label": sensor.label,
            "layer_index": sensor.layer_index,
            "bands": list(
                sensor.bands
            ),
            "normalize_sensitivity": bool(
                sensor.normalize_sensitivity
            ),
        })

    return {
        "success": True,
        "mode": (
            "calibrate_reflectance"
            if perform_calibration
            else "inspect_reflectance"
        ),
        "capture_group_count": len(
            capture_groups
        ),
        "input_file_count": len(
            filenames
        ),
        "camera_count": len(
            chunk.cameras
        ),
        "sensor_count": len(
            chunk.sensors
        ),
        "camera_groups": (
            camera_groups
        ),
        "calibration_camera_count": len(
            calibration_cameras
        ),
        "calibration_master_count": len(
            calibration_master_keys
        ),
        "calibration_master_keys": (
            calibration_master_keys
        ),
        "calibration_cameras": (
            calibration_camera_details
        ),
        "calibration_enabled_count": (
            calibration_enabled_count
        ),
        "calibration_disabled_count": (
            calibration_disabled_count
        ),
        "panel_calibration_metadata": (
            panel_calibration_metadata
        ),
        "sensor_status": (
            sensor_status
        ),
        "reflectance_calibrated": (
            perform_calibration
        ),
        "use_reflectance_panels": (
            True
            if perform_calibration
            else None
        ),
        "use_sun_sensor": (
            False
            if perform_calibration
            else None
        ),
        "sensitivity_before": (
            sensitivity_before
        ),
        "sensitivity_after": (
            sensitivity_after
        ),
    }

def _load_process_chunk(
    manifest: dict,
):

    capture_groups = (
        manifest.get("capture_groups")
        or []
    )

    if not capture_groups:
        raise ValueError(
            "No se recibieron grupos "
            "de captura."
        )

    expected = set(
        CANONICAL_MULTISPECTRAL_BANDS
    )

    filenames = []
    filegroups = []

    for group in capture_groups:

        capture_code = str(
            group.get(
                "capture_code",
                "",
            )
        ).strip()

        assets = (
            group.get("assets")
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
                    f"Banda duplicada "
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
            in CANONICAL_MULTISPECTRAL_BANDS
        ]

        for path in ordered_files:

            if not Path(path).is_file():
                raise ValueError(
                    "Archivo inexistente: "
                    f"{path}"
                )

        filenames.extend(
            ordered_files
        )

        filegroups.append(
            len(ordered_files)
        )

    doc = Metashape.Document()

    chunk = doc.addChunk()

    chunk.addPhotos(
        filenames=filenames,
        filegroups=filegroups,
        layout=Metashape.MultiplaneLayout,
    )

    return (
        doc,
        chunk,
        filenames,
        filegroups,
    )


def _get_processing_projection(
    chunk,
):

    if chunk.crs is None:
        raise ValueError(
            "Metashape no pudo determinar "
            "el CRS de la campaña."
        )

    projection = (
        Metashape.OrthoProjection()
    )

    projection.crs = chunk.crs

    return projection


def process_photogrammetry(
    manifest: dict,
) -> dict:

    output_dir = Path(
        manifest.get(
            "output_dir",
            "",
        )
    ).expanduser().resolve()

    if not str(
        manifest.get(
            "output_dir",
            "",
        )
    ).strip():

        raise ValueError(
            "No se recibió output_dir."
        )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    project_path = (
        output_dir
        / "metashape_project.psx"
    )

    dsm_path = (
        output_dir
        / "metashape_dsm.tif"
    )

    orthomosaic_native_path = (
        output_dir
        / (
            "metashape_orthomosaic_"
            "native.tif"
        )
    )

    (
        doc,
        chunk,
        filenames,
        filegroups,
    ) = _load_process_chunk(
        manifest
    )

    print(
        "METASHAPE_PROCESS_IMPORT_DONE"
    )

    #
    # 1. Detectar paneles de reflectancia.
    #

    chunk.locateReflectancePanels()

    calibration_cameras = [
        camera
        for camera in chunk.cameras
        if (
            camera.group is not None
            and str(
                camera.group.label
            ).strip().lower()
            == "calibration images"
        )
    ]

    if not calibration_cameras:
        raise ValueError(
            "No se detectaron imágenes "
            "de calibración de "
            "reflectancia."
        )

    calibration_master_keys = {
        (
            camera.master.key
            if camera.master is not None
            else camera.key
        )
        for camera
        in calibration_cameras
    }

    missing_panel_calibration = []

    for camera in calibration_cameras:

        metadata = dict(
            camera.meta or {}
        )

        if (
            "ReflectancePanel/Calibration"
            not in metadata
        ):
            missing_panel_calibration.append(
                camera.key
            )

        #
        # Nunca permitir que las imágenes
        # del panel entren al SfM.
        #
        camera.enabled = False

    if missing_panel_calibration:

        raise ValueError(
            "Existen imágenes de panel "
            "sin coeficiente de "
            "calibración: "
            f"{missing_panel_calibration}"
        )

    print(
        "METASHAPE_PROCESS_"
        "PANELS_VALIDATED"
    )

    #
    # 2. Calibración radiométrica.
    #

    for sensor in chunk.sensors:
        sensor.normalize_sensitivity = True

    chunk.calibrateReflectance(
        use_reflectance_panels=True,
        use_sun_sensor=False,
    )

    print(
        "METASHAPE_PROCESS_"
        "REFLECTANCE_CALIBRATED"
    )

    #
    # 3. Mapeo de bandas que necesitamos
    #    posteriormente en PE2.
    #

    band_mapping = (
        build_canonical_band_mapping(
            chunk
        )
    )

    #
    # 4. Guardamos proyecto antes de la
    #    reconstrucción pesada.
    #

    doc.save(
        str(project_path)
    )

    #
    # doc.save(path) funciona como Save As
    # en la API de Metashape. Después de
    # guardar debemos volver a obtener el
    # chunk asociado al documento.
    #

    chunk = doc.chunk

    if chunk is None:
        raise ValueError(
            "Metashape perdió el chunk "
            "después de guardar el proyecto."
        )

    #
    # Revalidamos el mapeo sobre el chunk
    # perteneciente al proyecto PSX.
    #

    band_mapping = (
        build_canonical_band_mapping(
            chunk
        )
    )

    #
    # 5. SfM / alineamiento.
    #

    print(
        "METASHAPE_PROCESS_MATCH_START"
    )

    chunk.matchPhotos(
        downscale=2,
        generic_preselection=True,
        reference_preselection=True,
        filter_stationary_points=True,
        keypoint_limit=40000,
        tiepoint_limit=4000,
    )

    print(
        "METASHAPE_PROCESS_MATCH_DONE"
    )

    chunk.alignCameras()

    print(
        "METASHAPE_PROCESS_ALIGNMENT_DONE"
    )

    enabled_master_keys = {
        (
            camera.master.key
            if camera.master is not None
            else camera.key
        )
        for camera in chunk.cameras
        if camera.enabled
    }

    aligned_master_keys = {
        (
            camera.master.key
            if camera.master is not None
            else camera.key
        )
        for camera in chunk.cameras
        if (
            camera.enabled
            and camera.transform
            is not None
        )
    }

    if not aligned_master_keys:

        raise ValueError(
            "Metashape no logró alinear "
            "ninguna posición de vuelo."
        )

    master_camera_count = len(
        enabled_master_keys
    )

    aligned_master_camera_count = len(
        aligned_master_keys
    )

    alignment_percent = (
        100.0
        * aligned_master_camera_count
        / master_camera_count
        if master_camera_count
        else 0.0
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

    doc.save()

    #
    # 6. Depth maps.
    #
    # downscale=4 = Medium para
    # buildDepthMaps.
    #

    print(
        "METASHAPE_PROCESS_"
        "DEPTH_MAPS_START"
    )

    chunk.buildDepthMaps(
        downscale=4,
        filter_mode=(
            Metashape.MildFiltering
        ),
        reuse_depth=False,
    )

    print(
        "METASHAPE_PROCESS_"
        "DEPTH_MAPS_DONE"
    )

    doc.save()

    #
    # 7. Nube de puntos.
    #
    # No necesitamos colores para generar
    # nuestro DSM/ortomosaico.
    #

    print(
        "METASHAPE_PROCESS_"
        "POINT_CLOUD_START"
    )

    chunk.buildPointCloud(
        source_data=(
            Metashape.DepthMapsData
        ),
        point_colors=False,
        point_confidence=False,
        keep_depth=True,
    )

    print(
        "METASHAPE_PROCESS_"
        "POINT_CLOUD_DONE"
    )

    doc.save()

    #
    # 8. DSM.
    #
    # No se clasificó terreno, por tanto
    # conceptualmente esto es DSM,
    # no DTM.
    #

    projection = (
        _get_processing_projection(
            chunk
        )
    )

    print(
        "METASHAPE_PROCESS_DSM_START"
    )

    chunk.buildDem(
        source_data=(
            Metashape.PointCloudData
        ),
        interpolation=(
            Metashape.EnabledInterpolation
        ),
        projection=projection,
    )

    print(
        "METASHAPE_PROCESS_DSM_DONE"
    )

    if chunk.elevation is None:
        raise ValueError(
            "Metashape terminó Build DEM "
            "sin generar una superficie."
        )

    doc.save()

    #
    # 9. Ortomosaico multiespectral.
    #

    print(
        "METASHAPE_PROCESS_"
        "ORTHOMOSAIC_START"
    )

    chunk.buildOrthomosaic(
        surface_data=(
            Metashape.ElevationData
        ),
        blending_mode=(
            Metashape.MosaicBlending
        ),
        fill_holes=True,
        ghosting_filter=False,
        color_enhancement=False,
        refine_seamlines=False,
        projection=projection,
    )

    print(
        "METASHAPE_PROCESS_"
        "ORTHOMOSAIC_DONE"
    )

    if chunk.orthomosaic is None:
        raise ValueError(
            "Metashape terminó "
            "Build Orthomosaic sin "
            "generar ortomosaico."
        )

    doc.save()

    #
    # 10. Export DSM.
    #

    print(
        "METASHAPE_PROCESS_"
        "EXPORT_DSM_START"
    )

    chunk.exportRaster(
        path=str(
            dsm_path
        ),
        source_data=(
            Metashape.ElevationData
        ),
        projection=projection,
        save_alpha=False,
        clip_to_boundary=True,
    )

    if not dsm_path.is_file():
        raise ValueError(
            "Metashape no generó el "
            "GeoTIFF DSM."
        )

    print(
        "METASHAPE_PROCESS_"
        "EXPORT_DSM_DONE"
    )

    #
    # 11. Exportar ortomosaico NATIVO.
    #
    # RasterTransformNone conserva las
    # cinco bandas originales y los
    # valores radiométricos.
    #

    print(
        "METASHAPE_PROCESS_"
        "EXPORT_ORTHO_START"
    )

    chunk.exportRaster(
        path=str(
            orthomosaic_native_path
        ),
        source_data=(
            Metashape.OrthomosaicData
        ),
        projection=projection,
        raster_transform=(
            Metashape.RasterTransformNone
        ),
        save_alpha=False,
        clip_to_boundary=True,
    )

    if not orthomosaic_native_path.is_file():
        raise ValueError(
            "Metashape no generó el "
            "GeoTIFF multiespectral."
        )

    print(
        "METASHAPE_PROCESS_"
        "EXPORT_ORTHO_DONE"
    )

    doc.save()

    return {
        "success": True,
        "mode": "process",
        "metashape_version": str(
            Metashape.app.version
        ),
        "capture_group_count": len(
            manifest.get(
                "capture_groups"
            )
            or []
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
        "calibration_camera_count": len(
            calibration_cameras
        ),
        "calibration_master_count": len(
            calibration_master_keys
        ),
        "master_camera_count": (
            master_camera_count
        ),
        "aligned_master_camera_count": (
            aligned_master_camera_count
        ),
        "alignment_percent": (
            alignment_percent
        ),
        "tie_point_count": (
            tie_point_count
        ),
        "band_mapping": (
            band_mapping
        ),
        "project_path": str(
            project_path
        ),
        "dsm_path": str(
            dsm_path
        ),
        "orthomosaic_native_path": str(
            orthomosaic_native_path
        ),
    }


if __name__ == "__main__":
    raise SystemExit(
        main()
    )