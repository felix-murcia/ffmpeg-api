"""
Audio info service - extracts metadata from audio files.
"""

import json
from typing import Dict, Any, Optional, Tuple
from .base import AudioService
from .exceptions import AudioInfoError
from .ffmpeg_executor import FFmpegExecutor
from .file_handler import FileHandler


class AudioInfoService(AudioService):
    """Service for extracting audio metadata using FFprobe."""

    def __init__(self, ffmpeg_executor: FFmpegExecutor, file_handler: FileHandler):
        self.ffmpeg_executor = ffmpeg_executor
        self.file_handler = file_handler

    def get_audio_info(self, file_path: str) -> Dict[str, Any]:
        """
        Extract audio metadata from file.

        Args:
            file_path: Path to audio file

        Returns:
            Dictionary with audio metadata (duration, codec, sample_rate, channels)

        Raises:
            AudioInfoError: If ffprobe fails or file is invalid
        """
        if not self.file_handler.exists(file_path):
            raise AudioInfoError(f"File not found: {file_path}")

        cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            file_path,
        ]

        try:
            _, stdout, _ = self.ffmpeg_executor.run_ffprobe(cmd)
            info = json.loads(stdout)
        except Exception as e:
            raise AudioInfoError(f"FFprobe error: {str(e)}") from e

        # Extract audio stream
        audio_stream = next(
            (s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None
        )

        duration = float(info.get("format", {}).get("duration", 0))

        result = {
            "duration": duration,
            "codec": audio_stream.get("codec_name") if audio_stream else None,
            "sample_rate": audio_stream.get("sample_rate") if audio_stream else None,
            "channels": audio_stream.get("channels") if audio_stream else None,
        }

        return result

    def process(self, file_path: str) -> Dict[str, Any]:
        """Alias for get_audio_info to satisfy AudioService interface."""
        return self.get_audio_info(file_path)
