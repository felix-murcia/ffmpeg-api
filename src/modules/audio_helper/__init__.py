"""
Audio helper modules - SOLID refactored audio processing services.
"""

from .file_handler import FileHandler
from .ffmpeg_executor import FFmpegExecutor
from .audio_info_service import AudioInfoService
from .audio_converter import AudioConverter
from .audio_cleaner import AudioCleaner
from .audio_validator import AudioValidator
from .audio_stream_detector import AudioStreamDetector
from .exceptions import (
    AudioProcessingError,
    AudioValidationError,
    AudioConversionError,
    AudioInfoError,
    AudioCleanError,
    FileNotFoundError,
)

__all__ = [
    "FileHandler",
    "FFmpegExecutor",
    "AudioInfoService",
    "AudioConverter",
    "AudioCleaner",
    "AudioValidator",
    "AudioStreamDetector",
    "AudioProcessingError",
    "AudioValidationError",
    "AudioConversionError",
    "AudioInfoError",
    "AudioCleanError",
    "FileNotFoundError",
]
