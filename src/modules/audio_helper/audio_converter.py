"""
Audio converter service - converts audio to different formats.
"""

import os
import subprocess
from typing import Optional, Tuple
from .base import AudioService
from .exceptions import AudioConversionError
from .ffmpeg_executor import FFmpegExecutor
from .file_handler import FileHandler


class AudioConverter(AudioService):
    """Service for converting audio files to different formats."""

    # Supported formats
    FORMAT_WAV = "wav"
    FORMAT_MP3 = "mp3"

    SUPPORTED_FORMATS = [FORMAT_WAV, FORMAT_MP3]

    # FFmpeg configurations per format
    FORMAT_CONFIGS = {
        FORMAT_WAV: {
            "args": [
                "-ac",
                "1",
                "-ar",
                "16000",
                "-acodec",
                "pcm_s16le",
                "-f",
                "wav",
                "-threads",
                "0",
            ],
            "mime_type": "audio/wav",
        },
        FORMAT_MP3: {
            "args": [
                "-vn",
                "-acodec",
                "libmp3lame",
                "-q:a",
                "9",
                "-threads",
                "0",
            ],  # VBR mínimo, tamaño reducido
            "mime_type": "audio/mpeg",
        },
    }

    def __init__(self, ffmpeg_executor: FFmpegExecutor, file_handler: FileHandler):
        self.ffmpeg_executor = ffmpeg_executor
        self.file_handler = file_handler

    def convert(
        self, input_path: str, output_format: str, temp_id: str
    ) -> Tuple[bytes, str, str]:
        """
        Convert audio file to specified format.

        Args:
            input_path: Path to input audio file
            output_format: Target format (wav or mp3)
            temp_id: Temporary ID for output file

        Returns:
            Tuple of (audio_bytes, mime_type, filename)

        Raises:
            AudioConversionError: If conversion fails or format unsupported
        """
        if output_format not in self.SUPPORTED_FORMATS:
            raise AudioConversionError(
                f"Unsupported format: {output_format}. "
                f"Supported: {self.SUPPORTED_FORMATS}"
            )

        config = self.FORMAT_CONFIGS[output_format]
        output_path = self.file_handler.generate_temp_path(temp_id, f".{output_format}")

        # Build command with threading for speed
        cmd = (
            ["ffmpeg", "-threads", "0", "-i", input_path]
            + config["args"]
            + ["-y", output_path]
        )

        try:
            self.ffmpeg_executor.run_ffmpeg(cmd)
        except subprocess.CalledProcessError as e:
            raise AudioConversionError(f"FFmpeg conversion failed: {e.stderr}") from e
        except Exception as e:
            raise AudioConversionError(f"Conversion error: {str(e)}") from e

        # Read output file
        try:
            with open(output_path, "rb") as f:
                audio_data = f.read()
        except Exception as e:
            raise AudioConversionError(f"Failed to read output file: {str(e)}") from e
        finally:
            # Cleanup
            self.file_handler.cleanup(output_path)

        mime_type = config["mime_type"]
        filename = f"converted.{output_format}"

        return audio_data, mime_type, filename

    def process(
        self, input_path: str, output_format: str, temp_id: str
    ) -> Tuple[bytes, str, str]:
        """Alias for convert to satisfy AudioService interface."""
        return self.convert(input_path, output_format, temp_id)

    def get_conversion_command(
        self, input_file: str, output_file: str, fmt: str
    ) -> list:
        """Get ffmpeg command for conversion (for suggested_conversion)."""
        if fmt not in self.FORMAT_CONFIGS:
            raise AudioConversionError(f"Unsupported format: {fmt}")
        config = self.FORMAT_CONFIGS[fmt]
        return ["ffmpeg", "-i", input_file] + config["args"] + ["-y", output_file]

    def convert_to_wav16k_mono(
        self, input_path: str, temp_id: str
    ) -> Tuple[bytes, str, str]:
        """
        Convert any audio to 16kHz mono WAV (standard format for transcription).

        This is a convenience method that always targets WAV with these ffmpeg args:
        -ac 1 (mono) -ar 16000 (16kHz) -f wav

        Args:
            input_path: Path to input audio file
            temp_id: Temporary ID for output file

        Returns:
            Tuple of (audio_bytes, mime_type="audio/wav", filename="converted.wav")

        Raises:
            AudioConversionError: If conversion fails
        """
        return self.convert(input_path, self.FORMAT_WAV, temp_id)

    def convert_to_mp3_file(
        self, input_path: str, delete_original: bool = False
    ) -> str:
        """
        Convert audio file to MP3 and optionally delete original.

        This replicates the ffmpeg command used in legacy client code:
        ffmpeg -i input -acodec libmp3lame -ab 192k -y output.mp3

        Args:
            input_path: Path to input audio file
            delete_original: If True, remove input file after successful conversion

        Returns:
            Path to the output MP3 file

        Raises:
            AudioConversionError: If conversion fails
        """
        if not self.file_handler.exists(input_path):
            raise AudioConversionError(f"Input file not found: {input_path}")

        output_path = os.path.splitext(input_path)[0] + ".mp3"

        # Build command matching legacy client but optimized for size & speed
        cmd = [
            "ffmpeg",
            "-threads",
            "0",
            "-i",
            input_path,
            "-vn",
            "-acodec",
            "libmp3lame",
            "-q:a",
            "9",  # VBR lowest quality for minimal size
            "-y",
            output_path,
        ]

        try:
            self.ffmpeg_executor.run_ffmpeg(cmd, check=True)
        except subprocess.CalledProcessError as e:
            raise AudioConversionError(
                f"FFmpeg MP3 conversion failed: {e.stderr}"
            ) from e
        except Exception as e:
            raise AudioConversionError(f"MP3 conversion error: {str(e)}") from e

        if not self.file_handler.exists(output_path):
            raise AudioConversionError("MP3 output file was not created")

        # Optionally delete original
        if delete_original:
            try:
                self.file_handler.cleanup(input_path)
            except Exception as e:
                # Log but don't fail if original cannot be deleted
                import warnings

                warnings.warn(f"Failed to delete original file {input_path}: {e}")

        return output_path
