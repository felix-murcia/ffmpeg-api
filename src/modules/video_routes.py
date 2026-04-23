"""
Módulo de rutas de video - Refactorizado con principios SOLID.
Mantiene compatibilidad total con la API existente.
"""

import logging
import time
import os
import subprocess
from flask import jsonify, request

logger = logging.getLogger("ffmpeg-api")

from .gpu import get_gpu_preset_and_level
from .process_manager import get_process_manager
from .video_helper import (
    FileHandler,
    FFmpegExecutor,
    VideoOptimizer,
    VideoCreator,
    VideoOptimizationError,
    VideoCreationError,
    FileNotFoundError,
)

# Initialize shared dependencies
_file_handler = FileHandler(temp_dir="/tmp")
_ffmpeg_executor = FFmpegExecutor(logger)
_process_manager = get_process_manager()

# Initialize video services
_video_optimizer = VideoOptimizer(
    _ffmpeg_executor, _file_handler, _process_manager, get_gpu_preset_and_level, logger
)
_video_creator = VideoCreator(_ffmpeg_executor, _file_handler, logger)


def register_video_routes(app):
    """Registra las rutas de video en la aplicación"""

    @app.route("/health", methods=["GET"])
    def health():
        """Health check"""
        return jsonify({"status": "UP", "service": "ffmpeg-api"})

    @app.route("/gpu-status", methods=["GET"])
    def gpu_status():
        """Verificar disponibilidad de GPU"""
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                gpu_name = result.stdout.strip().split("\n")[0]
                logger.info(f"✅  GPU detectada: {gpu_name}")
                return jsonify(
                    {"success": True, "gpu_available": True, "gpu_name": gpu_name}
                )
            else:
                logger.warning("⚠️ No se detectó GPU NVIDIA")
                return jsonify({"success": True, "gpu_available": False})
        except Exception as e:
            logger.error(f"❌  Error verificando GPU: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/optimize", methods=["POST"])
    def optimize():
        """Iniciar optimización de video con parámetros específicos"""
        data = request.json
        input_path = data.get("input")
        output_path = data.get("output")

        if not input_path or not output_path:
            logger.error("❌  input y output son requeridos")
            return jsonify({"error": "input y output son requeridos"}), 400

        try:
            process_id = _video_optimizer.launch_optimization(input_path, output_path)
            return jsonify(
                {
                    "success": True,
                    "process_id": process_id,
                    "message": "Optimización iniciada",
                }
            )
        except FileNotFoundError as e:
            logger.error(f"❌ Input file not found: {e}")
            return jsonify({"error": str(e)}), 404
        except VideoOptimizationError as e:
            logger.error(f"❌ Optimization error: {e}")
            return jsonify({"error": str(e)}), 500
        except Exception as e:
            logger.error(f"❌ Unexpected error in optimize: {e}")
            return jsonify({"error": "Internal server error"}), 500

    @app.route("/status/<process_id>", methods=["GET"])
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
        logger.info(
            f"[{process_id}] 📤 Devolviendo status: {process.get('status')}, progress: {process.get('progress', 0)}"
        )

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
            "error": process.get("error"),
        }

        return jsonify(response)

    @app.route("/active", methods=["GET"])
    def list_active():
        """Listar procesos activos"""
        process_manager = get_process_manager()
        active = process_manager.list_active()
        logger.info(f"📋 Procesos activos: {len(active)}")
        return jsonify({"success": True, "active": active})

    @app.route("/cancel/<process_id>", methods=["POST"])
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

    @app.route("/create-from-audio", methods=["POST"])
    def create_from_audio():
        """Crear video a partir de un audio y una imagen proporcionada"""
        data = request.json
        audio_path = data.get("audio_path")
        image_path = data.get("image_path")

        if not audio_path or not image_path:
            logger.error("❌ audio_path e image_path son requeridos")
            return jsonify({"error": "audio_path e image_path son requeridos"}), 400

        try:
            result = _video_creator.create(audio_path, image_path)
            return jsonify(result), 200
        except FileNotFoundError as e:
            logger.error(f"❌ File not found: {e}")
            return jsonify({"error": str(e)}), 404
        except VideoCreationError as e:
            logger.error(f"❌ Video creation error: {e}")
            return jsonify({"error": str(e)}), 500
        except Exception as e:
            logger.error(f"❌ Unexpected error: {e}")
            return jsonify({"error": str(e)}), 500
