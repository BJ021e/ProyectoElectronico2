# ====================================================
# Flask PC: Ground Control (Con Cálculo de Promedios)
# Archivo: principal.py
# ====================================================
from flask import (
    Flask, 
    render_template, 
    request, 
    redirect, url_for, 
    session, 
    send_file, 
    jsonify,
    Response,
)

import os
import threading
import shutil
import time
import numpy as np
import cv2
import rasterio
import json
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from config import Config
from models import CaptureRole, TelemetrySource

from services.raspberry_service import (
    RaspberryService,
    RaspberryConnectionError
)

from services.flight_service import (
    FlightService,
    FlightPersistenceError,
    InvalidFlightTransitionError,
)

from services.telemetry_service import (
    TelemetryService,
    TelemetryPersistenceError,
    InvalidTelemetryError,
)

from services.route_service import (
    RouteService,
    RoutePersistenceError,
)

from services.mission_service import (
    MissionService,
    MissionPersistenceError,
    MissionNotFoundError,
)

from services.drone_service import (
    DroneService,
    DroneServiceError,
    DroneProviderNotConfiguredError,
)

from services.campaign_service import (
    CampaignPersistenceError,
    CampaignService,
    InvalidCampaignError,
)

from services.capture_service import (
    CapturePersistenceError,
    CaptureService,
    InvalidCaptureError,
)

from services.processing_job_service import (
    InvalidProcessingJobError,
    ProcessingJobPersistenceError,
    ProcessingJobService,
)

from services.geospatial_product_service import (
    GeospatialProductPersistenceError,
    GeospatialProductService,
    InvalidGeospatialProductError,
)

from services.processing_service import (
    InvalidCampaignProcessingError,
    ProcessingExecutionError,
    ProcessingService,
)

from services.photogrammetry_backend_factory import (
    PhotogrammetryBackendConfigurationError,
    PhotogrammetryBackendFactory,
)

from services.rededge_import_service import (
    InvalidRedEdgeCaptureRoleError,
    IncompleteRedEdgeFolderError,
    InvalidRedEdgeCampaignError,
    InvalidRedEdgeFolderError,
    RedEdgeImportError,
    RedEdgeImportExecutionError,
    RedEdgeImportService,
)

from services.rededge_staging_service import (
    InvalidRedEdgeStageError,
    RedEdgeStagingError,
    RedEdgeStagingService,
)

from services.raster_preview_service import (
    InvalidRasterPreviewError,
    RasterPreviewError,
    RasterPreviewService,
)

from services.image_ingestion_service import (
    ImageIngestionService,
)

from services.spectral_index_product_service import (
    InvalidSpectralIndexSourceError,
    SpectralIndexProductAlreadyExistsError,
    SpectralIndexProductError,
    SpectralIndexProductService,
)

from services.spectral_index_visualization_service import (
    InvalidSpectralIndexVisualizationError,
    SpectralIndexVisualizationError,
    SpectralIndexVisualizationService,
)

from services.processing_executor import (
    ProcessingExecutor,
    ProcessingExecutorError,
)

from datetime import datetime, timezone

app = Flask(__name__)
app.secret_key = Config.SECRET_KEY


processing_executor = (
    ProcessingExecutor(
        max_workers=1
    )
)

# ---------------- CONFIGURACIÓN ----------------
BASE_DIR = "static/ground_mission"
UPLOAD_FOLDER = os.path.join(BASE_DIR, "raw_bands")
RESULT_FOLDER = os.path.join(BASE_DIR, "results")
CACHE_FOLDER = "static/ground_cache"

for f in [UPLOAD_FOLDER, RESULT_FOLDER, CACHE_FOLDER]:
    if os.path.exists(f): shutil.rmtree(f)
    os.makedirs(f, exist_ok=True)

RPI_IP = Config.RPI_IP
RPI_API_URL = Config.RPI_API_URL
ACCESS_CODE = Config.ACCESS_CODE
EPSILON = 1e-10
raspberry_service = RaspberryService(RPI_API_URL)

# ---------------- ESTADO GLOBAL ----------------
session_state = {
    "status": "idle",
    "captured_samples": [],
    "logs": [],
    "results": {},
    "telemetria_final": {},
    "last_set_detected": None,
    "altitude_history": [],  
    "active_flight_id": None,
    "active_flight_code": None,
}

def log_msg(msg):
    print(f"📝 {msg}")
    session_state["logs"].append(msg)

def process_preview_image(tif_path, output_name):
    try:
        img = cv2.imread(tif_path, cv2.IMREAD_UNCHANGED)
        if img is None: return None
        img_norm = cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        out_path = os.path.join(CACHE_FOLDER, output_name)
        cv2.imwrite(out_path, img_norm)
        return f"/static/ground_cache/{output_name}"
    except: return None

# ---------------- RUTAS ----------------
@app.route("/")
def index():
    return render_template(
        "pe2_home.html",
        pe2_demo_mode=Config.PE2_DEMO_MODE,
        processing_enabled=Config.PROCESSING_ENABLED,
        photogrammetry_backend=Config.PHOTOGRAMMETRY_BACKEND,
    )

@app.route("/ground_login", methods=["GET", "POST"])
def ground_login():
    error = None
    if request.method == "POST":
        if request.form.get("code") == ACCESS_CODE:
            session["user_ground"] = True
            return redirect(url_for("ground_init"))
        error = "Código incorrecto."
    return render_template("ground_login.html", error=error)

@app.route("/ground_init")
def ground_init():
    session_state.update({
        "status": "capturing", 
        "captured_samples": [], 
        "logs": ["Sistema Iniciado."], 
        "results": {},
        "last_set_detected": None,
        "altitude_history": [], # Reiniciar historial
        "active_flight_id": None,
        "active_flight_code": None,
    })
    
    try:
        flight = FlightService.create_flight(
            name="Sesión de captura multiespectral"
        )

        flight = FlightService.start_flight(
            flight["id"]
        )

        session_state["active_flight_id"] = flight["id"]
        session_state["active_flight_code"] = flight["flight_code"]

        log_msg(
            f"Vuelo iniciado: {flight['flight_code']}"
        )

    except (
        FlightPersistenceError,
        InvalidFlightTransitionError
    ) as e:
        log_msg(
            f"Error al iniciar vuelo persistente: {e}"
        )
        
    for f in [UPLOAD_FOLDER, RESULT_FOLDER, CACHE_FOLDER]:
        if os.path.exists(f): shutil.rmtree(f); os.makedirs(f, exist_ok=True)
    return redirect(url_for("ground_capture_interface"))

@app.route("/ground_capture")
def ground_capture_interface():
    return render_template("ground_capture.html")

