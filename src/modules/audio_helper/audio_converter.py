"""
Audio converter service - converts audio to different formats.
"""

import os
import subprocess
import math
import tempfile
import logging
from typing import Optional, Tuple
from .base import AudioService
from .exceptions import AudioConversionError
from .ffmpeg_executor import FFmpegExecutor
from .file_handler import FileHandler

logger = logging.getLogger("ffmpeg-api")

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

    def get_file_size_mb(self, file_path: str) -> float:
        """Obtiene tamaño del archivo en MB"""
        return os.path.getsize(file_path) / (1024 * 1024)
    
    def get_audio_duration(self, audio_path: str) -> float:
        """Obtiene duración en segundos usando ffprobe"""
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            audio_path
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except Exception as e:
            raise AudioConversionError(f"Error getting duration: {e}")
    
    def chunk_mp3(self, mp3_path: str, max_size_mb: int = 22) -> list:
        """
        Divide un MP3 en chunks que no excedan max_size_mb.
        Cada chunk es optimizado para Groq (mono, 16kHz, alta compresión).
        
        Args:
            mp3_path: Ruta del archivo MP3 a dividir
            max_size_mb: Tamaño máximo por chunk en MB
            
        Returns:
            Lista de rutas de chunks temporales
        """
        total_size = self.get_file_size_mb(mp3_path)
        total_duration = self.get_audio_duration(mp3_path)
        
        # Calcular número de chunks necesarios
        num_chunks = math.ceil(total_size / max_size_mb)
        chunk_duration = total_duration / num_chunks
        
        # Overlap de 3 segundos entre chunks (evita perder palabras en cortes)
        overlap_seconds = 3
        
        chunk_paths = []
        
        logger.info(f"Dividiendo {total_duration:.0f}s / {total_size:.1f}MB "
                   f"en {num_chunks} chunks de ~{chunk_duration:.0f}s c/u")
        
        for i in range(num_chunks):
            # Calcular tiempos del chunk
            start_time = i * chunk_duration
            if i > 0:
                start_time = max(0, start_time - overlap_seconds)
            
            end_time = min((i + 1) * chunk_duration + overlap_seconds, total_duration)
            
            # Crear archivo temporal
            chunk_path = tempfile.NamedTemporaryFile(
                delete=False, 
                suffix=f"_chunk_{i+1:03d}_of_{num_chunks}.mp3"
            ).name
            
            # Comando ffmpeg optimizado para voz (Groq Whisper)
            cmd = [
                "ffmpeg",
                "-i", mp3_path,
                "-ss", str(start_time),
                "-to", str(end_time),
                "-acodec", "libmp3lame",
                "-q:a", "9",           # Calidad más baja (menor tamaño)
                "-ac", "1",            # Mono
                "-ar", "16000",        # 16 kHz (óptimo para Whisper)
                "-y",
                chunk_path
            ]
            
            try:
                self.ffmpeg_executor.run_ffmpeg(cmd, check=True)
                chunk_size = self.get_file_size_mb(chunk_path)
                logger.info(f"Chunk {i+1}/{num_chunks}: {chunk_size:.1f}MB "
                           f"({start_time:.0f}s-{end_time:.0f}s)")
                chunk_paths.append(chunk_path)
                
            except subprocess.CalledProcessError as e:
                # Limpiar chunks creados hasta ahora
                for chunk in chunk_paths:
                    try:
                        os.unlink(chunk)
                    except:
                        pass
                raise AudioConversionError(f"Error creando chunk {i+1}: {e.stderr}")
        
        return chunk_paths