"""
Módulo de configuración de la aplicación Flask
"""

import os
import logging
from flask import Flask
from flask_cors import CORS


def create_app():
    """Crea y configura la aplicación Flask"""
    app = Flask(__name__)
    CORS(app)

    # Configurar logger con zona horaria local
    logger = logging.getLogger("ffmpeg-api")
    logger.setLevel(logging.INFO)

    # Evitar duplicar handlers si ya existe
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return app


# Instancia global de la aplicación (para uso en otros módulos)
_app_instance = None


def init_app():
    """Inicializa la aplicación global"""
    global _app_instance
    _app_instance = create_app()
    return _app_instance


def get_app():
    """Obtiene la instancia de la aplicación"""
    global _app_instance
    if _app_instance is None:
        _app_instance = init_app()
    return _app_instance


def get_logger():
    """Obtiene el logger de la aplicación"""
    return logging.getLogger("ffmpeg-api")


# Timeout configurations loaded from environment variables
class TimeoutConfig:
    """Centralized timeout configuration for all FFmpeg operations"""

    AUDIO_QUALITY_ANALYSIS_TIMEOUT = int(os.getenv('AUDIO_QUALITY_ANALYSIS_TIMEOUT', 100))
    AUDIO_STREAM_DETECTION_TIMEOUT = int(os.getenv('AUDIO_STREAM_DETECTION_TIMEOUT', 60))
    VIDEO_CREATION_TIMEOUT = int(os.getenv('VIDEO_CREATION_TIMEOUT', 300))
    AUDIO_CLEANING_TIMEOUT = int(os.getenv('AUDIO_CLEANING_TIMEOUT', 300))
    AUDIO_PROCESSING_TIMEOUT = int(os.getenv('AUDIO_PROCESSING_TIMEOUT', 300))
    AUDIO_CONCATENATION_TIMEOUT = int(os.getenv('AUDIO_CONCATENATION_TIMEOUT', 300))
    GPU_DETECTION_TIMEOUT = int(os.getenv('GPU_DETECTION_TIMEOUT', 5))
    DURATION_PROBE_TIMEOUT = int(os.getenv('DURATION_PROBE_TIMEOUT', 10))
    THREAD_JOIN_TIMEOUT = int(os.getenv('THREAD_JOIN_TIMEOUT', 2))