# --- TELEMETRÍA CON REGISTRO DE HISTORIAL ---
@app.route("/api/ground_telemetry")
def api_ground_telemetry():
    try:
        data = raspberry_service.get_telemetry(timeout=1)

        # Si estamos capturando, guardamos la altitud para el promedio
        if session_state["status"] == "capturing" and "altitud" in data:
            try:
                alt = float(data["altitud"])
                session_state["altitude_history"].append(alt)
            except (TypeError, ValueError):
                pass
        
        active_flight_id = session_state.get(
            "active_flight_id"
        )

        if (
            session_state["status"] == "capturing"
            and active_flight_id is not None
        ):
            try:
                TelemetryService.add_from_rpi_payload(
                    active_flight_id,
                    data
                )

            except (
                TelemetryPersistenceError,
                InvalidTelemetryError
            ) as e:
                log_msg(
                    f"Error guardando telemetría: {e}"
                )
        return jsonify(data)

    except RaspberryConnectionError:
        return jsonify({"error": True})

@app.route("/api/flights", methods=["GET"])
def api_list_flights():
    try:
        limit = request.args.get(
            "limit",
            default=50,
            type=int
        )

        flights = FlightService.list_flights_summary(
            limit=limit
        )

        return jsonify({
            "flights": flights,
            "count": len(flights)
        })

    except FlightPersistenceError as e:
        return jsonify({
            "error": True,
            "msg": str(e)
        }), 500
        
@app.route("/api/flights/<int:flight_id>", methods=["GET"])
def api_get_flight(flight_id):
    try:
        flight = FlightService.get_flight(
            flight_id
        )

        if flight is None:
            return jsonify({
                "error": True,
                "msg": "Vuelo no encontrado."
            }), 404

        points = TelemetryService.get_flight_points(
            flight_id
        )

        return jsonify({
            "flight": flight,
            "telemetry_count": len(points)
        })

    except (
        FlightPersistenceError,
        TelemetryPersistenceError
    ) as e:
        return jsonify({
            "error": True,
            "msg": str(e)
        }), 500
        
@app.route(
    "/api/flights/<int:flight_id>/trajectory",
    methods=["GET"]
)
def api_get_flight_trajectory(flight_id):
    try:
        flight = FlightService.get_flight(
            flight_id
        )

        if flight is None:
            return jsonify({
                "error": True,
                "msg": "Vuelo no encontrado."
            }), 404

        points = TelemetryService.get_flight_points(
            flight_id
        )

        trajectory = [
            {
                "latitude": point["latitude"],
                "longitude": point["longitude"],
                "altitude": point["altitude"],
                "recorded_at": point["recorded_at"]
            }
            for point in points
            if (
                point["latitude"] is not None
                and point["longitude"] is not None
            )
        ]

        return jsonify({
            "flight_id": flight_id,
            "flight_code": flight["flight_code"],
            "points": trajectory,
            "count": len(trajectory)
        })

    except (
        FlightPersistenceError,
        TelemetryPersistenceError
    ) as e:
        return jsonify({
            "error": True,
            "msg": str(e)
        }), 500
        
@app.route("/api/ground_trigger", methods=["POST"])
def api_ground_trigger():
    try:
        data = raspberry_service.trigger_capture(timeout=45)

        blue_path = data.get("blue_path")
        
        if not blue_path: return jsonify({"status":"error", "msg":"No path"})

        parts = blue_path.split('/')
        current_set = next((p for p in parts if p.endswith("SET")), "UNKNOWN")
        filename = parts[-1] 
        base_name = filename.replace("_1.tif", "")
        
        last_set = session_state.get("last_set_detected")
        if last_set is None:
            log_msg(f"📂 Set Inicial: {current_set}")
            session_state["last_set_detected"] = current_set
        elif current_set != last_set:
            log_msg(f"⚠️ CAMBIO DE SET: {last_set} -> {current_set}")
            session_state["last_set_detected"] = current_set

        sample_id = f"{current_set}_{base_name}"
        exists = any(s['id'] == sample_id for s in session_state["captured_samples"])
        
        if not exists:
            base_path_remote = blue_path.replace("_1.tif", "")
            session_state["captured_samples"].append({
                "id": sample_id,
                "base_path_remote": base_path_remote,
                "display_name": f"{current_set} / {base_name}"
            })
            log_msg(f"📸 Captura Guardada: {base_name}")
            
        local_tmp = os.path.join(CACHE_FOLDER, "temp.tif")

        raspberry_service.download_file(
            remote_path=blue_path,
            local_path=local_tmp,
            timeout=15
        )
        
        img_url = f"prev_{len(session_state['captured_samples'])}.png"
        web_path = process_preview_image(local_tmp, img_url)
        
        return jsonify({"status":"success", "count":len(session_state["captured_samples"]), "img_url": web_path, "last_parcel": base_name})
        
    except RaspberryConnectionError as e:
        log_msg(f"Error de comunicación con Raspberry: {e}")
        return jsonify({
            "status": "error",
            "msg": "Fallo RPi"
        })
        
    except Exception as e: 
        log_msg(f"Error trigger: {e}")
        return jsonify({"status":"error", "msg":str(e)})

@app.route("/ground_start_process", methods=["POST"])
def ground_start_process():
    active_flight_id = session_state.get(
    "active_flight_id"
    )

    if active_flight_id is not None:
        try:
            flight = FlightService.finish_flight(
                active_flight_id
            )

            log_msg(
                f"Vuelo finalizado: {flight['flight_code']}"
            )

        except (
            FlightPersistenceError,
            InvalidFlightTransitionError
        ) as e:
            log_msg(
                f"Error al finalizar vuelo: {e}"
            )
            
    session_state["status"] = "processing"
    threading.Thread(target=processing_worker).start()
    return jsonify({"status": "success", "redirect": url_for("ground_processing_view")})

@app.route("/ground_processing")
def ground_processing_view(): return render_template("ground_processing.html")

@app.route("/api/ground_status")
def api_ground_status():
    return jsonify({"status": session_state["status"], "log": session_state["logs"][-1] if session_state["logs"] else "..."})

@app.route("/ground_results")
def ground_results_view():
    return render_template("ground_results.html", 
                           resultados=session_state["results"], 
                           telemetria=session_state["telemetria_final"],
                           num_parcelas=len(session_state["results"]))

@app.route("/ground_download_pdf")
def ground_download_pdf():
    return send_file(os.path.join(RESULT_FOLDER, "Reporte_Parcelas.pdf"), as_attachment=True)

@app.route("/logout")
def logout(): session.clear(); return redirect(url_for('ground_login'))

def _execute_processing_job_background(
    *,
    job_id: int,
    backend,
) -> None:

    try:

        ProcessingService.execute_job(
            job_id=job_id,
            backend=backend,
        )

    except Exception:

        app.logger.exception(
            "Falló el trabajo geoespacial "
            "en segundo plano. job_id=%s",
            job_id,
        )

# ---------------- WORKER ----------------

