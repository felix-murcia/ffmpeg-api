"""
Audio concatenator service - joins multiple audio files into one.

Uses ffmpeg concat demuxer for lossless concatenation.
"""

import json
import os
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from .base import AudioService
from .exceptions import AudioProcessingError
from .ffmpeg_executor import FFmpegExecutor
from .file_handler import FileHandler
from ..config import TimeoutConfig


class AudioConcatenationError(AudioProcessingError):
    """Raised when audio concatenation fails."""
    pass


class AudioConcatenator(AudioService):
    """Service for concatenating multiple audio files into one."""

    OUTPUT_FORMAT = "mp3"
    MIME_TYPE = "audio/mpeg"
    DEFAULT_FILENAME = "concatenated.mp3"

    def __init__(
        self,
        ffmpeg_executor: FFmpegExecutor,
        file_handler: FileHandler,
        logger,
        timeout: int = TimeoutConfig.AUDIO_CONCATENATION_TIMEOUT,
    ):
        self.ffmpeg_executor = ffmpeg_executor
        self.file_handler = file_handler
        self.logger = logger
        self.timeout = timeout

    def concatenate(
        self,
        audio_paths: List[str],
        temp_id: str,
        output_format: str = "mp3",
    ) -> Tuple[bytes, str, str]:
        """
        Concatenate multiple audio files into one.

        Args:
            audio_paths: List of paths to audio files to concatenate
            temp_id: Temporary ID for output file
            output_format: Output format (mp3, wav, etc.)

        Returns:
            Tuple of (audio_bytes, mime_type, filename)

        Raises:
            AudioConcatenationError: If concatenation fails
        """
        if not audio_paths:
            raise AudioConcatenationError("No audio files provided")

        # Validate all files exist
        for path in audio_paths:
            if not os.path.exists(path):
                raise AudioConcatenationError(f"File not found: {path}")

        # If only one file, return it directly
        if len(audio_paths) == 1:
            self.logger.info("[CONCAT] Only one file provided, returning as-is")
            try:
                with open(audio_paths[0], "rb") as f:
                    data = f.read()
                return data, self.MIME_TYPE, self.DEFAULT_FILENAME
            except Exception as e:
                raise AudioConcatenationError(f"Failed to read audio file: {e}") from e

        output_path = self.file_handler.generate_temp_path(
            f"{temp_id}_concatenated", f".{output_format}"
        )

        # Create concat list file
        list_file = None
        try:
            # Write concat demuxer list file
            list_file = tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, dir="/tmp"
            )

            for path in audio_paths:
                # Escape single quotes for ffmpeg concat demuxer
                safe_path = path.replace("'", "'\\''")
                list_file.write(f"file '{safe_path}'\n")

            list_file.close()

            self.logger.info(
                f"[CONCAT] Concatenating {len(audio_paths)} audio files to {output_format}"
            )

            # Build ffmpeg command
            cmd = [
                "ffmpeg",
                "-f", "concat",
                "-safe", "0",
                "-i", list_file.name,
                "-c", "copy",
                "-y",
                output_path,
            ]

            self.logger.debug(f"[CONCAT] Command: {' '.join(cmd)}")

            result = self.ffmpeg_executor.run_ffmpeg(cmd, timeout=self.timeout)

            if result[0] != 0:
                error_msg = result[2] if len(result) > 2 else "Unknown error"
                self.logger.error(f"[CONCAT] FFmpeg error: {error_msg}")
                raise AudioConcatenationError(f"Concatenation failed: {error_msg}")

            if not os.path.exists(output_path):
                raise AudioConcatenationError("Output file was not created")

            # Read concatenated audio
            with open(output_path, "rb") as f:
                data = f.read()

            self.logger.info(
                f"[CONCAT] Concatenation successful: {len(audio_paths)} files → "
                f"{output_path} ({len(data)} bytes)"
            )

            # Cleanup output file
            try:
                os.remove(output_path)
            except Exception as e:
                self.logger.warning(f"[CONCAT] Failed to cleanup temp output: {e}")

            return data, self.MIME_TYPE, self.DEFAULT_FILENAME

        except AudioConcatenationError:
            raise
        except Exception as e:
            self.logger.error(f"[CONCAT] Error: {e}")
            raise AudioConcatenationError(str(e)) from e
        finally:
            # Cleanup list file
            if list_file:
                try:
                    os.unlink(list_file.name)
                except Exception as e:
                    self.logger.debug(f"[CONCAT] Failed to cleanup list file: {e}")

    def process(self, input_path: str, temp_id: str) -> Tuple[bytes, str, str]:
        """Not used for concatenator, as it requires a list of paths."""
        raise NotImplementedError(
            "Use concatenate() instead, passing a list of audio file paths"
        )
