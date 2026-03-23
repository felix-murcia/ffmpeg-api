"""
Módulo de configuración de la aplicación Flask
"""
import logging
from flask import Flask
from flask_cors import CORS


def create_app():
    """Crea y configura la aplicación Flask"""
    app = Flask(__name__)
    CORS(app)
    
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("ffmpeg-api")
    
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