def processing_worker():
    global session_state
    try:
        log_msg("📥 Iniciando procesamiento...")
        
        # 1. Obtener Telemetría Final (Snapshot)
        try:
            final_telem = raspberry_service.get_telemetry(timeout=2)
        except RaspberryConnectionError:
            final_telem = {
                "bateria": "N/A",
                "modo": "N/A",
                "altitud": 0,
                "latitud": 0,
                "longitud": 0
            }

        # 2. Calcular Altitud Promedio
        historia = session_state["altitude_history"]
        if historia:
            avg_alt = sum(historia) / len(historia)
        else:
            avg_alt = float(final_telem.get("altitud", 0))
            
        # Guardar en el objeto final para usar en HTML/PDF
        final_telem["altitud_promedio"] = round(avg_alt, 2)
        session_state["telemetria_final"] = final_telem

        log_msg(f"📊 Altitud Promedio Calculada: {final_telem['altitud_promedio']} m")

        samples = session_state["captured_samples"]
        results = {}
        band_indices = { "Blue": 1, "Green": 2, "Red": 3, "NIR": 4, "RedEdge": 5 }
        
        for idx, sample in enumerate(samples):
            s_id = sample['id']
            base_remote = sample['base_path_remote']
            log_msg(f"Analizando [{idx+1}/{len(samples)}]: {sample['display_name']}...")
            
            local_dir = os.path.join(UPLOAD_FOLDER, s_id)
            os.makedirs(local_dir, exist_ok=True)
            bands_arrays = {}
            valid_sample = True
            
        for band_name, band_idx in band_indices.items():
            remote_file = f"{base_remote}_{band_idx}.tif"
            local_file = os.path.join(local_dir, f"{band_name}.tif")

            try:
                raspberry_service.download_file(
                    remote_path=remote_file,
                    local_path=local_file,
                    timeout=15
                )

                with rasterio.open(local_file) as src:
                    bands_arrays[band_name] = (
                        src.read(1).astype(np.float32)
                    )

            except Exception as e:
                log_msg(f"⚠️ Fallo banda {band_name}: {e}")
                valid_sample = False
                break
            
            if not valid_sample: continue

            B, G, R, RE, NIR = bands_arrays["Blue"], bands_arrays["Green"], bands_arrays["Red"], bands_arrays["RedEdge"], bands_arrays["NIR"]
            indices = {
                "NDVI": float(np.nanmean((NIR-R)/(NIR+R+EPSILON))),
                "GNDVI": float(np.nanmean((NIR-G)/(NIR+G+EPSILON))),
                "NDRE": float(np.nanmean((NIR-RE)/(NIR+RE+EPSILON))),
                "SAVI": float(np.nanmean((1.5*(NIR-R))/(NIR+R+0.5+EPSILON))),
                "EVI": 0.0
            }
            val = indices["GNDVI"]
            if val > 0.35: diag, rec = "SANO", "Vegetación saludable."
            elif val > 0.10: diag, rec = "ESTRÉS", "Posible deficiencia hídrica."
            else: diag, rec = "INFECTADO", "Alerta: Posible clorosis o plaga."
            
            img_name = f"res_{s_id}.png"
            norm = cv2.normalize(B, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
            cv2.imwrite(os.path.join(RESULT_FOLDER, img_name), norm)
            
            results[s_id] = { "indices": indices, "diagnostico": diag, "recomendacion": rec, "imagen_muestra": img_name }
        
        if not results:
            log_msg("❌ Error: Sin resultados.")
            session_state["status"] = "error"
        else:
            generar_pdf_parcelas(results, session_state["telemetria_final"])
            session_state["results"] = results
            session_state["status"] = "completed"
            log_msg("✅ Terminado.")

    except Exception as e:
        session_state["status"] = "error"
        log_msg(f"Error Fatal: {e}")

def generar_pdf_parcelas(resultados_parcelas, telemetria_resumen):
    pdf_path = os.path.join(RESULT_FOLDER, "Reporte_Parcelas.pdf")
    c = canvas.Canvas(pdf_path, pagesize=A4)
    width, height = A4
    margin = 50
    
    c.setFont("Helvetica-Bold", 20)
    c.drawString(margin, height - 60, "Reporte de Diagnóstico Multiespectral")
    c.setFont("Helvetica", 12)
    c.drawString(margin, height - 85, f"Muestras: {len(resultados_parcelas)}")

    # SECCIÓN TELEMETRÍA (ACTUALIZADA CON PROMEDIO)
    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(colors.darkblue)
    c.drawString(margin, height - 120, "1. Resumen de Vuelo / Telemetría")
    c.setFont("Helvetica", 11)
    c.setFillColor(colors.black)
    
    alt_avg = telemetria_resumen.get('altitud_promedio', 'N/A')
    bat = telemetria_resumen.get('bateria', 'N/A')
    mode = telemetria_resumen.get('modo', 'N/A')
    
    c.drawString(margin + 10, height - 145, f"• Batería Final: {bat}")
    c.drawString(margin + 200, height - 145, f"• Modo Final: {mode}")
    c.drawString(margin + 400, height - 145, f"• Altitud Promedio: {alt_avg} m")
    
    y = height - 190
    c.setFont("Helvetica-Bold", 16)
    c.setFillColor(colors.darkgreen)
    c.drawString(margin, y, "2. Detalle por Parcela")
    y -= 40 
    
    for idx, (nombre, datos) in enumerate(resultados_parcelas.items()):
        if y < 150: c.showPage(); y = height - 50
        c.setStrokeColor(colors.lightgrey); c.line(margin, y + 10, width - margin, y + 10)
        
        display_name = nombre.replace("_", " / ")
        c.setFont("Helvetica-Bold", 12); c.setFillColor(colors.black)
        c.drawString(margin, y, f"Muestra: {display_name}")
        
        diag = datos['diagnostico']
        color = colors.green if "SANO" in diag else (colors.orange if "ESTRÉS" in diag else colors.red)
        c.setFillColor(color)
        c.drawString(margin, y - 20, f"ESTADO: {diag}")
        
        c.setFillColor(colors.black); c.setFont("Helvetica", 10)
        c.drawString(margin, y - 40, f"GNDVI: {datos['indices']['GNDVI']:.3f} | NDVI: {datos['indices']['NDVI']:.3f}")
        
        img_p = os.path.join(RESULT_FOLDER, datos['imagen_muestra'])
        if os.path.exists(img_p):
            try: c.drawImage(ImageReader(img_p), margin + 350, y - 60, width=80, height=80)
            except: pass
        y -= 80

    c.save()
    return pdf_path

@app.route("/flight_history")
def flight_history():
    return render_template(
        "flight_history.html"
    )

@app.route("/campaigns")
def campaigns_view():
    return render_template(
        "campaigns.html",
        pe2_demo_mode=Config.PE2_DEMO_MODE,
    )


@app.route("/campaigns/<int:campaign_id>")
def campaign_detail_view(
    campaign_id
):
    return render_template(
        "campaign_detail.html",
        campaign_id=campaign_id,
        processing_enabled=(
            Config.PROCESSING_ENABLED
        ),
        pe2_demo_mode=Config.PE2_DEMO_MODE,
    )

@app.route("/flight_history/<int:flight_id>")
def flight_detail(flight_id):
    return render_template(
        "flight_detail.html",
        flight_id=flight_id
    )

@app.route("/api/routes", methods=["GET"])
def api_list_routes():
    try:
        limit = request.args.get(
            "limit",
            default=50,
            type=int
        )

        routes = RouteService.list_routes(
            limit=limit
        )

        return jsonify({
            "routes": routes,
            "count": len(routes)
        })

    except RoutePersistenceError as e:
        return jsonify({
            "error": True,
            "msg": str(e)
        }), 500
        
@app.route(
    "/api/routes/<int:route_id>",
    methods=["GET"]
)
def api_get_route(route_id):
    try:
        route = RouteService.get_route(
            route_id
        )

        if route is None:
            return jsonify({
                "error": True,
                "msg": "Ruta no encontrada."
            }), 404

        return jsonify({
            "route": route
        })

    except RoutePersistenceError as e:
        return jsonify({
            "error": True,
            "msg": str(e)
        }), 500
 
@app.route("/mission_routes")
def mission_routes():
    return render_template(
        "mission_routes.html"
    )
    
@app.route("/mission_routes/<int:route_id>")
def mission_route_detail(route_id):
    return render_template(
        "mission_route_detail.html",
        route_id=route_id
    )

@app.route(
    "/api/flights/<int:flight_id>/mission",
    methods=["GET"]
)
def api_get_flight_mission(flight_id):

    try:

        mission = (
            MissionService.get_mission(
                flight_id
            )
        )

        return jsonify(
            mission
        )


    except MissionNotFoundError as e:

        return jsonify({
            "error": True,
            "msg": str(e)
        }), 404


    except MissionPersistenceError as e:

        return jsonify({
            "error": True,
            "msg": str(e)
        }), 500

@app.route(
    "/api/drone/state",
    methods=["GET"]
)
def api_drone_state():

    try:

        state = (
            DroneService
            .get_state_dict()
        )

        return jsonify({
            "configured": True,
            "state": state
        })


    except DroneProviderNotConfiguredError:

        return jsonify({
            "configured": False,
            "state": None
        })

@app.route(
    "/api/drone/simulator/setup",
    methods=["POST"]
)
def api_drone_simulator_setup():

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )


    route_id = data.get(
        "route_id"
    )


    if route_id is None:

        return jsonify({
            "error": True,
            "msg": "route_id es obligatorio."
        }), 400


    try:

        route_id = int(
            route_id
        )

    except (
        TypeError,
        ValueError
    ):

        return jsonify({
            "error": True,
            "msg": "route_id debe ser un entero."
        }), 400


    step_fraction = data.get(
        "step_fraction",
        0.20
    )


    initial_battery = data.get(
        "initial_battery",
        100.0
    )


    try:

        step_fraction = float(
            step_fraction
        )

        initial_battery = float(
            initial_battery
        )

    except (
        TypeError,
        ValueError
    ):

        return jsonify({
            "error": True,
            "msg": (
                "step_fraction e initial_battery "
                "deben ser valores numéricos."
            )
        }), 400


    try:

        state = (
            DroneService
            .configure_simulator(
                route_id,
                step_fraction=step_fraction,
                initial_battery=initial_battery
            )
        )


        return jsonify({
            "status": "configured",

            "provider":
                DroneService
                .get_provider_name(),

            "route_id":
                route_id,

            "state":
                state.to_dict()
        })


    except (
        DroneServiceError,
        ValueError
    ) as e:

        return jsonify({
            "error": True,
            "msg": str(e)
        }), 400

