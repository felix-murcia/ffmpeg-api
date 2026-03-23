"""
Módulo de gestión de procesos y almacenamiento en memoria
"""
import json
import logging
import os
from multiprocessing import Manager

logger = logging.getLogger("ffmpeg-api")


class ProcessManager:
    """Gestor de procesos activos con almacenamiento en memoria y archivos"""
    
    def __init__(self):
        self._manager = Manager()
        self._processes = self._manager.dict()
    
    @property
    def processes(self):
        """Acceso al diccionario de procesos"""
        return self._processes
    
    def get(self, process_id):
        """Obtiene un proceso por su ID"""
        return self._processes.get(process_id)
    
    def set(self, process_id, data):
        """Establece los datos de un proceso"""
        self._processes[process_id] = self._manager.dict(data)
    
    def update(self, process_id, status, **kwargs):
        """Actualiza el estado del proceso"""
        if process_id in self._processes:
            self._processes[process_id]["status"] = status
            for key, value in kwargs.items():
                self._processes[process_id][key] = value
            # Guardar en archivo para visibilidad entre procesos
            try:
                status_file = f"/tmp/ffmpeg_status_{process_id}.json"
                with open(status_file, 'w') as f:
                    json.dump(dict(self._processes[process_id]), f)
            except Exception as e:
                logger.error(f"[update_process_status] Error guardando archivo: {e}")
    
    def get_from_file(self, process_id):
        """Obtiene el proceso desde el archivo si no está en memoria"""
        status_file = f"/tmp/ffmpeg_status_{process_id}.json"
        if os.path.exists(status_file):
            try:
                with open(status_file, 'r') as f:
                    process = json.load(f)
                    # Actualizar memoria
                    try:
                        self._processes[process_id] = self._manager.dict(process)
                    except:
                        pass
                return process
            except Exception as e:
                logger.error(f"[{process_id}] Error leyendo archivo de estado: {e}")
        return None
    
    def save_to_file(self, process_id, data=None):
        """Guarda el estado del proceso en archivo"""
        try:
            status_file = f"/tmp/ffmpeg_status_{process_id}.json"
            if data is None:
                data = dict(self._processes.get(process_id, {}))
            with open(status_file, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            logger.error(f"[{process_id}] Error guardando estado: {e}")
    
    def list_active(self):
        """Lista los procesos activos"""
        active = []
        for pid, p in self._processes.items():
            status = p.get("status", "unknown")
            if status in ["starting", "running", "copying"]:
                active.append({
                    "id": pid,
                    "status": status,
                    "progress": p.get("progress", 0)
                })
        return active


# Instancia global del gestor de procesos
_process_manager = None


def get_process_manager():
    """Obtiene la instancia global del gestor de procesos"""
    global _process_manager
    if _process_manager is None:
        _process_manager = ProcessManager()
    return _process_manager