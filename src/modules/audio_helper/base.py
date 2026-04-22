"""
Abstract base classes for audio processing.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Tuple


class AudioService(ABC):
    """Abstract base class for all audio services."""

    @abstractmethod
    def process(self, *args, **kwargs):
        """Main processing method."""
        pass


class FileHandler(ABC):
    """Abstract base class for file handling operations."""

    @abstractmethod
    def save_upload(self, file_storage, temp_id: str) -> str:
        """Save uploaded file to temporary location."""
        pass

    @abstractmethod
    def cleanup(self, *file_paths: str):
        """Remove temporary files."""
        pass

    @abstractmethod
    def generate_temp_path(self, temp_id: str, suffix: str = "") -> str:
        """Generate a temporary file path."""
        pass


class FFmpegExecutor(ABC):
    """Abstract base class for FFmpeg/FFprobe execution."""

    @abstractmethod
    def run_ffmpeg(
        self, cmd: list, timeout: Optional[int] = None
    ) -> Tuple[int, str, str]:
        """Run ffmpeg command and return exit code, stdout, stderr."""
        pass

    @abstractmethod
    def run_ffprobe(
        self, cmd: list, timeout: Optional[int] = None
    ) -> Tuple[int, str, str]:
        """Run ffprobe command and return exit code, stdout, stderr."""
        pass