@app.route(
    "/api/drone/simulator/connect",
    methods=["POST"]
)
def api_drone_simulator_connect():

    try:

        state = (
            DroneService
            .simulator_connect()
        )

        return jsonify({
            "status": "connected",
            "state": state.to_dict()
        })


    except DroneServiceError as e:

        return jsonify({
            "error": True,
            "msg": str(e)
        }), 400

@app.route(
    "/api/drone/simulator/start",
    methods=["POST"]
)
def api_drone_simulator_start():

    try:

        state = (
            DroneService
            .simulator_start()
        )

        return jsonify({
            "status": "running",
            "state": state.to_dict()
        })


    except DroneServiceError as e:

        return jsonify({
            "error": True,
            "msg": str(e)
        }), 400
        
@app.route(
    "/api/drone/simulator/advance",
    methods=["POST"]
)
def api_drone_simulator_advance():

    try:

        state = (
            DroneService
            .simulator_advance()
        )

        return jsonify({
            "status": (
                "running"
                if DroneService
                .simulator_is_running()
                else "completed"
            ),

            "state":
                state.to_dict()
        })


    except DroneServiceError as e:

        return jsonify({
            "error": True,
            "msg": str(e)
        }), 400

@app.route(
    "/api/drone/simulator/reset",
    methods=["POST"]
)
def api_drone_simulator_reset():

    try:

        state = (
            DroneService
            .simulator_reset()
        )

        return jsonify({
            "status": "reset",
            "state": state.to_dict()
        })


    except DroneServiceError as e:

        return jsonify({
            "error": True,
            "msg": str(e)
        }), 400
        
@app.route(
    "/api/drone/simulator/disconnect",
    methods=["POST"]
)
def api_drone_simulator_disconnect():

    try:

        state = (
            DroneService
            .simulator_disconnect()
        )

        return jsonify({
            "status": "disconnected",
            "state": state.to_dict()
        })


    except DroneServiceError as e:

        return jsonify({
            "error": True,
            "msg": str(e)
        }), 400

@app.route("/dji-cloud")
def dji_cloud_probe():
    """
    Página mínima para verificar que DJI Pilot 2 puede abrir
    la plataforma PE2 desde Servicios en la nube / Plataformas abiertas.
    """
    client_ip = request.headers.get(
        "X-Forwarded-For",
        request.remote_addr,
    )

    user_agent = request.headers.get(
        "User-Agent",
        "",
    )

    app.logger.info(
        "DJI Cloud probe abierto desde ip=%s user_agent=%s",
        client_ip,
        user_agent,
    )

    return render_template(
        "dji_cloud_probe.html",
        client_ip=client_ip,
        user_agent=user_agent,
        server_time=datetime.now(timezone.utc).isoformat(),
    )


@app.route("/api/dji-cloud/ping", methods=["GET", "POST"])
def api_dji_cloud_ping():
    """
    Endpoint de prueba para confirmar comunicación WebView DJI Pilot 2 → Flask.
    No implementa aún licencia DJI ni telemetría real.
    """
    payload = request.get_json(silent=True) or {}

    return jsonify({
        "ok": True,
        "source": "pe2-dji-cloud-probe",
        "remote_addr": request.remote_addr,
        "user_agent": request.headers.get("User-Agent", ""),
        "received": payload,
        "server_time": datetime.now(timezone.utc).isoformat(),
    })

@app.route("/drone_operation")
def drone_operation():
    return render_template(
        "drone_operation.html"
    )

@app.route(
    "/api/drone/simulator/auto/status",
    methods=["GET"]
)
def api_drone_simulator_auto_status():

    try:

        return jsonify(
            DroneService
            .simulator_auto_status()
        )


    except DroneServiceError as e:

        return jsonify({
            "error": True,
            "msg": str(e)
        }), 400
        
