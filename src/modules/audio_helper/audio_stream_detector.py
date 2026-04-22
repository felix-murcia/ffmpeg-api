"""
Audio stream detector - checks if a video/audio file contains an audio stream.
"""

import os
from typing import Optional
from .ffmpeg_executor import FFmpegExecutor


class AudioStreamDetector:
    """Detects if a media file contains an audio stream."""

    def __init__(self, ffmpeg_executor: FFmpegExecutor):
        self.ffmpeg_executor = ffmpeg_executor

    def has_audio_stream(self, file_path: str, timeout: int = 10) -> bool:
        """
        Check if a video/audio file contains an audio stream.

        Replicates the ffprobe command:
        ffprobe -v error -select_streams a:0 -show_entries stream=codec_type -of csv=p=0 file_path

        Args:
            file_path: Path to media file
            timeout: Timeout in seconds for ffprobe command

        Returns:
            True if audio stream exists, False otherwise
        """
        if not os.path.exists(file_path):
            return False

        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "csv=p=0",
            file_path,
        ]

        try:
            _, stdout, stderr = self.ffmpeg_executor.run_ffprobe(cmd)
            return bool(stdout.strip())
        except Exception:
            # Fallback: check if file has reasonable size (> 10KB)
            try:
                return os.path.getsize(file_path) > 10240
            except Exception:
                return False
