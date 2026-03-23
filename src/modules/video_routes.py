"""
Módulo de rutas de video
"""
import json
import logging
import os
import subprocess
import time
import uuid
from flask import jsonify, request

logger = logging.getLogger("ffmpeg-api")

from .gpu import get_gpu_preset_and_level
from .process_manager import get_process_manager
from .ffmpeg_runner import run_ffmpeg


def register_video_routes(app):
    """Registra las rutas de video en la aplicación"""
    
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
                logger.info(f"✅  GPU detectada: {gpu_name}")
                return jsonify({
                    "success": True,
                    "gpu_available": True,
                    "gpu_name": gpu_name
                })
            else:
                logger.warning("⚠️ No se detectó GPU NVIDIA")
                return jsonify({"success": True, "gpu_available": False})
        except Exception as e:
            logger.error(f"❌  Error verificando GPU: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route('/optimize', methods=['POST'])
    def optimize():
        """Iniciar optimización de video con parámetros específicos"""
        data = request.json
        input_path = data.get('input')
        output_path = data.get('output')
        
        logger.info(f"📥 Recibida petición optimize: input={input_path}, output={output_path}")
        
        if not input_path or not output_path:
            logger.error("❌  input y output son requeridos")
            return jsonify({"error": "input y output son requeridos"}), 400
        
        if not os.path.exists(input_path):
            logger.error(f"❌  Input file not found: {input_path}")
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
        
        # Construir comando base con mapping genérico por tipo
        # Esto maneja automáticamente archivos con múltiples streams de audio
        cmd = [
            "ffmpeg",
            "-hwaccel", "cuda",
            "-i", temp_input if needs_copy else input_path,
            "-map", "0:v:0",           # Selecciona el primer stream de video
            "-map", "0:a:0?",          # Selecciona el primer stream de audio (opcional)
            "-map", "0:s:0?",           # Selecciona el primer stream de subtítulos (opcional)
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
            "-disposition:a:0", "default",  # Marcar el audio como default
            "-f", "matroska",
            "-y",
            output_path
        ])
        
        logger.info(f"🎬 Comando: {' '.join(cmd)}")
        
        # Gestor de procesos
        process_manager = get_process_manager()
        
        # Crear entrada en el diccionario compartido
        process_manager.set(process_id, {
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
        
        logger.info(f"[{process_id}] ✅  Proceso creado en diccionario compartido")
        
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
                process = process_manager.get(process_id)
                if process:
                    process["total_duration"] = duration
                logger.info(f"⏱️ Duración total: {duration:.2f} segundos")
        except Exception as e:
            logger.warning(f"⚠️ No se pudo obtener duración: {e}")
        
        # Guardar estado inicial en archivo
        process_manager.save_to_file(process_id)
        logger.info(f"[{process_id}] 💾 Estado inicial guardado en archivo")
        
        # Importar Process aquí para evitar problemas de importación circular
        from multiprocessing import Process
        p = Process(target=run_ffmpeg, args=(process_id, cmd))
        p.daemon = True
        p.start()
        
        return jsonify({
            "success": True,
            "process_id": process_id,
            "message": "Optimización iniciada"
        })

    @app.route('/status/<process_id>', methods=['GET'])
    def get_status(process_id):
        """Obtiene el estado de un proceso"""
        process_manager = get_process_manager()
        process = process_manager.get(process_id)
        
        # Si no está en memoria, intentar leer del archivo
        if not process:
            process = process_manager.get_from_file(process_id)
        
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
        process_manager = get_process_manager()
        active = process_manager.list_active()
        logger.info(f"📋 Procesos activos: {len(active)}")
        return jsonify({"success": True, "active": active})

    @app.route('/cancel/<process_id>', methods=['POST'])
    def cancel_process(process_id):
        """Cancelar un proceso"""
        process_manager = get_process_manager()
        process = process_manager.get(process_id)
        if process and process.get("pid"):
            try:
                import signal
                os.kill(process.get("pid"), signal.SIGTERM)  # SIGTERM
                process["status"] = "cancelled"
                logger.info(f"[{process_id}] ⛔  Proceso cancelado")
                return jsonify({"success": True, "message": "Proceso cancelado"})
            except Exception as e:
                logger.error(f"[{process_id}] ❌  Error cancelando: {e}")
        
        logger.warning(f"⚠️ Cancelación no implementada para {process_id}")
        return jsonify({"error": "Not implemented"}), 501