@app.route(
    "/api/drone/simulator/auto/start",
    methods=["POST"]
)
def api_drone_simulator_auto_start():

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )


    interval_seconds = data.get(
        "interval_seconds",
        1.0
    )


    try:

        result = (
            DroneService
            .simulator_start_auto(
                interval_seconds
            )
        )


        return jsonify({
            "status": "auto_started",
            "runtime": result
        })


    except DroneServiceError as e:

        return jsonify({
            "error": True,
            "msg": str(e)
        }), 400

@app.route(
    "/api/drone/simulator/auto/stop",
    methods=["POST"]
)
def api_drone_simulator_auto_stop():

    try:

        result = (
            DroneService
            .simulator_stop_auto()
        )


        return jsonify({
            "status": "auto_stopped",
            "runtime": result
        })


    except DroneServiceError as e:

        return jsonify({
            "error": True,
            "msg": str(e)
        }), 400

@app.route(
    "/api/drone/operation/prepare",
    methods=["POST"]
)
def api_drone_operation_prepare():

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )


    route_id = data.get(
        "route_id"
    )


    if route_id is None:

        return jsonify({
            "error": True,
            "msg": "route_id es obligatorio."
        }), 400


    try:

        route_id = int(
            route_id
        )

    except (
        TypeError,
        ValueError
    ):

        return jsonify({
            "error": True,
            "msg": "route_id debe ser un entero."
        }), 400


    name = (
        str(
            data.get(
                "name",
                "Vuelo simulado"
            )
        )
        .strip()
    )


    if not name:
        name = "Vuelo simulado"


    try:

        result = (
            DroneService
            .prepare_simulated_flight(
                route_id,
                name=name,
            )
        )


        return jsonify({
            "status": "prepared",
            "operation": result
        })


    except DroneServiceError as e:

        return jsonify({
            "error": True,
            "msg": str(e)
        }), 400
    
@app.route(
    "/api/drone/operation/context",
    methods=["GET"]
)
def api_drone_operation_context():

    try:

        return jsonify(
            DroneService
            .get_operation_context()
        )


    except DroneServiceError as e:

        return jsonify({
            "error": True,
            "msg": str(e)
        }), 400

@app.route(
    "/api/drone/operation/integration-status",
    methods=["GET"]
)
def api_drone_operation_integration_status():
    """
    Devuelve el estado técnico normalizado
    de la integración activa con el dron.
    """

    try:

        status = (
            DroneService
            .get_integration_status()
        )

        return jsonify(
            status.to_dict()
        )


    except DroneServiceError as exc:

        return jsonify({
            "status": "error",
            "message": str(exc),
        }), 400
        

@app.route(
    "/api/drone/operation/cancel",
    methods=["POST"]
)
def api_drone_operation_cancel():

    try:

        result = (
            DroneService
            .cancel_active_operation()
        )


        return jsonify(
            result
        )


    except DroneServiceError as e:

        return jsonify({
            "error": True,
            "msg": str(e)
        }), 400

@app.route(
    "/api/drone/operation/connect",
    methods=["POST"]
)
def api_drone_operation_connect():

    try:

        return jsonify(
            DroneService.connect_operation()
        )

    except DroneServiceError as exc:

        return jsonify({
            "error": True,
            "msg": str(exc),
        }), 400

@app.route(
    "/api/drone/operation/start",
    methods=["POST"]
)
def api_drone_operation_start():

    try:

        data = request.get_json(
            silent=True
        ) or {}


        interval_seconds = (
            data.get(
                "interval_seconds",
                0.5
            )
        )


        return jsonify(
            DroneService.start_operation(
                interval_seconds
            )
        )

    except DroneServiceError as exc:

        return jsonify({
            "error": True,
            "msg": str(exc),
        }), 400
        
@app.route(
    "/api/drone/operation/pause",
    methods=["POST"]
)
def api_drone_operation_pause():

    try:

        return jsonify(
            DroneService.pause_operation()
        )

    except DroneServiceError as exc:

        return jsonify({
            "error": True,
            "msg": str(exc),
        }), 400

@app.route(
    "/api/drone/operation/resume",
    methods=["POST"]
)
def api_drone_operation_resume():

    try:

        data = request.get_json(
            silent=True
        ) or {}


        return jsonify(
            DroneService.resume_operation(
                data.get(
                    "interval_seconds",
                    0.5
                )
            )
        )

    except DroneServiceError as exc:

        return jsonify({
            "error": True,
            "msg": str(exc),
        }), 400

@app.route(
    "/api/drone/operation/disconnect",
    methods=["POST"]
)
def api_drone_operation_disconnect():

    try:

        return jsonify(
            DroneService.disconnect_operation()
        )

    except DroneServiceError as exc:

        return jsonify({
            "error": True,
            "msg": str(exc),
        }), 400
        
@app.route(
    "/api/campaigns",
    methods=["GET"],
)
def api_list_campaigns():
    try:
        limit = request.args.get(
            "limit",
            default=50,
            type=int,
        )

        campaigns = (
            CampaignService.list_campaigns(
                limit=limit,
            )
        )

        return jsonify({
            "campaigns": campaigns,
            "count": len(campaigns),
        })

    except CampaignPersistenceError as exc:
        return jsonify({
            "error": True,
            "msg": str(exc),
        }), 500


@app.route(
    "/api/campaigns",
    methods=["POST"],
)
def api_create_campaign():
    data = request.get_json(
        silent=True
    ) or {}

    try:
        campaign = (
            CampaignService.create_campaign(
                name=data.get("name"),
                sensor_type=data.get(
                    "sensor_type"
                ),
                sensor_model=data.get(
                    "sensor_model"
                ),
                flight_id=data.get(
                    "flight_id"
                ),
                description=data.get(
                    "description"
                ),
                notes=data.get(
                    "notes"
                ),
            )
        )

        return jsonify(
            campaign
        ), 201

    except InvalidCampaignError as exc:
        return jsonify({
            "error": True,
            "msg": str(exc),
        }), 400

    except CampaignPersistenceError as exc:
        return jsonify({
            "error": True,
            "msg": str(exc),
        }), 500


@app.route(
    "/api/campaigns/<int:campaign_id>",
    methods=["GET"],
)
def api_get_campaign(campaign_id):
    try:
        campaign = (
            CampaignService.get_campaign(
                campaign_id
            )
        )

        if campaign is None:
            return jsonify({
                "error": True,
                "msg": (
                    "La campaña con ID "
                    f"{campaign_id} no existe."
                ),
            }), 404

        return jsonify(
            campaign
        )

    except CampaignPersistenceError as exc:
        return jsonify({
            "error": True,
            "msg": str(exc),
        }), 500
        
