#!/usr/bin/env python3
"""
FFmpeg API Service - Ejecuta FFmpeg con GPU y expone endpoints REST
"""
import os
import shutil
import subprocess
from multiprocessing import Process, Manager
import threading
import time
import uuid
import logging
import json
import re
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ffmpeg-api")

# Almacenamiento en memoria de procesos activos
# Usamos un Manager().dict() para compartir entre procesos
manager = Manager()
processes = manager.dict()

# Función para actualizar estado en archivo (para multiprocessing)
def update_process_status(process_id, status, **kwargs):
    """Actualiza el estado del proceso en el diccionario local y en archivo"""
    if process_id in processes:
        processes[process_id]["status"] = status
        for key, value in kwargs.items():
            processes[process_id][key] = value
        # Also save to file for cross-process visibility
        try:
            status_file = f"/tmp/ffmpeg_status_{process_id}.json"
            with open(status_file, 'w') as f:
                json.dump(dict(processes[process_id]), f)
        except Exception as e:
            logger.error(f"[update_process_status] Error guardando archivo: {e}")

def get_gpu_preset_and_level():
    """Detectar GPU y devolver preset y configuración adecuada"""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            gpu_name = result.stdout.strip().split('\n')[0]
            logger.info(f"✅ GPU detectada: {gpu_name}")
            
            # GPUs Maxwell (9xxM) - NO incluir level, preset p4
            if any(model in gpu_name for model in ["960M", "950M", "860M", "GTX 9"]):
                logger.info("🔧 GPU Maxwell detectada - preset p4, sin level")
                return {
                    "preset": "p4", 
                    "include_level": False,
                    "multipass": "none", 
                    "lookahead": "16"
                }
            # GPUs Pascal (10xx) - incluir level 4.1, preset p6
            elif any(model in gpu_name for model in ["1050", "1060", "1070", "1080", "GTX 10"]):
                logger.info("🔧 GPU Pascal detectada - preset p6, level 4.1")
                return {
                    "preset": "p6", 
                    "include_level": True,
                    "level": "4.1",
                    "multipass": "fullres", 
                    "lookahead": "32"
                }
            # GPUs Turing/Ampere (20xx, 30xx, 40xx) - preset p7, level 4.1
            else:
                logger.info("🔧 GPU moderna detectada - preset p7, level 4.1")
                return {
                    "preset": "p7", 
                    "include_level": True,
                    "level": "4.1",
                    "multipass": "fullres", 
                    "lookahead": "32"
                }
        else:
            logger.warning("⚠️ No se detectó GPU NVIDIA - usando valores seguros")
            return {
                "preset": "p4", 
                "include_level": False,
                "multipass": "none", 
                "lookahead": "16"
            }
    except Exception as e:
        logger.error(f"❌ Error detectando GPU: {e}")
        return {
            "preset": "p4", 
            "include_level": False,
            "multipass": "none", 
            "lookahead": "16"
        }

@app.route('/health', methods=['GET'])
def health():
    """Health check"""
    return jsonify({"status": "UP", "service": "ffmpeg-api"})

