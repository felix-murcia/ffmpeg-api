"""
Módulo de rutas de audio
"""

import json
import logging
import os
import re
import shutil
import subprocess
import uuid
from flask import jsonify, request, Response

logger = logging.getLogger("ffmpeg-api")

from .utils import format_duration


def register_audio_routes(app):
    """Registra las rutas de audio en la aplicación"""

    @app.route("/audio/info", methods=["POST"])
    def audio_info():
        """Devuelve metadata del audio usando ffprobe."""
        if "file" not in request.files:
            return jsonify({"error": "No se envió ningún archivo"}), 400

        file = request.files["file"]
        temp_id = str(uuid.uuid4())
        input_path = f"/tmp/audio_info_{temp_id}"

        file.save(input_path)

        cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            input_path,
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            info = json.loads(result.stdout)
        except Exception as e:
            return jsonify({"error": "ffprobe error", "details": str(e)}), 500
        finally:
            os.remove(input_path)

        duration = float(info["format"].get("duration", 0))
        stream = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)

        return jsonify(
            {
                "duration": duration,
                "codec": stream.get("codec_name") if stream else None,
                "sample_rate": stream.get("sample_rate") if stream else None,
                "channels": stream.get("channels") if stream else None,
            }
        )

    @app.route("/audio/convert", methods=["POST"])
    def convert_audio():
        """Convierte un archivo de audio a WAV 16kHz mono o MP3."""
        if "file" not in request.files:
            return jsonify({"error": "No se envió ningún archivo"}), 400

        fmt = request.form.get("format", "wav")  # wav o mp3

        file = request.files["file"]
        temp_id = str(uuid.uuid4())
        input_path = f"/tmp/audio_input_{temp_id}"
        output_path = f"/tmp/audio_output_{temp_id}.{fmt}"

        file.save(input_path)

        if fmt == "wav":
            cmd = [
                "ffmpeg",
                "-i",
                input_path,
                "-ac",
                "1",
                "-ar",
                "16000",
                "-f",
                "wav",
                "-y",
                output_path,
            ]
        elif fmt == "mp3":
            cmd = [
                "ffmpeg",
                "-i",
                input_path,
                "-vn",
                "-acodec",
                "libmp3lame",
                "-b:a",
                "192k",
                "-y",
                output_path,
            ]
        else:
            return jsonify({"error": "Formato no soportado"}), 400

        try:
            subprocess.run(
                cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
        except subprocess.CalledProcessError as e:
            return jsonify({"error": "FFmpeg error", "details": e.stderr.decode()}), 500

        with open(output_path, "rb") as f:
            data = f.read()

        os.remove(input_path)
        os.remove(output_path)

        return (
            data,
            200,
            {
                "Content-Type": f"audio/{fmt}",
                "Content-Disposition": f"attachment; filename=converted.{fmt}",
            },
        )

    @app.route("/audio/clean", methods=["POST"])
    def clean_audio():
        """Limpia un archivo de audio: normaliza volumen y convierte a formato estándar."""
        if "file" not in request.files:
            return jsonify({"error": "No se envió ningún archivo"}), 400

        file = request.files["file"]
        temp_id = str(uuid.uuid4())

        input_path = f"/tmp/audio_clean_input_{temp_id}"
        output_path = f"/tmp/audio_clean_output_{temp_id}.wav"

        file.save(input_path)

        logger.info(f"[CLEAN] Procesando: {input_path}")
        logger.info(f"[CLEAN] Tamaño original: {os.path.getsize(input_path)} bytes")

        # Filtros simplificados - solo conversión básica
        # Sin reducción de ruido, sin silenceremove
        cmd = [
            "ffmpeg",
            "-i",
            input_path,
            "-ac",
            "1",
            "-ar",
            "16000",
            "-y",
            output_path,
        ]

        logger.info(f"[CLEAN] Comando: {' '.join(cmd)}")

        try:
            # Usar timeout para evitar que se cuelgue
            result = subprocess.run(cmd, timeout=60, capture_output=True, text=True)

            if result.returncode != 0:
                logger.error(f"[CLEAN] Error en FFmpeg: {result.stderr}")
                # Si falla, devolver el original
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

        except subprocess.TimeoutExpired:
            logger.error(f"[CLEAN] Timeout después de 60 segundos")
            # Si timeout, devolver original
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
        except Exception as e:
            logger.error(f"[CLEAN] Error: {e}")
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

        if not os.path.exists(output_path):
            logger.error(f"[CLEAN] Archivo de salida no creado")
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

        with open(output_path, "rb") as f:
            data = f.read()

        logger.info(f"[CLEAN] Tamaño de salida: {len(data)} bytes")

        # Limpiar archivos temporales
        try:
            os.remove(input_path)
            os.remove(output_path)
        except:
            pass

        return (
            data,
            200,
            {
                "Content-Type": "audio/wav",
                "Content-Disposition": "attachment; filename=cleaned.wav",
            },
        )

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
        input_path = f"/tmp/audio_validate_{temp_id}"

        file.save(input_path)

        try:
            # 1. Obtener información básica con ffprobe
            probe_cmd = [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                input_path,
            ]

            probe_result = subprocess.run(
                probe_cmd, capture_output=True, text=True, check=True
            )
            info = json.loads(probe_result.stdout)

            # Extraer datos del audio
            audio_stream = None
            for stream in info.get("streams", []):
                if stream.get("codec_type") == "audio":
                    audio_stream = stream
                    break

            if not audio_stream:
                return jsonify(
                    {
                        "valid": False,
                        "error": "No se encontró stream de audio en el archivo",
                    }
                ), 400

            duration = float(info["format"].get("duration", 0))
            codec = audio_stream.get("codec_name", "unknown")
            sample_rate = int(audio_stream.get("sample_rate", 0))
            channels = audio_stream.get("channels", 0)
            bitrate = (
                int(audio_stream.get("bit_rate", 0))
                if audio_stream.get("bit_rate")
                else 0
            )

            # 2. Validaciones básicas
            issues = []
            warnings = []

            # Verificar duración
            if duration < 1:
                issues.append("El audio es demasiado corto (menos de 1 segundo)")
            elif duration > 3600:  # 1 hora
                warnings.append(
                    "El audio es muy largo (> 1 hora), puede tardar mucho en transcribirse"
                )
            elif duration > 7200:  # 2 horas
                issues.append(
                    "El audio es demasiado largo (> 2 horas) para transcripción"
                )

            # Verificar sample rate
            if sample_rate < 8000:
                issues.append(
                    f"Frecuencia de muestreo demasiado baja ({sample_rate} Hz). Mínimo 8000 Hz"
                )
            elif sample_rate < 16000:
                warnings.append(
                    f"Frecuencia de muestreo baja ({sample_rate} Hz). Se recomienda 16000 Hz o más"
                )

            # Verificar canales
            if channels == 0:
                issues.append("No se detectaron canales de audio")
            elif channels > 2:
                warnings.append(
                    f"Audio con {channels} canales. Se convertirá a mono para transcripción"
                )

            # Verificar bitrate (si está disponible)
            if bitrate > 0 and bitrate < 32000:
                warnings.append(
                    f"Bitrate bajo ({bitrate // 1000} kbps). La calidad podría ser insuficiente"
                )

            # 3. Analizar calidad con ffmpeg (detectar silencio y ruido)
            quality_check_cmd = [
                "ffmpeg",
                "-i",
                input_path,
                "-af",
                "volumedetect,silencedetect=noise=-30dB:d=0.5",
                "-f",
                "null",
                "-",
            ]

            quality_result = subprocess.run(
                quality_check_cmd, capture_output=True, text=True, timeout=30
            )

            # Analizar salida de volumedetect
            mean_volume = None
            max_volume = None
            silence_detected = False
            silence_duration = 0

            for line in quality_result.stderr.split("\n"):
                if "mean_volume" in line:
                    match = re.search(r"mean_volume:\s*(-?\d+\.?\d*)\s*dB", line)
                    if match:
                        mean_volume = float(match.group(1))
                elif "max_volume" in line:
                    match = re.search(r"max_volume:\s*(-?\d+\.?\d*)\s*dB", line)
                    if match:
                        max_volume = float(match.group(1))
                elif "silence_start" in line:
                    silence_detected = True
                    match = re.search(r"silence_duration:\s*(\d+\.?\d*)", line)
                    if match:
                        silence_duration += float(match.group(1))

            # Verificar volumen
            if mean_volume is not None:
                if mean_volume < -30:
                    issues.append(
                        f"Volumen muy bajo ({mean_volume:.1f} dB). El audio apenas se escucha"
                    )
                elif mean_volume < -20:
                    warnings.append(
                        f"Volumen bajo ({mean_volume:.1f} dB). Puede afectar la transcripción"
                    )
                elif mean_volume > -5:
                    warnings.append(
                        f"Volumen muy alto ({mean_volume:.1f} dB). Puede haber distorsión"
                    )

            # Verificar silencios excesivos
            if silence_detected and silence_duration > (duration * 0.5):
                issues.append(
                    f"Demasiado silencio en el audio ({silence_duration:.1f}s de {duration:.1f}s)"
                )
            elif silence_detected and silence_duration > (duration * 0.3):
                warnings.append(
                    f"Mucho silencio en el audio ({silence_duration:.1f}s de {duration:.1f}s)"
                )

            # 4. Detectar si hay voz (usando silencedetect inverso)
            has_voice = True
            if silence_duration > (duration * 0.9):
                has_voice = False
                issues.append("El audio parece no contener voz (demasiado silencio)")

            # 5. Recomendaciones de formato
            recommendations = []
            if codec not in ["mp3", "wav", "opus", "aac", "flac"]:
                recommendations.append(
                    f"El códec {codec} puede no ser óptimo. Se recomienda convertir a WAV o MP3"
                )

            if sample_rate != 16000:
                recommendations.append(
                    "Se recomienda convertir a 16kHz para mejor rendimiento de transcripción"
                )

            if channels != 1:
                recommendations.append(
                    "Se recomienda convertir a mono para transcripción"
                )

            # Determinar si el audio es apto
            is_valid = len(issues) == 0
            is_optimal = is_valid and len(warnings) == 0

            return jsonify(
                {
                    "valid": is_valid,
                    "optimal": is_optimal,
                    "issues": issues,
                    "warnings": warnings,
                    "recommendations": recommendations,
                    "metadata": {
                        "duration_seconds": duration,
                        "duration_formatted": format_duration(duration),
                        "codec": codec,
                        "sample_rate_hz": sample_rate,
                        "channels": channels,
                        "bitrate_kbps": bitrate // 1000 if bitrate > 0 else None,
                        "mean_volume_db": mean_volume,
                        "max_volume_db": max_volume,
                        "silence_duration_seconds": silence_duration,
                        "silence_percentage": round(
                            (silence_duration / duration) * 100, 1
                        )
                        if duration > 0
                        else 0,
                        "has_voice": has_voice,
                    },
                    "suggested_conversion": {
                        "needs_conversion": not is_optimal,
                        "target_format": "wav",
                        "target_sample_rate": 16000,
                        "target_channels": 1,
                        "command": "ffmpeg -i input.wav -ac 1 -ar 16000 output.wav"
                        if not is_optimal
                        else None,
                    },
                }
            )

        except subprocess.CalledProcessError as e:
            logger.error(f"Error en ffprobe/ffmpeg: {e.stderr}")
            return jsonify(
                {
                    "valid": False,
                    "error": "Error analizando el audio",
                    "details": e.stderr.decode() if e.stderr else str(e),
                }
            ), 500
        except Exception as e:
            logger.error(f"Error validando audio: {e}")
            return jsonify(
                {
                    "valid": False,
                    "error": "Error interno al validar el audio",
                    "details": str(e),
                }
            ), 500
        finally:
            # Limpiar archivo temporal
            if os.path.exists(input_path):
                os.remove(input_path)

    @app.route("/audio/validate-by-path", methods=["POST"])
    def validate_audio_by_path():
        """Valida un audio por su ruta en el sistema de archivos."""
        data = request.json
        file_path = data.get("path")

        if not file_path:
            return jsonify({"error": "Se requiere la ruta del archivo"}), 400

        if not os.path.exists(file_path):
            return jsonify({"error": f"Archivo no encontrado: {file_path}"}), 404

        # Simular una petición con el archivo
        with open(file_path, "rb") as f:
            # Crear un objeto similar a request.files
            from werkzeug.datastructures import FileStorage

            file_obj = FileStorage(
                stream=f,
                filename=os.path.basename(file_path),
                content_type="audio/mpeg",
            )

            # Crear una copia para procesar
            temp_id = str(uuid.uuid4())
            temp_path = f"/tmp/audio_validate_{temp_id}"

            shutil.copy2(file_path, temp_path)

            # Procesar usando la lógica de validate_audio_from_path
            try:
                return validate_audio_from_path_impl(temp_path)
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

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
            "-i",
            input_path,
            "-vn",
            "-acodec",
            "libmp3lame",
            "-b:a",
            "192k",
            "-y",
            output_path,
        ]

        try:
            subprocess.run(cmd, check=True, capture_output=True)
            os.remove(input_path)
            return jsonify({"output": output_path}), 200
        except subprocess.CalledProcessError as e:
            return jsonify({"error": e.stderr.decode()}), 500