@app.route(
    "/api/campaigns/<int:campaign_id>/captures",
    methods=["GET"],
)
def api_list_campaign_captures(
    campaign_id
):
    try:
        campaign = (
            CampaignService.get_campaign(
                campaign_id
            )
        )

        if campaign is None:
            return jsonify({
                "error": True,
                "msg": (
                    "La campaña con ID "
                    f"{campaign_id} no existe."
                ),
            }), 404

        captures = (
            CaptureService.list_captures(
                campaign_id
            )
        )

        return jsonify({
            "campaign_id": campaign_id,
            "captures": captures,
            "count": len(captures),
            "role_counts": {
                role.value: sum(capture["role"] == role.value for capture in captures)
                for role in CaptureRole
            },
        })

    except (
        InvalidCaptureError,
        CapturePersistenceError,
    ) as exc:
        return jsonify({
            "error": True,
            "msg": str(exc),
        }), 500
        
@app.route(
    "/api/campaigns/<int:campaign_id>/processing-jobs",
    methods=["GET"],
)
def api_list_campaign_processing_jobs(
    campaign_id
):
    try:
        campaign = (
            CampaignService.get_campaign(
                campaign_id
            )
        )

        if campaign is None:
            return jsonify({
                "error": True,
                "msg": (
                    "La campaña con ID "
                    f"{campaign_id} no existe."
                ),
            }), 404

        jobs = (
            ProcessingJobService.list_jobs(
                campaign_id
            )
        )

        return jsonify({
            "campaign_id": campaign_id,
            "jobs": jobs,
            "count": len(jobs),
        })

    except (
        InvalidProcessingJobError,
        ProcessingJobPersistenceError,
    ) as exc:
        return jsonify({
            "error": True,
            "msg": str(exc),
        }), 500
        
@app.route(
    "/api/campaigns/<int:campaign_id>/products",
    methods=["GET"],
)
def api_list_campaign_products(
    campaign_id
):
    try:
        campaign = (
            CampaignService.get_campaign(
                campaign_id
            )
        )

        if campaign is None:
            return jsonify({
                "error": True,
                "msg": (
                    "La campaña con ID "
                    f"{campaign_id} no existe."
                ),
            }), 404

        product_type = request.args.get(
            "type"
        )

        products = (
            GeospatialProductService
            .list_products(
                campaign_id,
                product_type=product_type,
            )
        )

        return jsonify({
            "campaign_id": campaign_id,
            "products": products,
            "count": len(products),
        })

    except InvalidGeospatialProductError as exc:
        return jsonify({
            "error": True,
            "msg": str(exc),
        }), 400

    except GeospatialProductPersistenceError as exc:
        return jsonify({
            "error": True,
            "msg": str(exc),
        }), 500


@app.route(
    "/api/geospatial-products/<int:product_id>",
    methods=["GET"],
)
def api_get_geospatial_product(
    product_id
):
    try:
        product = (
            GeospatialProductService
            .get_product(
                product_id
            )
        )

        if product is None:
            return jsonify({
                "error": True,
                "msg": (
                    "El producto geoespacial "
                    f"con ID {product_id} "
                    "no existe."
                ),
            }), 404

        return jsonify(
            product
        )

    except GeospatialProductPersistenceError as exc:
        return jsonify({
            "error": True,
            "msg": str(exc),
        }), 500

@app.route(
    (
        "/api/geospatial-products/"
        "<int:product_id>/preview.png"
    ),
    methods=["GET"],
)
def api_geospatial_product_preview(
    product_id
):

    try:
        product = (
            GeospatialProductService
            .get_product(
                product_id
            )
        )

        if product is None:
            return jsonify({
                "error": True,
                "msg": (
                    "El producto geoespacial "
                    f"con ID {product_id} "
                    "no existe."
                ),
            }), 404

        source_path = (
            ImageIngestionService
            .resolve_managed_path(
                product["storage_path"]
            )
        )

        product_type = (
            product.get(
                "product_type"
            )
            or product.get(
                "type"
            )
        )
        
        normalized_product_type = (
            str(
                product_type or ""
            )
            .strip()
            .upper()
        )

        display_mode = (
            request.args.get(
                "mode",
                "natural",
            )
            .strip()
            .upper()
        )
        
        if (
            normalized_product_type
            in (
                SpectralIndexVisualizationService
                .SUPPORTED_INDEXES
            )
        ):

            png_bytes = (
                SpectralIndexVisualizationService
                .render_png(
                    source_path=source_path,
                    index_name=(
                        normalized_product_type
                    ),
                )
            )

        else:

            png_bytes = (
                RasterPreviewService
                .render_png(
                    source_path=source_path,
                    product_type=product_type,
                    display_mode=display_mode,
                )
            )

        response = Response(
            png_bytes,
            mimetype="image/png",
        )

        response.headers[
            "Cache-Control"
        ] = "no-store"

        return response

    except InvalidRasterPreviewError as exc:

        return jsonify({
            "error": True,
            "msg": str(exc),
        }), 422

    except RasterPreviewError as exc:

        return jsonify({
            "error": True,
            "msg": str(exc),
        }), 500
    
    except (
        InvalidSpectralIndexVisualizationError
    ) as exc:

        return jsonify({
            "error": True,
            "msg": str(exc),
        }), 422

    except SpectralIndexVisualizationError as exc:

        return jsonify({
            "error": True,
            "msg": str(exc),
        }), 500
        

@app.route(
    "/api/campaigns/<int:campaign_id>/process",
    methods=["POST"],
)
def api_process_campaign(
    campaign_id
):

    try:

        if not Config.PROCESSING_ENABLED:

            return jsonify({
                "error": True,
                "msg": (
                    "El procesamiento está deshabilitado "
                    "por configuración operativa."
                ),
            }), 409

        campaign = (
            CampaignService.get_campaign(
                campaign_id
            )
        )

        if campaign is None:

            return jsonify({
                "error": True,
                "msg": (
                    "La campaña con ID "
                    f"{campaign_id} no existe."
                ),
            }), 404

        backend = (
            PhotogrammetryBackendFactory
            .create()
        )

        job = (
            ProcessingService.prepare_campaign(
                campaign_id=campaign_id,
                backend=backend,
            )
        )

        try:

            processing_executor.submit(
                job_id=job["id"],
                task=lambda: (
                    _execute_processing_job_background(
                        job_id=job["id"],
                        backend=backend,
                    )
                ),
            )

        except (
            ProcessingExecutorError,
            RuntimeError,
        ) as exc:

            failure_message = (
                "No fue posible encolar "
                "el trabajo de procesamiento: "
                f"{exc}"
            )

            try:

                ProcessingJobService.fail_job(
                    job["id"],
                    error_message=(
                        failure_message
                    ),
                )

            except Exception:

                app.logger.exception(
                    "No fue posible marcar "
                    "FAILED el job que no pudo "
                    "encolarse. job_id=%s",
                    job["id"],
                )

            return jsonify({
                "error": True,
                "msg": failure_message,
                "job": job,
            }), 500

        return jsonify({
            "accepted": True,
            "job": job,
            "msg": (
                "El procesamiento fue "
                "aceptado y continuará "
                "en segundo plano."
            ),
        }), 202

    except (
        InvalidCampaignProcessingError,
        InvalidCampaignError,
    ) as exc:

        return jsonify({
            "error": True,
            "msg": str(exc),
        }), 400

    except (
        ProcessingExecutionError,
        PhotogrammetryBackendConfigurationError,
    ) as exc:

        return jsonify({
            "error": True,
            "msg": str(exc),
        }), 500

    except (
        CampaignPersistenceError,
        ProcessingJobPersistenceError,
        GeospatialProductPersistenceError,
    ) as exc:

        return jsonify({
            "error": True,
            "msg": str(exc),
        }), 500