@app.route('/gpu-status', methods=['GET'])
def gpu_status():
    """Verificar disponibilidad de GPU"""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            gpu_name = result.stdout.strip().split('\n')[0]
            logger.info(f"✅ GPU detectada: {gpu_name}")
            return jsonify({
                "success": True,
                "gpu_available": True,
                "gpu_name": gpu_name
            })
        else:
            logger.warning("⚠️ No se detectó GPU NVIDIA")
            return jsonify({"success": True, "gpu_available": False})
    except Exception as e:
        logger.error(f"❌ Error verificando GPU: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/optimize', methods=['POST'])
def optimize():
    """Iniciar optimización de video con parámetros específicos"""
    data = request.json
    input_path = data.get('input')
    output_path = data.get('output')
    
    logger.info(f"📥 Recibida petición optimize: input={input_path}, output={output_path}")
    
    if not input_path or not output_path:
        logger.error("❌ input y output son requeridos")
        return jsonify({"error": "input y output son requeridos"}), 400
    
    if not os.path.exists(input_path):
        logger.error(f"❌ Input file not found: {input_path}")
        return jsonify({"error": f"Input file not found: {input_path}"}), 404
    
    # Verificar tamaño del archivo
    file_size = os.path.getsize(input_path) / (1024 * 1024 * 1024)  # GB
    logger.info(f"📊 Tamaño del archivo: {file_size:.2f} GB")
    
    process_id = str(uuid.uuid4())
    logger.info(f"🆔 Nuevo proceso: {process_id}")
    
    # Determinar si es necesario copiar el archivo (si está en /downloads)
    # Si el input está en /downloads, copiar a /temp para mejor rendimiento
    original_input = input_path
    needs_copy = input_path.startswith('/downloads') or input_path.startswith('~/downloads')
    temp_input = input_path
    
    if needs_copy:
        # Crear path temporal en /temp
        filename = os.path.basename(input_path)
        temp_dir = '/tmp/ffmpeg_input'
        os.makedirs(temp_dir, exist_ok=True)
        temp_input = os.path.join(temp_dir, f"{process_id}_{filename}")
        logger.info(f"📁 Archivo en /downloads detectado - será copiado a {temp_input}")
    
    # Detectar configuración según GPU
    gpu_config = get_gpu_preset_and_level()
    
    # Construir comando base
    cmd = [
        "ffmpeg",
        "-hwaccel", "cuda",
        "-i", temp_input if needs_copy else input_path,  # Usar temp_input si hay copia
        "-c:v", "h264_nvenc",
        "-preset", gpu_config["preset"],
        "-rc", "vbr",
        "-tune", "hq",
    ]
    
    # Añadir multipass solo si no es "none"
    if gpu_config["multipass"] != "none":
        cmd.extend(["-multipass", gpu_config["multipass"]])
    
    cmd.extend([
        "-cq", "28",
        "-b:v", "1800k",
        "-maxrate", "2200k",
        "-bufsize", "4400k",
        "-rc-lookahead", gpu_config["lookahead"],
        "-profile:v", "high",
    ])
    
    # Añadir level SOLO si include_level es True
    if gpu_config.get("include_level", False):
        cmd.extend(["-level", gpu_config["level"]])
    
    cmd.extend([
        "-pix_fmt", "yuv420p",
        "-g", "120",
        "-c:a", "aac",
        "-b:a", "128k",
        "-ac", "2",
        "-ar", "48000",
        "-c:s", "copy",
        "-f", "matroska",
        "-y",
        output_path
    ])
    
    logger.info(f"🎬 Comando: {' '.join(cmd)}")
    
    # Crear entrada en el diccionario compartido
    processes[process_id] = manager.dict({
        "id": process_id,
        "cmd": " ".join(cmd),
        "input": original_input,
        "input_for_ffmpeg": temp_input,
        "output": output_path,
        "status": "starting",
        "progress": 0,
        "start_time": time.time(),
        "logs": [],
        "total_duration": None,
        "gpu_config": gpu_config,
        "needs_copy": needs_copy,
        "copy_progress": 0
    })
    
    logger.info(f"[{process_id}] ✅ Proceso creado en diccionario compartido")
    
    # Intentar obtener duración total
    try:
        duration_cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            input_path
        ]
        result = subprocess.run(duration_cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and result.stdout.strip():
            duration = float(result.stdout.strip())
            processes[process_id]["total_duration"] = duration
            logger.info(f"⏱️ Duración total: {duration:.2f} segundos")
    except Exception as e:
        logger.warning(f"⚠️ No se pudo obtener duración: {e}")
    
    # Guardar estado inicial en archivo
    status_file = f"/tmp/ffmpeg_status_{process_id}.json"
    try:
        with open(status_file, 'w') as f:
            json.dump(dict(processes[process_id]), f)
        logger.info(f"[{process_id}] 💾 Estado inicial guardado en archivo")
    except Exception as e:
        logger.error(f"[{process_id}] ❌ Error guardando estado inicial: {e}")
    
    p = Process(target=_run_ffmpeg, args=(process_id, cmd))
    p.daemon = True
    p.start()
    
    return jsonify({
        "success": True,
        "process_id": process_id,
        "message": "Optimización iniciada"
    })

def _run_ffmpeg(process_id, cmd):
    """Ejecuta FFmpeg en segundo plano y calcula progreso"""
    
    # Función local para actualizar estado
    def save_status(status, **kwargs):
        try:
            if process_id in processes:
                processes[process_id]["status"] = status
                for key, value in kwargs.items():
                    processes[process_id][key] = value
                # Guardar en archivo para persistencia
                status_file = f"/tmp/ffmpeg_status_{process_id}.json"
                with open(status_file, 'w') as f:
                    json.dump(dict(processes[process_id]), f)
                logger.info(f"[{process_id}] 💾 Guardado estado: {status}, progress: {kwargs.get('progress', 'N/A')}")
            else:
                # Si no existe en processes, crear entrada básica y guardar
                basic_info = {"status": status, **kwargs}
                status_file = f"/tmp/ffmpeg_status_{process_id}.json"
                with open(status_file, 'w') as f:
                    json.dump(basic_info, f)
                logger.warning(f"[{process_id}] ⚠️ Proceso no estaba en memoria, guardado básico: {status}")
        except Exception as e:
            logger.error(f"[{process_id}] ❌ Error guardando estado: {e}")
    
    logger.info(f"[{process_id}] 🚀 Iniciando _run_ffmpeg")
    
    # Cargar process_info del archivo o de memoria
    process_info = None
    if process_id in processes:
        process_info = processes[process_id]
    else:
        # Intentar leer del archivo
        status_file = f"/tmp/ffmpeg_status_{process_id}.json"
        if os.path.exists(status_file):
            try:
                with open(status_file, 'r') as f:
                    process_info = json.load(f)
                    # Sincronizar con el diccionario compartido
                    processes[process_id] = manager.dict(process_info)
                    logger.info(f"[{process_id}] 📥 Cargado desde archivo")
            except Exception as e:
                logger.error(f"[{process_id}] ❌ Error leyendo archivo: {e}")
    
    if not process_info:
        logger.error(f"[{process_id}] ❌ No se pudo obtener process_info")
        return
    
    # Obtener duración total si no se tiene
    total_duration = process_info.get("total_duration")
    if not total_duration:
        try:
            # Extraer input path del comando
            input_idx = cmd.index("-i") + 1
            input_path = cmd[input_idx]
            
            duration_cmd = ["ffprobe", "-v", "error", "-show_entries", 
                           "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", 
                           input_path]
            result = subprocess.run(duration_cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and result.stdout.strip():
                total_duration = float(result.stdout.strip())
                process_info["total_duration"] = total_duration
                logger.info(f"[{process_id}] ⏱️ Duración total: {total_duration:.2f}s")
        except Exception as e:
            logger.warning(f"[{process_id}] ⚠️ No se pudo obtener duración: {e}")
    
    # Primero: copiar archivo si es necesario
    if process_info.get("needs_copy", False):
        save_status("copying")
        # ... (código de copia existente) ...
    
    # Segundo: ejecutar FFmpeg
    logger.info(f"[{process_id}] 🚀 Iniciando FFmpeg")
    
    try:
        # Leer stdout línea por línea para calcular progreso
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        
        process_info["pid"] = proc.pid
        process_info["log_file"] = f"/tmp/ffmpeg_{process_id}.log"
        
        # ✅ CAMBIAR ESTADO A RUNNING INMEDIATAMENTE
        save_status("running", pid=proc.pid, start_time=time.time())
        logger.info(f"[{process_id}] 🔴 ESTADO CAMBIADO A RUNNING - PID: {proc.pid}")
        
        # Guardar también en archivo de log
        with open(process_info["log_file"], 'w') as log_f:
            # Leer línea por línea
            for line in proc.stdout:
                line = line.strip()
                log_f.write(line + "\n")
                log_f.flush()
                
                # Guardar últimas líneas en memoria
                if "logs" not in process_info:
                    process_info["logs"] = []
                process_info["logs"].append(line)
                if len(process_info["logs"]) > 100:
                    process_info["logs"] = process_info["logs"][-100:]
                
                # Calcular progreso si tenemos duración total
                if total_duration and "time=" in line:
                    try:
                        # Buscar patrón time=HH:MM:SS.MS
                        time_match = re.search(r'time=(\d{2}):(\d{2}):(\d{2})\.(\d{2})', line)
                        if time_match:
                            hours = int(time_match.group(1))
                            minutes = int(time_match.group(2))
                            seconds = int(time_match.group(3))
                            current_seconds = hours * 3600 + minutes * 60 + seconds
                            
                            progress = (current_seconds / total_duration) * 100
                            process_info["progress"] = min(100, progress)
                            
                            # Guardar cada 5% para no saturar
                            if int(progress) % 5 == 0:
                                logger.info(f"[{process_id}] Progreso: {progress:.1f}% (estado={process_info.get('status')})")
                                
                                # Guardar estado en archivo periódicamente
                                save_status("running", progress=process_info["progress"])
                    except Exception as e:
                        pass
        
        # Esperar a que termine
        return_code = proc.wait()
        
        if return_code == 0:
            save_status("completed", progress=100, end_time=time.time())
            logger.info(f"[{process_id}] ✅ Optimización completada")
        else:
            save_status("error", error=process_info.get("error") or f"FFmpeg exited with code {return_code}")
            logger.error(f"[{process_id}] ❌ Error en FFmpeg: {return_code}")
    
    except Exception as e:
        save_status("error", error=str(e))
        logger.error(f"[{process_id}] ❌ Excepción: {e}")
        
        
@app.route('/status/<process_id>', methods=['GET'])
def get_status(process_id):
    process = processes.get(process_id)
    
    # Si no está en memoria, intentar leer del archivo
    if not process:
        status_file = f"/tmp/ffmpeg_status_{process_id}.json"
        if os.path.exists(status_file):
            try:
                with open(status_file, 'r') as f:
                    process = json.load(f)
                    # Actualizar memoria
                    try:
                        processes[process_id] = manager.dict(process)
                    except:
                        pass
            except Exception as e:
                logger.error(f"[{process_id}] Error leyendo archivo de estado: {e}")
    
    if not process:
        logger.warning(f"⚠️ Proceso no encontrado: {process_id}")
        return jsonify({"error": "Process not found"}), 404
    
    # LOG IMPORTANTE: Ver qué estado se está devolviendo
    logger.info(f"[{process_id}] 📤 Devolviendo status: {process.get('status')}, progress: {process.get('progress', 0)}")
    
    # Calcular ETA si está running y tiene progreso
    eta_seconds = None
    if process.get("status") == "running" and process.get("progress", 0) > 0:
        elapsed = time.time() - process.get("start_time", time.time())
        progress = process.get("progress", 0)
        if progress > 0:
            total_estimated = (elapsed / progress) * 100
            eta_seconds = int(total_estimated - elapsed)
    
    response = {
        "success": True,
        "process_id": process_id,
        "status": process.get("status"),
        "progress": round(process.get("progress", 0), 1),
        "logs": process.get("logs", [])[-50:],
        "input_file": os.path.basename(process.get("input", "")),
        "output_file": os.path.basename(process.get("output", "")),
        "eta_seconds": eta_seconds,
        "error": process.get("error")
    }
    
    return jsonify(response)

@app.route('/active', methods=['GET'])
def list_active():
    """Listar procesos activos"""
    active = []
    for pid, p in processes.items():
        status = p.get("status", "unknown")
        if status in ["starting", "running", "copying"]:
            active.append({
                "id": pid, 
                "status": status, 
                "progress": p.get("progress", 0)
            })
    logger.info(f"📋 Procesos activos: {len(active)}")
    return jsonify({"success": True, "active": active})

@app.route('/cancel/<process_id>', methods=['POST'])
def cancel_process(process_id):
    """Cancelar un proceso (TODO)"""
    process = processes.get(process_id)
    if process and process.get("pid"):
        try:
            os.kill(process.get("pid"), 15)  # SIGTERM
            process["status"] = "cancelled"
            logger.info(f"[{process_id}] ⛔ Proceso cancelado")
            return jsonify({"success": True, "message": "Proceso cancelado"})
        except Exception as e:
            logger.error(f"[{process_id}] ❌ Error cancelando: {e}")
    logger.warning(f"⚠️ Cancelación no implementada para {process_id}")
    return jsonify({"error": "Not implemented"}), 501

if __name__ == '__main__':
    logger.info("🚀 Iniciando FFmpeg API en puerto 8080")
    app.run(host='0.0.0.0', port=8080, debug=False)