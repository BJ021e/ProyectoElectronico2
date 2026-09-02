# ====================================================
# Flask PC: Ground Control (Con Cálculo de Promedios)
# Archivo: principal.py
# ====================================================
from flask import Flask, render_template, request, redirect, url_for, session, send_file, jsonify
import os
import threading
import shutil
import time
import numpy as np
import cv2
import rasterio
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from config import Config
from models import TelemetrySource

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

app = Flask(__name__)
app.secret_key = Config.SECRET_KEY

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
def index(): return redirect(url_for('ground_login'))

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
        
if __name__ == "__main__":
    app.run(
        debug=Config.FLASK_DEBUG,
        host=Config.FLASK_HOST,
        port=Config.FLASK_PORT
    )