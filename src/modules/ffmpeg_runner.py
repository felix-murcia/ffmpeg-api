"""
Módulo de ejecución de FFmpeg con cálculo de progreso
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


def run_ffmpeg(process_id, cmd):
    """Ejecuta FFmpeg en segundo plano y calcula progreso"""
    process_manager = get_process_manager()
    
    # Función local para actualizar estado
    def save_status(status, **kwargs):
        try:
            process = process_manager.get(process_id)
            if process:
                process["status"] = status
                for key, value in kwargs.items():
                    process[key] = value
                # Guardar en archivo para persistencia
                status_file = f"/tmp/ffmpeg_status_{process_id}.json"
                with open(status_file, 'w') as f:
                    json.dump(dict(process), f)
                logger.info(f"[{process_id}] 💾 Guardado estado: {status}, progress: {kwargs.get('progress', 'N/A')}")
            else:
                # Si no existe en processes, crear entrada básica y guardar
                basic_info = {"status": status, **kwargs}
                status_file = f"/tmp/ffmpeg_status_{process_id}.json"
                with open(status_file, 'w') as f:
                    json.dump(basic_info, f)
                logger.warning(f"[{process_id}] ⚠️ Proceso no estaba en memoria, guardado básico: {status}")
        except Exception as e:
            logger.error(f"[{process_id}] ❌  Error guardando estado: {e}")
    
    logger.info(f"[{process_id}] 🚀 Iniciando run_ffmpeg")
    
    # Cargar process_info del archivo o de memoria
    process_info = process_manager.get(process_id)
    if not process_info:
        # Intentar leer del archivo
        process_info = process_manager.get_from_file(process_id)
    
    if not process_info:
        logger.error(f"[{process_id}] ❌  No se pudo obtener process_info")
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
        # Código de copia existente...
        # (mantén tu código de copia actual aquí)
    
    # Segundo: ejecutar FFmpeg
    logger.info(f"[{process_id}] 🚀 Iniciando FFmpeg")
    
    try:
        # Usar PIPE separados para stdout y stderr
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1
        )
        
        process_info["pid"] = proc.pid
        process_info["log_file"] = f"/tmp/ffmpeg_{process_id}.log"
        
        save_status("running", pid=proc.pid, start_time=time.time())
        logger.info(f"[{process_id}] 🔴 ESTADO CAMBIADO A RUNNING - PID: {proc.pid}")
        
        # Guardar en archivo de log
        with open(process_info["log_file"], 'w') as log_f:
            # Leer stdout y stderr en hilos separados
            stdout_lines = []
            stderr_lines = []
            
            def read_output(pipe, is_stderr=False):
                for line in iter(pipe.readline, ''):
                    line = line.strip()
                    if is_stderr:
                        stderr_lines.append(line)
                    else:
                        stdout_lines.append(line)
                    log_f.write(line + "\n")
                    log_f.flush()
                    
                    # Guardar últimas líneas
                    if "logs" not in process_info:
                        process_info["logs"] = []
                    process_info["logs"].append(line)
                    if len(process_info["logs"]) > 100:
                        process_info["logs"] = process_info["logs"][-100:]
                    
                    # Calcular progreso
                    if total_duration and "time=" in line:
                        try:
                            time_match = re.search(r'time=(\d{2}):(\d{2}):(\d{2})\.(\d{2})', line)
                            if time_match:
                                hours = int(time_match.group(1))
                                minutes = int(time_match.group(2))
                                seconds = int(time_match.group(3))
                                current_seconds = hours * 3600 + minutes * 60 + seconds
                                progress = (current_seconds / total_duration) * 100
                                process_info["progress"] = min(100, progress)
                                if int(progress) % 5 == 0:
                                    save_status("running", progress=process_info["progress"])
                        except Exception as e:
                            pass
            
            # Crear hilos para leer stdout y stderr
            stdout_thread = threading.Thread(target=read_output, args=(proc.stdout, False))
            stderr_thread = threading.Thread(target=read_output, args=(proc.stderr, True))
            stdout_thread.daemon = True
            stderr_thread.daemon = True
            stdout_thread.start()
            stderr_thread.start()
            
            # Esperar a que termine
            return_code = proc.wait()
            stdout_thread.join(timeout=1)
            stderr_thread.join(timeout=1)
            
            if return_code == 0:
                save_status("completed", progress=100, end_time=time.time())
                logger.info(f"[{process_id}] ✅  Optimización completada")
            else:
                # Capturar el error específico
                error_msg = f"FFmpeg exited with code {return_code}"
                if stderr_lines:
                    error_msg = f"FFmpeg error: {' '.join(stderr_lines[-5:])}"
                save_status("error", error=error_msg)
                logger.error(f"[{process_id}] ❌  Error en FFmpeg: {error_msg}")
                
    except Exception as e:
        save_status("error", error=str(e))
        logger.error(f"[{process_id}] ❌  Excepción: {e}")