#!/usr/bin/env python3
"""
FFmpeg API Service - Ejecuta FFmpeg con GPU y expone endpoints REST
Refactorizado en módulos por funcionalidad
"""
import logging
from src.modules import (
    create_app,
    register_video_routes,
    register_audio_routes,
    get_logger
)

# Inicializar la aplicación
app = create_app()
logger = get_logger()

# Registrar las rutas
register_video_routes(app)
register_audio_routes(app)

if __name__ == '__main__':
    logger.info("🚀 Iniciando FFmpeg API en puerto 8080")
    app.run(host='0.0.0.0', port=8080, debug=False)
