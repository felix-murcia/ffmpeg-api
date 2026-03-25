"""
Módulo de ejecución de FFmpeg con cálculo de progreso y fallback
Versión definitiva: usa -map 0 para incluir todos los streams
"""
import json
import logging
import os
import re
import subprocess
import threading
import time
from .process_manager import get_process_manager

logger = logging.getLogger("ffmpeg-api")

def get_audio_tracks(input_path):
    """
    Detecta pistas de audio y devuelve el índice de la pista en español.
    """
    try:
        cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', input_path]
        result = subprocess.check_output(cmd, text=True)
        data = json.loads(result)
        
        first_audio = None
        spanish_audio = None
        
        for i, stream in enumerate(data['streams']):
            if stream['codec_type'] == 'audio':
                tags = stream.get('tags', {})
                title = tags.get('title', '')
                language = tags.get('language', '')
                
                logger.info(f"🎵 Stream {i}: audio, title='{title}', language='{language}'")
                
                if first_audio is None:
                    first_audio = i
                
                if title == 'Español' or language == 'spa':
                    spanish_audio = i
                    logger.info(f"🎵 ✅ Español encontrado en stream {i}")
                    break
        
        selected_index = spanish_audio if spanish_audio is not None else (first_audio if first_audio is not None else 0)
        reason = "español" if spanish_audio is not None else ("primera pista" if first_audio is not None else "fallback")
        
        logger.info(f"🎵 📌 Seleccionado audio índice {selected_index} ({reason})")
        
        return {
            'selected_track_index': selected_index,
            'selected_reason': reason
        }
        
    except Exception as e:
        logger.error(f"❌ Error analizando audio: {e}")
        return {'selected_track_index': 0, 'selected_reason': 'error'}

def build_ffmpeg_command(input_path, output_path, gpu_config, audio_strategy='aac'):
    """
    Construye el comando FFmpeg SIN subtítulos para evitar problemas
    """
    logger.info(f"🎵 Construyendo comando con estrategia de audio: {audio_strategy}")
    
    cmd = [
        "ffmpeg",
        "-hwaccel", "cuda",
        "-i", input_path,
        "-map", "0:v:0",                    # Solo el primer video
        "-map", "0:a?",                     # Todos los audios
        "-sn",                              # SIN subtítulos (evita problemas)
        "-c:v", "h264_nvenc",
        "-preset", gpu_config["preset"],
        "-rc", "vbr",
        "-tune", "hq",
    ]
    
    # Parámetros de video
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
    
    if gpu_config.get("include_level", False):
        cmd.extend(["-level", gpu_config["level"]])
    
    cmd.extend([
        "-pix_fmt", "yuv420p",
        "-g", "120",
    ])
    
    # Configuración de audio según estrategia
    if audio_strategy == 'aac':
        cmd.extend(["-c:a", "aac", "-b:a", "128k", "-ac", "2", "-ar", "48000"])
    elif audio_strategy == 'aac_low':
        cmd.extend(["-c:a", "aac", "-b:a", "96k", "-ac", "2", "-ar", "44100"])
    elif audio_strategy == 'copy':
        cmd.extend(["-c:a", "copy"])
    elif audio_strategy == 'mp3':
        cmd.extend(["-c:a", "libmp3lame", "-b:a", "192k", "-ar", "48000", "-ac", "2"])
    else:
        cmd.extend(["-c:a", "aac", "-b:a", "128k", "-ac", "2", "-ar", "48000"])
    
    # Subtítulos: copiar sin modificar
    cmd.extend([
        "-c:s", "copy",
        "-f", "matroska",
        "-y",
        output_path
    ])
    
    return cmd