@app.route(
    (
        "/api/geospatial-products/"
        "<int:product_id>/spectral-indices/"
        "<string:index_name>"
    ),
    methods=["POST"],
)
def api_generate_spectral_index(
    product_id,
    index_name,
):

    try:
        product = (
            SpectralIndexProductService
            .generate_index(
                source_product_id=product_id,
                index_name=index_name,
            )
        )

        return jsonify({
            "ok": True,
            "product": product,
            "msg": (
                f"{index_name.upper()} "
                "generado correctamente."
            ),
        }), 201

    except (
        SpectralIndexProductAlreadyExistsError
    ) as exc:

        return jsonify({
            "ok": False,
            "msg": str(exc),
        }), 409

    except InvalidSpectralIndexSourceError as exc:

        return jsonify({
            "ok": False,
            "msg": str(exc),
        }), 400

    except SpectralIndexProductError as exc:

        return jsonify({
            "ok": False,
            "msg": str(exc),
        }), 422

@app.route(
    (
        "/api/geospatial-products/"
        "<int:product_id>/statistics"
    ),
    methods=["GET"],
)
def api_geospatial_product_statistics(
    product_id
):

    try:

        product = (
            GeospatialProductService
            .get_product(
                product_id
            )
        )

        if product is None:

            return jsonify({
                "error": True,
                "msg": (
                    "El producto "
                    "geoespacial no existe."
                ),
            }), 404

        product_type = (
            str(
                product.get(
                    "product_type"
                )
                or product.get(
                    "type"
                )
                or ""
            )
            .strip()
            .upper()
        )

        if (
            product_type
            not in (
                SpectralIndexVisualizationService
                .SUPPORTED_INDEXES
            )
        ):

            return jsonify({
                "error": True,
                "msg": (
                    "Las estadísticas "
                    "espectrales están "
                    "disponibles únicamente "
                    "para NDVI, NDRE y GNDVI."
                ),
            }), 400

        source_path = (
            ImageIngestionService
            .resolve_managed_path(
                product[
                    "storage_path"
                ]
            )
        )

        statistics = (
            SpectralIndexVisualizationService
            .calculate_statistics(
                source_path=source_path,
                index_name=product_type,
            )
        )

        return jsonify({
            "ok": True,
            "product_id": product_id,
            "statistics": statistics,
            "legend": (
                SpectralIndexVisualizationService
                .get_legend()
            ),
        })

    except (
        InvalidSpectralIndexVisualizationError
    ) as exc:

        return jsonify({
            "error": True,
            "msg": str(exc),
        }), 422

    except SpectralIndexVisualizationError as exc:

        return jsonify({
            "error": True,
            "msg": str(exc),
        }), 500


@app.route(
    "/api/campaigns/<int:campaign_id>/rededge/inspect",
    methods=["POST"],
)
def api_inspect_rededge_upload(
    campaign_id
):

    token = None

    try:
        campaign = (
            CampaignService.get_campaign(
                campaign_id
            )
        )

        if campaign is None:
            return jsonify({
                "error": True,
                "msg": (
                    "La campaña con ID "
                    f"{campaign_id} no existe."
                ),
            }), 404

        if (
            campaign["sensor_type"]
            != "MULTISPECTRAL"
        ):
            return jsonify({
                "error": True,
                "msg": (
                    "La importación RedEdge "
                    "requiere una campaña "
                    "MULTISPECTRAL."
                ),
            }), 400

        uploads = (
            request.files.getlist(
                "files"
            )
        )

        if not uploads:
            return jsonify({
                "error": True,
                "msg": (
                    "No se recibieron archivos."
                ),
            }), 400

        relative_paths_raw = (
            request.form.get(
                "relative_paths"
            )
        )

        if not relative_paths_raw:
            return jsonify({
                "error": True,
                "msg": (
                    "No se recibieron "
                    "las rutas relativas."
                ),
            }), 400

        try:
            relative_paths = (
                json.loads(
                    relative_paths_raw
                )
            )

        except json.JSONDecodeError:
            return jsonify({
                "error": True,
                "msg": (
                    "relative_paths "
                    "no contiene JSON válido."
                ),
            }), 400

        if not isinstance(
            relative_paths,
            list,
        ):
            return jsonify({
                "error": True,
                "msg": (
                    "relative_paths debe "
                    "ser una lista."
                ),
            }), 400

        if (
            len(relative_paths)
            != len(uploads)
        ):
            return jsonify({
                "error": True,
                "msg": (
                    "La cantidad de archivos "
                    "no coincide con las "
                    "rutas relativas."
                ),
            }), 400

        token = (
            RedEdgeStagingService
            .create_stage(
                campaign_id=campaign_id
            )
        )

        for (
            upload,
            relative_path,
        ) in zip(
            uploads,
            relative_paths,
        ):

            (
                RedEdgeStagingService
                .stage_file(
                    token=token,
                    campaign_id=campaign_id,
                    relative_path=(
                        relative_path
                    ),
                    source_stream=(
                        upload.stream
                    ),
                )
            )

        inspection = (
            RedEdgeStagingService
            .inspect_stage(
                token=token,
                campaign_id=campaign_id,
            )
        )

        return jsonify({
            "staging_token": token,
            "uploaded_file_count": (
                len(uploads)
            ),
            "inspection": inspection,
        }), 201

    except (
        InvalidRedEdgeStageError,
        InvalidRedEdgeFolderError,
        RedEdgeImportError,
    ) as exc:

        if token is not None:
            try:
                (
                    RedEdgeStagingService
                    .delete_stage(
                        token=token,
                        campaign_id=campaign_id,
                    )
                )
            except Exception:
                pass

        return jsonify({
            "error": True,
            "msg": str(exc),
        }), 400

    except RedEdgeStagingError as exc:

        if token is not None:
            try:
                (
                    RedEdgeStagingService
                    .delete_stage(
                        token=token,
                        campaign_id=campaign_id,
                    )
                )
            except Exception:
                pass

        return jsonify({
            "error": True,
            "msg": str(exc),
        }), 500

