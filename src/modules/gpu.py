"""
Módulo de detección de GPU y configuración de presets
"""
import subprocess
import logging

logger = logging.getLogger("ffmpeg-api")


def get_gpu_preset_and_level():
    """Detectar GPU y devolver preset y configuración adecuada"""
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
            
            # GPUs Maxwell (9xxM) - NO incluir level, preset p4
            if any(model in gpu_name for model in ["960M", "950M", "860M", "GTX 9"]):
                logger.info("🔧 GPU Maxwell detectada - preset p4, sin level")
                return {
                    "preset": "p4",
                    "include_level": False,
                    "multipass": "none",
                    "lookahead": "16"
                }
            # GPUs Pascal (10xx) - incluir level 4.1, preset p6
            elif any(model in gpu_name for model in ["1050", "1060", "1070", "1080", "GTX 10"]):
                logger.info("🔧 GPU Pascal detectada - preset p6, level 4.1")
                return {
                    "preset": "p6",
                    "include_level": True,
                    "level": "4.1",
                    "multipass": "fullres",
                    "lookahead": "32"
                }
            # GPUs Turing/Ampere (20xx, 30xx, 40xx) - preset p7, level 4.1
            else:
                logger.info("🔧 GPU moderna detectada - preset p7, level 4.1")
                return {
                    "preset": "p7",
                    "include_level": True,
                    "level": "4.1",
                    "multipass": "fullres",
                    "lookahead": "32"
                }
        else:
            logger.warning("⚠️ No se detectó GPU NVIDIA - usando valores seguros")
            return {
                "preset": "p4",
                "include_level": False,
                "multipass": "none",
                "lookahead": "16"
            }
    except Exception as e:
        logger.error(f"❌  Error detectando GPU: {e}")
        return {
            "preset": "p4",
            "include_level": False,
            "multipass": "none",
            "lookahead": "16"
        }