def run_ffmpeg(process_id, cmd):
    """Ejecuta FFmpeg con fallback automático entre estrategias de audio"""
    process_manager = get_process_manager()
    
    def save_status(status, **kwargs):
        try:
            process = process_manager.get(process_id)
            if process:
                process["status"] = status
                for key, value in kwargs.items():
                    process[key] = value
                with open(f"/tmp/ffmpeg_status_{process_id}.json", 'w') as f:
                    json.dump(dict(process), f)
                logger.info(f"[{process_id}] 💾 Estado: {status}")
            else:
                basic_info = {"status": status, **kwargs}
                with open(f"/tmp/ffmpeg_status_{process_id}.json", 'w') as f:
                    json.dump(basic_info, f)
        except Exception as e:
            logger.error(f"[{process_id}] ❌ Error guardando: {e}")
    
    logger.info(f"[{process_id}] 🚀 Iniciando optimización")
    
    process_info = process_manager.get(process_id)
    if not process_info:
        process_info = process_manager.get_from_file(process_id)
    
    if not process_info:
        logger.error(f"[{process_id}] ❌ No se pudo obtener process_info")
        return
    
    total_duration = process_info.get("total_duration")
    input_path = process_info.get("input", "")
    output_path = process_info.get("output", "")
    
    # Obtener duración si no está
    if not total_duration:
        try:
            duration_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                           "-of", "default=noprint_wrappers=1:nokey=1", input_path]
            result = subprocess.run(duration_cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and result.stdout.strip():
                total_duration = float(result.stdout.strip())
                process_info["total_duration"] = total_duration
                logger.info(f"[{process_id}] ⏱️ Duración: {total_duration:.2f}s")
        except Exception as e:
            logger.warning(f"[{process_id}] ⚠️ No se pudo obtener duración: {e}")
    
    # Configuración GPU
    from .gpu import get_gpu_preset_and_level
    gpu_config = get_gpu_preset_and_level()
    
    # Estrategias en orden
    strategies = [
        ('aac', 'AAC estándar'),
        ('aac_low', 'AAC baja calidad'),
        ('copy', 'Copiar audio original'),
        ('mp3', 'MP3 fallback')
    ]
    
    for strategy, strategy_name in strategies:
        logger.info(f"[{process_id}] 🔄 Probando: {strategy_name}")
        
        new_cmd = build_ffmpeg_command(input_path, output_path, gpu_config, strategy)
        logger.info(f"[{process_id}] 🎬 Comando: {' '.join(new_cmd)}")
        save_status("running", progress=0)
        
        try:
            proc = subprocess.Popen(
                new_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1
            )
            
            process_info["pid"] = proc.pid
            stderr_lines = []
            
            def read_stderr():
                for line in iter(proc.stderr.readline, ''):
                    line = line.strip()
                    if line:
                        stderr_lines.append(line)
                        if "logs" not in process_info:
                            process_info["logs"] = []
                        process_info["logs"].append(line)
                        if len(process_info["logs"]) > 100:
                            process_info["logs"] = process_info["logs"][-100:]
                        
                        # Calcular progreso
                        if total_duration and "time=" in line:
                            try:
                                match = re.search(r'time=(\d{2}):(\d{2}):(\d{2})\.', line)
                                if match:
                                    h, m, s = int(match.group(1)), int(match.group(2)), int(match.group(3))
                                    current = h * 3600 + m * 60 + s
                                    progress = (current / total_duration) * 100
                                    process_info["progress"] = min(100, progress)
                            except:
                                pass
            
            stderr_thread = threading.Thread(target=read_stderr)
            stderr_thread.daemon = True
            stderr_thread.start()
            
            return_code = proc.wait()
            stderr_thread.join(timeout=2)
            
            if return_code == 0:
                save_status("completed", progress=100)
                logger.info(f"[{process_id}] ✅ Éxito con {strategy_name}")
                return
            else:
                error_msg = f"FFmpeg error: {' '.join(stderr_lines[-5:])}" if stderr_lines else f"Código {return_code}"
                logger.warning(f"[{process_id}] ⚠️ {error_msg}")
                
        except Exception as e:
            logger.error(f"[{process_id}] ❌ Excepción: {e}")
            continue
    
    save_status("error", error="Todas las estrategias fallaron")
    logger.error(f"[{process_id}] ❌ Falló")