"""
Audio cleaner service - normalizes and standardizes audio.
"""

import os
import subprocess
from typing import Optional, Tuple
from .base import AudioService
from .exceptions import AudioCleanError
from .ffmpeg_executor import FFmpegExecutor
from .file_handler import FileHandler


class AudioCleaner(AudioService):
    """Service for cleaning and normalizing audio files."""

    # Output format
    OUTPUT_FORMAT = "wav"
    MIME_TYPE = "audio/wav"
    DEFAULT_FILENAME = "cleaned.wav"
    ORIGINAL_FILENAME = "original.wav"

    # FFmpeg parameters for cleaning (WAV 16kHz mono, max speed)
    CLEAN_PARAMS = ["-ac", "1", "-ar", "16000", "-acodec", "pcm_s16le"]

    def __init__(
        self,
        ffmpeg_executor: FFmpegExecutor,
        file_handler: FileHandler,
        logger,
        timeout: int = 60,
    ):
        self.ffmpeg_executor = ffmpeg_executor
        self.file_handler = file_handler
        self.logger = logger
        self.timeout = timeout

    def clean(self, input_path: str, temp_id: str) -> Tuple[bytes, str, str]:
        """
        Clean audio file - convert to standard format (16kHz mono WAV).

        On failure, returns original audio as fallback.

        Args:
            input_path: Path to input audio file
            temp_id: Temporary ID for output file

        Returns:
            Tuple of (audio_bytes, mime_type, filename)

        Raises:
            AudioCleanError: If cleaning fails catastrophically
        """
        output_path = self.file_handler.generate_temp_path(
            temp_id, f".{self.OUTPUT_FORMAT}"
        )

        self.logger.info(f"[CLEAN] Processing: {input_path}")
        self.logger.info(
            f"[CLEAN] Original size: {self.file_handler.get_size(input_path)} bytes"
        )

        # Build command with threading for speed
        cmd = (
            ["ffmpeg", "-threads", "0", "-i", input_path]
            + self.CLEAN_PARAMS
            + ["-y", output_path]
        )

        self.logger.info(f"[CLEAN] Command: {' '.join(cmd)}")

        try:
            result = self.ffmpeg_executor.run_ffmpeg(cmd, timeout=self.timeout)

            if result[0] != 0:  # non-zero exit code
                self.logger.error(f"[CLEAN] FFmpeg error: {result[2]}")
                return self._return_original(input_path)

        except subprocess.TimeoutExpired:
            self.logger.error("[CLEAN] Timeout after 60 seconds")
            return self._return_original(input_path)
        except Exception as e:
            self.logger.error(f"[CLEAN] Error: {e}")
            return self._return_original(input_path)

        # Check if output was created
        if not self.file_handler.exists(output_path):
            self.logger.error("[CLEAN] Output file not created")
            return self._return_original(input_path)

        # Read cleaned audio
        try:
            with open(output_path, "rb") as f:
                data = f.read()
        except Exception as e:
            self.logger.error(f"[CLEAN] Failed to read output: {e}")
            return self._return_original(input_path)
        finally:
            self.file_handler.cleanup(output_path)

        self.logger.info(f"[CLEAN] Output size: {len(data)} bytes")

        return data, self.MIME_TYPE, self.DEFAULT_FILENAME

    def _return_original(self, input_path: str) -> Tuple[bytes, str, str]:
        """Return original audio as fallback."""
        try:
            with open(input_path, "rb") as f:
                data = f.read()
            return data, self.MIME_TYPE, self.ORIGINAL_FILENAME
        except Exception as e:
            self.logger.error(f"[CLEAN] Failed to read original: {e}")
            raise AudioCleanError("Failed to read original file") from e

    def process(self, input_path: str, temp_id: str) -> Tuple[bytes, str, str]:
        """Alias for clean to satisfy AudioService interface."""
        return self.clean(input_path, temp_id)
