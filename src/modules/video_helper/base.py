"""
Abstract base classes for video processing.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Tuple


class VideoService(ABC):
    """Abstract base class for all video services."""

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

    @abstractmethod
    def copy_file(self, source_path: str, temp_id: str) -> str:
        """Copy a file to temporary location."""
        pass

    @abstractmethod
    def exists(self, path: str) -> bool:
        """Check if file exists."""
        pass

    @abstractmethod
    def get_size(self, path: str) -> int:
        """Get file size in bytes."""
        pass


class FFmpegExecutor(ABC):
    """Abstract base class for FFmpeg/FFprobe execution."""

    @abstractmethod
    def run_ffmpeg(
        self, cmd: list, timeout: Optional[int] = None, check: bool = True
    ) -> Tuple[int, str, str]:
        """Run ffmpeg command and return exit code, stdout, stderr."""
        pass

    @abstractmethod
    def run_ffprobe(
        self, cmd: list, timeout: Optional[int] = None
    ) -> Tuple[int, str, str]:
        """Run ffprobe command and return exit code, stdout, stderr."""
        pass