@app.route(
    "/api/campaigns/<int:campaign_id>/rededge/import",
    methods=["POST"],
)
def api_import_rededge_upload(
    campaign_id
):

    data = request.get_json(
        silent=True
    ) or {}

    token = data.get(
        "staging_token"
    )

    skip_incomplete = data.get(
        "skip_incomplete",
        False,
    )

    if not isinstance(
        skip_incomplete,
        bool,
    ):
        return jsonify({
            "error": True,
            "msg": (
                "skip_incomplete "
                "debe ser booleano."
            ),
        }), 400

    try:
        stage_directory = (
            RedEdgeStagingService
            .get_stage_directory(
                token=token,
                campaign_id=campaign_id,
            )
        )

        result = (
            RedEdgeImportService
            .import_folder(
                campaign_id=campaign_id,
                source_dir=stage_directory,
                capture_role=data.get("capture_role", "UNKNOWN"),
                skip_incomplete=(
                    skip_incomplete
                ),
            )
        )

        (
            RedEdgeStagingService
            .delete_stage(
                token=token,
                campaign_id=campaign_id,
            )
        )

        return jsonify(
            result
        ), 201

    except (
        InvalidRedEdgeStageError,
        InvalidRedEdgeCampaignError,
        InvalidRedEdgeFolderError,
        IncompleteRedEdgeFolderError,
        InvalidRedEdgeCaptureRoleError,
    ) as exc:

        return jsonify({
            "error": True,
            "msg": str(exc),
        }), 400

    except (
        RedEdgeImportExecutionError,
        RedEdgeStagingError,
    ) as exc:

        return jsonify({
            "error": True,
            "msg": str(exc),
        }), 500

@app.route(
    (
        "/api/campaigns/"
        "<int:campaign_id>/"
        "rededge/staging/"
        "<string:token>"
    ),
    methods=["DELETE"],
)
def api_delete_rededge_staging(
    campaign_id,
    token,
):

    try:
        deleted = (
            RedEdgeStagingService
            .delete_stage(
                token=token,
                campaign_id=campaign_id,
            )
        )

        return jsonify({
            "deleted": deleted,
        })

    except InvalidRedEdgeStageError as exc:

        return jsonify({
            "error": True,
            "msg": str(exc),
        }), 404

    except RedEdgeStagingError as exc:

        return jsonify({
            "error": True,
            "msg": str(exc),
        }), 500

@app.route(
    "/api/campaigns/<int:campaign_id>/rededge/staging",
    methods=["POST"],
)
def api_create_rededge_staging(
    campaign_id
):

    try:
        campaign = (
            CampaignService.get_campaign(
                campaign_id
            )
        )

        if campaign is None:
            return jsonify({
                "error": True,
                "msg": (
                    "La campaña con ID "
                    f"{campaign_id} no existe."
                ),
            }), 404

        if (
            campaign["sensor_type"]
            != "MULTISPECTRAL"
        ):
            return jsonify({
                "error": True,
                "msg": (
                    "La importación RedEdge "
                    "requiere una campaña "
                    "MULTISPECTRAL."
                ),
            }), 400

        token = (
            RedEdgeStagingService
            .create_stage(
                campaign_id=campaign_id
            )
        )

        return jsonify({
            "staging_token": token,
        }), 201

    except RedEdgeStagingError as exc:

        return jsonify({
            "error": True,
            "msg": str(exc),
        }), 500
        
@app.route(
    (
        "/api/campaigns/"
        "<int:campaign_id>/"
        "rededge/staging/"
        "<string:token>/files"
    ),
    methods=["POST"],
)
def api_upload_rededge_stage_files(
    campaign_id,
    token,
):

    stored_paths = []

    try:
        (
            RedEdgeStagingService
            .get_stage_directory(
                token=token,
                campaign_id=campaign_id,
            )
        )

        uploads = (
            request.files.getlist(
                "files"
            )
        )

        if not uploads:
            return jsonify({
                "error": True,
                "msg": (
                    "No se recibieron archivos."
                ),
            }), 400

        max_files = (
            Config
            .RED_EDGE_UPLOAD_BATCH_MAX_FILES
        )

        if len(uploads) > max_files:
            return jsonify({
                "error": True,
                "msg": (
                    "El lote supera el máximo "
                    f"de {max_files} archivos."
                ),
            }), 400

        relative_paths_raw = (
            request.form.get(
                "relative_paths"
            )
        )

        if not relative_paths_raw:
            return jsonify({
                "error": True,
                "msg": (
                    "No se recibieron "
                    "las rutas relativas."
                ),
            }), 400

        try:
            relative_paths = (
                json.loads(
                    relative_paths_raw
                )
            )

        except json.JSONDecodeError:
            return jsonify({
                "error": True,
                "msg": (
                    "relative_paths "
                    "no contiene JSON válido."
                ),
            }), 400

        if not isinstance(
            relative_paths,
            list,
        ):
            return jsonify({
                "error": True,
                "msg": (
                    "relative_paths debe "
                    "ser una lista."
                ),
            }), 400

        if (
            len(relative_paths)
            != len(uploads)
        ):
            return jsonify({
                "error": True,
                "msg": (
                    "La cantidad de archivos "
                    "no coincide con las "
                    "rutas relativas."
                ),
            }), 400

        for (
            upload,
            relative_path,
        ) in zip(
            uploads,
            relative_paths,
        ):

            stored = (
                RedEdgeStagingService
                .stage_file(
                    token=token,
                    campaign_id=campaign_id,
                    relative_path=(
                        relative_path
                    ),
                    source_stream=(
                        upload.stream
                    ),
                )
            )

            stored_paths.append(
                stored
            )

        return jsonify({
            "stored_count": (
                len(stored_paths)
            ),
        }), 201

    except InvalidRedEdgeStageError as exc:

        # Revertimos únicamente los archivos
        # incorporados por este lote.
        for path in reversed(
            stored_paths
        ):
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                pass

        return jsonify({
            "error": True,
            "msg": str(exc),
        }), 400

    except RedEdgeStagingError as exc:

        for path in reversed(
            stored_paths
        ):
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                pass

        return jsonify({
            "error": True,
            "msg": str(exc),
        }), 500
        
@app.route(
    (
        "/api/campaigns/"
        "<int:campaign_id>/"
        "rededge/staging/"
        "<string:token>/inspect"
    ),
    methods=["POST"],
)
def api_inspect_rededge_stage(
    campaign_id,
    token,
):

    try:
        inspection = (
            RedEdgeStagingService
            .inspect_stage(
                token=token,
                campaign_id=campaign_id,
            )
        )

        if (
            inspection["group_count"]
            == 0
        ):
            return jsonify({
                "error": True,
                "msg": (
                    "No se detectaron "
                    "capturas RedEdge."
                ),
            }), 400

        return jsonify({
            "staging_token": token,
            "inspection": inspection,
        })

    except (
        InvalidRedEdgeStageError,
        InvalidRedEdgeFolderError,
        RedEdgeImportError,
    ) as exc:

        return jsonify({
            "error": True,
            "msg": str(exc),
        }), 400

    except RedEdgeStagingError as exc:

        return jsonify({
            "error": True,
            "msg": str(exc),
        }), 500

if __name__ == "__main__":
    app.run(
        debug=Config.FLASK_DEBUG,
        host=Config.FLASK_HOST,
        port=Config.FLASK_PORT
    )