def validate_audio_from_path_impl(file_path):
    """Valida un audio desde su ruta (implementación interna)"""
    if not os.path.exists(file_path):
        return jsonify({"error": f"Archivo no encontrado: {file_path}"}), 404

    input_path = file_path

    try:
        # 1. Obtener información básica con ffprobe
        probe_cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            input_path,
        ]

        probe_result = subprocess.run(
            probe_cmd, capture_output=True, text=True, check=True
        )
        info = json.loads(probe_result.stdout)

        # Extraer datos del audio
        audio_stream = None
        for stream in info.get("streams", []):
            if stream.get("codec_type") == "audio":
                audio_stream = stream
                break

        if not audio_stream:
            return jsonify(
                {
                    "valid": False,
                    "error": "No se encontró stream de audio en el archivo",
                }
            ), 400

        duration = float(info["format"].get("duration", 0))
        codec = audio_stream.get("codec_name", "unknown")
        sample_rate = int(audio_stream.get("sample_rate", 0))
        channels = audio_stream.get("channels", 0)
        bitrate = (
            int(audio_stream.get("bit_rate", 0)) if audio_stream.get("bit_rate") else 0
        )

        # 2. Validaciones básicas
        issues = []
        warnings = []

        if duration < 1:
            issues.append("El audio es demasiado corto (menos de 1 segundo)")
        elif duration > 3600:
            warnings.append(
                "El audio es muy largo (> 1 hora), puede tardar mucho en transcribirse"
            )
        elif duration > 7200:
            issues.append("El audio es demasiado largo (> 2 horas) para transcripción")

        if sample_rate < 8000:
            issues.append(
                f"Frecuencia de muestreo demasiado baja ({sample_rate} Hz). Mínimo 8000 Hz"
            )
        elif sample_rate < 16000:
            warnings.append(
                f"Frecuencia de muestreo baja ({sample_rate} Hz). Se recomienda 16000 Hz o más"
            )

        if channels == 0:
            issues.append("No se detectaron canales de audio")
        elif channels > 2:
            warnings.append(
                f"Audio con {channels} canales. Se convertirá a mono para transcripción"
            )

        if bitrate > 0 and bitrate < 32000:
            warnings.append(
                f"Bitrate bajo ({bitrate // 1000} kbps). La calidad podría ser insuficiente"
            )

        # 3. Analizar calidad
        quality_check_cmd = [
            "ffmpeg",
            "-i",
            input_path,
            "-af",
            "volumedetect,silencedetect=noise=-30dB:d=0.5",
            "-f",
            "null",
            "-",
        ]

        quality_result = subprocess.run(
            quality_check_cmd, capture_output=True, text=True, timeout=30
        )

        mean_volume = None
        max_volume = None
        silence_detected = False
        silence_duration = 0

        for line in quality_result.stderr.split("\n"):
            if "mean_volume" in line:
                match = re.search(r"mean_volume:\s*(-?\d+\.?\d*)\s*dB", line)
                if match:
                    mean_volume = float(match.group(1))
            elif "max_volume" in line:
                match = re.search(r"max_volume:\s*(-?\d+\.?\d*)\s*dB", line)
                if match:
                    max_volume = float(match.group(1))
            elif "silence_start" in line:
                silence_detected = True
                match = re.search(r"silence_duration:\s*(\d+\.?\d*)", line)
                if match:
                    silence_duration += float(match.group(1))

        if mean_volume is not None:
            if mean_volume < -30:
                issues.append(
                    f"Volumen muy bajo ({mean_volume:.1f} dB). El audio apenas se escucha"
                )
            elif mean_volume < -20:
                warnings.append(
                    f"Volumen bajo ({mean_volume:.1f} dB). Puede afectar la transcripción"
                )
            elif mean_volume > -5:
                warnings.append(
                    f"Volumen muy alto ({mean_volume:.1f} dB). Puede haber distorsión"
                )

        if silence_detected and silence_duration > (duration * 0.5):
            issues.append(
                f"Demasiado silencio en el audio ({silence_duration:.1f}s de {duration:.1f}s)"
            )
        elif silence_detected and silence_duration > (duration * 0.3):
            warnings.append(
                f"Mucho silencio en el audio ({silence_duration:.1f}s de {duration:.1f}s)"
            )

        has_voice = True
        if silence_duration > (duration * 0.9):
            has_voice = False
            issues.append("El audio parece no contener voz (demasiado silencio)")

        recommendations = []
        if codec not in ["mp3", "wav", "opus", "aac", "flac"]:
            recommendations.append(
                f"El códec {codec} puede no ser óptimo. Se recomienda convertir a WAV o MP3"
            )
        if sample_rate != 16000:
            recommendations.append(
                "Se recomienda convertir a 16kHz para mejor rendimiento de transcripción"
            )
        if channels != 1:
            recommendations.append("Se recomienda convertir a mono para transcripción")

        is_valid = len(issues) == 0
        is_optimal = is_valid and len(warnings) == 0

        return jsonify(
            {
                "valid": is_valid,
                "optimal": is_optimal,
                "issues": issues,
                "warnings": warnings,
                "recommendations": recommendations,
                "metadata": {
                    "duration_seconds": duration,
                    "duration_formatted": format_duration(duration),
                    "codec": codec,
                    "sample_rate_hz": sample_rate,
                    "channels": channels,
                    "bitrate_kbps": bitrate // 1000 if bitrate > 0 else None,
                    "mean_volume_db": mean_volume,
                    "max_volume_db": max_volume,
                    "silence_duration_seconds": silence_duration,
                    "silence_percentage": round((silence_duration / duration) * 100, 1)
                    if duration > 0
                    else 0,
                    "has_voice": has_voice,
                },
                "suggested_conversion": {
                    "needs_conversion": not is_optimal,
                    "target_format": "wav",
                    "target_sample_rate": 16000,
                    "target_channels": 1,
                    "command": "ffmpeg -i input.wav -ac 1 -ar 16000 output.wav"
                    if not is_optimal
                    else None,
                },
            }
        )

    except subprocess.CalledProcessError as e:
        logger.error(f"Error en ffprobe/ffmpeg: {e.stderr}")
        return jsonify(
            {
                "valid": False,
                "error": "Error analizando el audio",
                "details": e.stderr.decode() if e.stderr else str(e),
            }
        ), 500
    except Exception as e:
        logger.error(f"Error validando audio: {e}")
        return jsonify(
            {
                "valid": False,
                "error": "Error interno al validar el audio",
                "details": str(e),
            }
        ), 500
