"""
Audio tempo adjuster service - applies atempo filter for speed adjustment.

Used to speed up or slow down audio without changing pitch.
"""

import os
from typing import Optional, Tuple

from .base import AudioService
from .exceptions import AudioProcessingError
from .ffmpeg_executor import FFmpegExecutor
from .file_handler import FileHandler
from ..config import TimeoutConfig


class AudioTempoError(AudioProcessingError):
    """Raised when tempo adjustment fails."""
    pass


class AudioTempoAdjuster(AudioService):
    """Service for adjusting audio speed using atempo filter."""

    OUTPUT_FORMAT = "wav"
    MIME_TYPE = "audio/wav"
    DEFAULT_FILENAME = "tempo_adjusted.wav"

    def __init__(
        self,
        ffmpeg_executor: FFmpegExecutor,
        file_handler: FileHandler,
        logger,
        timeout: int = TimeoutConfig.AUDIO_PROCESSING_TIMEOUT,
    ):
        self.ffmpeg_executor = ffmpeg_executor
        self.file_handler = file_handler
        self.logger = logger
        self.timeout = timeout

    def adjust_tempo(
        self,
        input_path: str,
        temp_id: str,
        tempo_factor: float = 1.0,
    ) -> Tuple[bytes, str, str]:
        """
        Adjust audio tempo (speed) without changing pitch.

        Args:
            input_path: Path to input audio file
            temp_id: Temporary ID for output file
            tempo_factor: Speed factor (0.5 = half speed, 2.0 = double speed)

        Returns:
            Tuple of (audio_bytes, mime_type, filename)

        Raises:
            AudioTempoError: If adjustment fails
        """
        if not os.path.exists(input_path):
            raise AudioTempoError(f"Input file not found: {input_path}")

        if tempo_factor < 0.25 or tempo_factor > 4.0:
            raise AudioTempoError(
                f"Tempo factor must be between 0.25 and 4.0, got {tempo_factor}"
            )

        # If tempo is 1.0 (no change), just return the input
        if tempo_factor == 1.0:
            self.logger.info("[TEMPO] Tempo factor is 1.0, returning input unchanged")
            try:
                with open(input_path, "rb") as f:
                    data = f.read()
                return data, self.MIME_TYPE, self.DEFAULT_FILENAME
            except Exception as e:
                raise AudioTempoError(f"Failed to read input file: {e}") from e

        output_path = self.file_handler.generate_temp_path(
            f"{temp_id}_tempo_{str(tempo_factor).replace('.', '_')}", f".{self.OUTPUT_FORMAT}"
        )

        self.logger.info(
            f"[TEMPO] Adjusting tempo: {tempo_factor}x (input: {input_path})"
        )

        cmd = [
            "ffmpeg",
            "-i", input_path,
            "-filter:a", f"atempo={tempo_factor}",
            "-q:a", "9",
            "-y",
            output_path,
        ]

        try:
            result = self.ffmpeg_executor.run_ffmpeg(cmd, timeout=self.timeout)

            if result[0] != 0:
                error_msg = result[2] if len(result) > 2 else "Unknown error"
                self.logger.error(f"[TEMPO] FFmpeg error: {error_msg}")
                raise AudioTempoError(f"Tempo adjustment failed: {error_msg}")

            if not os.path.exists(output_path):
                raise AudioTempoError("Output file was not created")

            # Read adjusted audio
            with open(output_path, "rb") as f:
                data = f.read()

            self.logger.info(
                f"[TEMPO] Tempo adjusted successfully: {output_path} ({len(data)} bytes)"
            )

            # Cleanup
            try:
                os.remove(output_path)
            except Exception as e:
                self.logger.warning(f"[TEMPO] Failed to cleanup temp file: {e}")

            return data, self.MIME_TYPE, self.DEFAULT_FILENAME

        except Exception as e:
            self.logger.error(f"[TEMPO] Error: {e}")
            raise AudioTempoError(str(e)) from e

    def process(self, input_path: str, temp_id: str) -> Tuple[bytes, str, str]:
        """Alias for adjust_tempo with default tempo factor."""
        return self.adjust_tempo(input_path, temp_id, tempo_factor=1.0)
