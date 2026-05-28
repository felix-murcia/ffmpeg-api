"""
Módulo de rutas de audio - Refactorizado con principios SOLID.
Mantiene compatibilidad total con la API existente.
"""

import json
import logging
import os
import shutil
import uuid
from flask import jsonify, request, Response
from werkzeug.datastructures import FileStorage

logger = logging.getLogger("ffmpeg-api")

from .utils import format_duration
from .config import TimeoutConfig

# Import services from audio_helper
from .audio_helper import (
    FileHandler,
    FFmpegExecutor,
    AudioInfoService,
    AudioConverter,
    AudioCleaner,
    AudioValidator,
    AudioStreamDetector,
    AudioValidationError,
    AudioConversionError,
    AudioInfoError,
)

# Constants
MAX_FILE_SIZE_MB = 25
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


# Initialize shared dependencies
_file_handler = FileHandler(temp_dir="/tmp")
_ffmpeg_executor = FFmpegExecutor(logger)


def register_audio_routes(app):
    """Registra las rutas de audio en la aplicación"""
    logger.info("Registrando rutas de audio...")

    @app.route("/audio/info", methods=["POST"])
    def audio_info():
        """Devuelve metadata del audio usando ffprobe."""
        if "file" not in request.files:
            return jsonify({"error": "No se envió ningún archivo"}), 400

        file = request.files["file"]
        temp_id = str(uuid.uuid4())

        try:
            input_path = _file_handler.save_upload(file, temp_id)

            service = AudioInfoService(_ffmpeg_executor, _file_handler)
            info = service.get_audio_info(input_path)

            return jsonify(info)
        except AudioInfoError as e:
            logger.error(f"Audio info error: {e}")
            return jsonify({"error": "ffprobe error", "details": str(e)}), 500
        except Exception as e:
            logger.error(f"Unexpected error in audio_info: {e}")
            return jsonify({"error": "ffprobe error", "details": str(e)}), 500
        finally:
            _file_handler.cleanup(input_path)

    @app.route("/audio/convert", methods=["POST"])
    def convert_audio():
        """Convierte un archivo de audio a WAV 16kHz mono o MP3."""
        if "file" not in request.files:
            return jsonify({"error": "No se envió ningún archivo"}), 400

        fmt = request.form.get("format", "wav")  # wav o mp3

        file = request.files["file"]
        temp_id = str(uuid.uuid4())

        try:
            input_path = _file_handler.save_upload(file, temp_id)

            service = AudioConverter(_ffmpeg_executor, _file_handler)
            audio_data, mime_type, filename = service.convert(input_path, fmt, temp_id)

            return (
                audio_data,
                200,
                {
                    "Content-Type": mime_type,
                    "Content-Disposition": f"attachment; filename={filename}",
                },
            )
        except AudioConversionError as e:
            logger.error(f"Audio conversion error: {e}")
            return jsonify({"error": "FFmpeg error", "details": str(e)}), 500
        except Exception as e:
            logger.error(f"Unexpected error in convert_audio: {e}")
            return jsonify({"error": "FFmpeg error", "details": str(e)}), 500
        finally:
            _file_handler.cleanup(input_path)

    @app.route("/audio/convert-to-wav16k", methods=["POST"])
    def convert_to_wav16k():
        """Convierte cualquier archivo de audio a WAV 16kHz mono (formato estándar para transcripción).

        Acepta:
        - multipart/form-data con campo 'file' (límite 25 MB)
        - JSON con campo 'path' (ruta absoluta en el filesystem compartido, sin límite de tamaño)
        """
        input_path = None
        temp_id = None

        # Determinar origen: multipart (file) o JSON (path)
        if "file" in request.files:
            # Modo subida de archivo
            file = request.files["file"]

            # Validar tamaño (máximo 25 MB)
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            file.seek(0)

            if file_size > MAX_FILE_SIZE_BYTES:
                return jsonify(
                    {
                        "error": f"Archivo demasiado grande",
                        "max_size_mb": MAX_FILE_SIZE_MB,
                        "file_size_mb": round(file_size / (1024 * 1024), 2),
                    }
                ), 413  # Payload Too Large

            temp_id = str(uuid.uuid4())
            try:
                input_path = _file_handler.save_upload(file, temp_id)
            except Exception as e:
                logger.error(f"Error guardando archivo subido: {e}")
                return jsonify({"error": "No se pudo guardar el archivo"}), 500

        elif request.is_json:
            # Modo ruta (path-based)
            data = request.get_json()
            input_path = data.get("path")
            if not input_path:
                return jsonify({"error": "Se requiere 'path' en el JSON"}), 400
            if not os.path.exists(input_path):
                return jsonify({"error": f"Archivo no encontrado: {input_path}"}), 404
        else:
            return jsonify({"error": "No se envió archivo ni ruta válida"}), 400

        # Convertir a WAV16k
        try:
            service = AudioConverter(_ffmpeg_executor, _file_handler)
            audio_data, mime_type, filename = service.convert_to_wav16k_mono(
                input_path, temp_id or "path_upload"
            )

            return (
                audio_data,
                200,
                {
                    "Content-Type": mime_type,
                    "Content-Disposition": f"attachment; filename={filename}",
                },
            )
        except AudioConversionError as e:
            logger.error(f"Audio conversion error: {e}")
            return jsonify({"error": "FFmpeg error", "details": str(e)}), 500
        except Exception as e:
            logger.error(f"Unexpected error in convert_to_wav16k: {e}")
            return jsonify({"error": "FFmpeg error", "details": str(e)}), 500
        finally:
            # Solo limpiar archivos subidos temporales; los archivos por ruta NO se borran
            if temp_id and input_path:
                try:
                    _file_handler.cleanup(input_path)
                except Exception:
                    pass

    @app.route("/audio/convert-to-mp3", methods=["POST"])
    def convert_to_mp3():
        """
        Convierte un archivo de audio a MP3 (compatible con cliente legacy).
        Reemplaza el subprocess.run directo del cliente.
        """
        data = request.json
        input_path = data.get("path")

        if not input_path:
            return jsonify({"error": "Se requiere la ruta del archivo"}), 400

        if not os.path.exists(input_path):
            return jsonify({"error": f"Archivo no encontrado: {input_path}"}), 404

        try:
            service = AudioConverter(_ffmpeg_executor, _file_handler)
            output_path = service.convert_to_mp3_file(input_path, delete_original=True)
            return jsonify({"output": output_path}), 200
        except AudioConversionError as e:
            logger.error(f"MP3 conversion error: {e}")
            return jsonify({"error": str(e)}), 500
        except Exception as e:
            logger.error(f"Unexpected error in convert_to_mp3: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/audio/has-audio-stream", methods=["POST"])
    def has_audio_stream():
        """
        Verifica si un archivo de video/audio contiene un stream de audio.
        Reemplaza el subprocess de ffprobe del cliente.
        """
        data = request.json
        file_path = data.get("path")

        if not file_path:
            return jsonify({"error": "Se requiere la ruta del archivo"}), 400

        if not os.path.exists(file_path):
            return jsonify({"error": f"Archivo no encontrado: {file_path}"}), 404

        try:
            detector = AudioStreamDetector(_ffmpeg_executor)
            has_audio = detector.has_audio_stream(file_path)
            return jsonify({"has_audio": has_audio})
        except Exception as e:
            logger.error(f"Error checking audio stream: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/audio/clean", methods=["POST"])
    def clean_audio():
        """Limpia un archivo de audio: normaliza volumen y convierte a formato estándar."""
        if "file" not in request.files:
            return jsonify({"error": "No se envió ningún archivo"}), 400

        file = request.files["file"]
        temp_id = str(uuid.uuid4())

        try:
            input_path = _file_handler.save_upload(file, temp_id)

            service = AudioCleaner(_ffmpeg_executor, _file_handler, logger)
            audio_data, mime_type, filename = service.clean(input_path, temp_id)

            return (
                audio_data,
                200,
                {
                    "Content-Type": mime_type,
                    "Content-Disposition": f"attachment; filename={filename}",
                },
            )
        except Exception as e:
            logger.error(f"Error in clean_audio: {e}")
            # Fallback: return original
            try:
                with open(input_path, "rb") as f:
                    data = f.read()
                return (
                    data,
                    200,
                    {
                        "Content-Type": "audio/wav",
                        "Content-Disposition": "attachment; filename=original.wav",
                    },
                )
            except Exception as fallback_error:
                logger.error(f"Fallback failed: {fallback_error}")
                return jsonify({"error": "Failed to process audio"}), 500
        finally:
            _file_handler.cleanup(input_path)

    @app.route("/audio/validate", methods=["POST"])
    def validate_audio():
        """
        Valida si un archivo de audio es apto para transcripción.
        Analiza duración, calidad, formato y detecta si hay voz.
        """
        if "file" not in request.files:
            return jsonify({"error": "No se envió ningún archivo"}), 400

        file = request.files["file"]
        temp_id = str(uuid.uuid4())

        try:
            input_path = _file_handler.save_upload(file, temp_id)

            service = AudioValidator(_ffmpeg_executor, _file_handler, format_duration)
            result = service.validate(input_path)

            return jsonify(result)
        except AudioValidationError as e:
            logger.error(f"Validation error: {e}")
            return jsonify(
                {
                    "valid": False,
                    "error": "Error analizando el audio",
                    "details": str(e),
                }
            ), 500
        except Exception as e:
            logger.error(f"Unexpected error in validate_audio: {e}")
            return jsonify(
                {
                    "valid": False,
                    "error": "Error interno al validar el audio",
                    "details": str(e),
                }
            ), 500
        finally:
            _file_handler.cleanup(input_path)

    @app.route("/audio/validate-by-path", methods=["POST"])
    def validate_audio_by_path():
        """Valida un audio por su ruta en el sistema de archivos."""
        data = request.json
        file_path = data.get("path")

        if not file_path:
            return jsonify({"error": "Se requiere la ruta del archivo"}), 400

        if not os.path.exists(file_path):
            return jsonify({"error": f"Archivo no encontrado: {file_path}"}), 404

        # Copy to temp and validate
        temp_id = str(uuid.uuid4())
        temp_path = _file_handler.generate_temp_path(temp_id)

        try:
            _file_handler.copy_file(file_path, temp_id)
            service = AudioValidator(_ffmpeg_executor, _file_handler, format_duration)
            result = service.validate(temp_path)
            return jsonify(result)
        except Exception as e:
            logger.error(f"Error validating by path: {e}")
            return jsonify(
                {
                    "valid": False,
                    "error": "Error analizando el audio",
                    "details": str(e),
                }
            ), 500
        finally:
            _file_handler.cleanup(temp_path)

    @app.route("/audio/convert-by-path", methods=["POST"])
    def convert_audio_by_path():
        """Convierte un archivo de audio por su ruta en el sistema a MP3."""
        data = request.json
        input_path = data.get("path")
        fmt = data.get("format", "mp3")

        if not input_path:
            return jsonify({"error": "Se requiere la ruta del archivo"}), 400

        if not os.path.exists(input_path):
            return jsonify({"error": f"Archivo no encontrado: {input_path}"}), 404

        output_path = os.path.splitext(input_path)[0] + f".{fmt}"

        cmd = [
            "ffmpeg",
            "-threads",
            "0",
            "-i",
            input_path,
            "-vn",
            "-acodec",
            "libmp3lame",
            "-q:a",
            "9",  # VBR mínimo, tamaño reducido
            "-y",
            output_path,
        ]

        try:
            _ffmpeg_executor.run_ffmpeg(cmd, check=True)
            os.remove(input_path)
            return jsonify({"output": output_path}), 200
        except Exception as e:
            logger.error(f"Convert by path error: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/audio/convert-to-mp3-chunked", methods=["POST"])
    def convert_to_mp3_chunked():
        """
        Convierte audio a MP3 y lo divide en chunks para Groq.
        Diseñado para audios largos (>2 horas) que exceden el límite de 25MB.

        Input: {"path": "ruta/al/audio.webm"}
        Output: {
            "chunks": ["/tmp/chunk1.mp3", "/tmp/chunk2.mp3", ...],
            "total_chunks": 3,
            "original_mp3": "/tmp/audio.mp3"  # opcional, para cleanup
        }
        """

        data = request.json
        input_path = data.get("path")
        max_size_mb = data.get("max_size_mb", 22)  # 22MB para margen de seguridad
        
        if not input_path:
            return jsonify({"error": "Se requiere la ruta del archivo"}), 400
        
        if not os.path.exists(input_path):
            return jsonify({"error": f"Archivo no encontrado: {input_path}"}), 404
        
        try:
            service = AudioConverter(_ffmpeg_executor, _file_handler)
            
            # Paso 1: Convertir a MP3 optimizado
            logger.info(f"Convertiendo a MP3: {input_path}")
            mp3_path = service.convert_to_mp3_file(input_path, delete_original=False)
            logger.info(f"MP3 convertido: {mp3_path}")
            # Paso 2: Verificar tamaño y dividir si es necesario
            size_mb = service.get_file_size_mb(mp3_path)
            
            if size_mb <= max_size_mb:
                # No necesita división
                logger.info(f"MP3 pequeño ({size_mb:.1f}MB), no requiere chunking")
                return jsonify({
                    "chunks": [mp3_path],
                    "total_chunks": 1,
                    "needs_chunking": False
                }), 200
            else:
                # Dividir en chunks
                logger.info(f"MP3 grande ({size_mb:.1f}MB), dividiendo en chunks")
                chunks = service.chunk_mp3(mp3_path, max_size_mb)
                
                return jsonify({
                    "chunks": chunks,
                    "total_chunks": len(chunks),
                    "original_mp3": mp3_path,
                    "needs_chunking": True
                }), 200
                
        except AudioConversionError as e:
            logger.error(f"Error en convert-to-mp3-chunked: {e}")
            return jsonify({"error": str(e)}), 500
        except Exception as e:
            logger.error(f"Error inesperado: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/audio/post-process", methods=["POST"])
    def post_process_audio():
        """
        Post-process audio to remove TTS artifacts.

        Implements multi-step enhancement:
        1. Loudness normalization (LUFS-based)
        2. Breathing artifact removal
        3. Plosive/spectral artifact stabilization (EQ)
        4. Dynamic range compression

        Input: {
            "path": "ruta/al/audio.wav",
            "normalize": true,
            "remove_breathing": true,
            "stabilize_plosives": true,
            "noise_gate_threshold": -40.0
        }

        Output: Binary WAV audio data
        """
        from .audio_helper import AudioPostProcessor

        data = request.json or {}
        input_path = data.get("path")

        if not input_path:
            return jsonify({"error": "Se requiere 'path' en el JSON"}), 400

        if not os.path.exists(input_path):
            return jsonify({"error": f"Archivo no encontrado: {input_path}"}), 404

        # Extract optional parameters
        normalize = data.get("normalize", True)
        remove_breathing = data.get("remove_breathing", True)
        stabilize_plosives = data.get("stabilize_plosives", True)
        noise_gate_threshold = float(data.get("noise_gate_threshold", -40.0))

        temp_id = str(uuid.uuid4())

        try:
            service = AudioPostProcessor(_ffmpeg_executor, _file_handler, logger)
            audio_data, mime_type, filename = service.post_process(
                input_path,
                temp_id,
                normalize=normalize,
                remove_breathing=remove_breathing,
                stabilize_plosives=stabilize_plosives,
                noise_gate_threshold=noise_gate_threshold,
            )

            return (
                audio_data,
                200,
                {
                    "Content-Type": mime_type,
                    "Content-Disposition": f"attachment; filename={filename}",
                },
            )
        except Exception as e:
            logger.error(f"[POST-PROCESS] Error: {e}")
            return jsonify({"error": f"Post-processing failed: {str(e)}"}), 500

    @app.route("/audio/apply-atempo", methods=["POST"])
    def apply_atempo_filter():
        """
        Adjust audio speed (tempo) without changing pitch.

        Uses ffmpeg atempo filter for tempo adjustment.

        Input: {
            "path": "ruta/al/audio.wav",
            "tempo_factor": 1.2  # 0.25 to 4.0
        }

        Output: Binary WAV audio data
        """
        from .audio_helper import AudioTempoAdjuster

        data = request.json or {}
        input_path = data.get("path")

        if not input_path:
            return jsonify({"error": "Se requiere 'path' en el JSON"}), 400

        if not os.path.exists(input_path):
            return jsonify({"error": f"Archivo no encontrado: {input_path}"}), 404

        tempo_factor = float(data.get("tempo_factor", 1.0))

        if tempo_factor < 0.25 or tempo_factor > 4.0:
            return jsonify(
                {
                    "error": "Tempo factor must be between 0.25 and 4.0",
                    "received": tempo_factor,
                }
            ), 400

        temp_id = str(uuid.uuid4())

        try:
            service = AudioTempoAdjuster(_ffmpeg_executor, _file_handler, logger)
            audio_data, mime_type, filename = service.adjust_tempo(
                input_path, temp_id, tempo_factor=tempo_factor
            )

            return (
                audio_data,
                200,
                {
                    "Content-Type": mime_type,
                    "Content-Disposition": f"attachment; filename={filename}",
                },
            )
        except Exception as e:
            logger.error(f"[TEMPO] Error: {e}")
            return jsonify({"error": f"Tempo adjustment failed: {str(e)}"}), 500

    @app.route("/audio/concatenate", methods=["POST"])
    def concatenate_audio():
        """
        Concatenate multiple audio files into one.

        Uses ffmpeg concat demuxer for lossless concatenation.

        Input: {
            "paths": ["/tmp/audio1.mp3", "/tmp/audio2.mp3", ...],
            "output_format": "mp3"  # Optional, default: mp3
        }

        Output: Binary audio data in requested format
        """
        from .audio_helper import AudioConcatenator

        data = request.json or {}
        audio_paths = data.get("paths", [])
        output_format = data.get("output_format", "mp3")

        if not audio_paths:
            return jsonify({"error": "Se requiere 'paths' con lista de archivos"}), 400

        if not isinstance(audio_paths, list):
            return jsonify({"error": "'paths' debe ser una lista de rutas"}), 400

        # Validate all files exist
        for path in audio_paths:
            if not os.path.exists(path):
                return jsonify({"error": f"Archivo no encontrado: {path}"}), 404

        temp_id = str(uuid.uuid4())

        try:
            service = AudioConcatenator(_ffmpeg_executor, _file_handler, logger)
            audio_data, mime_type, filename = service.concatenate(
                audio_paths, temp_id, output_format=output_format
            )

            return (
                audio_data,
                200,
                {
                    "Content-Type": mime_type,
                    "Content-Disposition": f"attachment; filename={filename}",
                },
            )
        except Exception as e:
            logger.error(f"[CONCAT] Error: {e}")
            return jsonify({"error": f"Concatenation failed: {str(e)}"}), 500