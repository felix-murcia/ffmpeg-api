"""
Video creator service - creates video from audio and image.
"""

import os
import uuid
import subprocess
import logging
from typing import Dict

from .file_handler import FileHandler
from .ffmpeg_executor import FFmpegExecutor
from .exceptions import VideoCreationError, FileNotFoundError
from ..config import TimeoutConfig

logger = logging.getLogger("ffmpeg-api")

class VideoCreator:
    """Service for creating video from audio and image."""

    def __init__(
        self,
        ffmpeg_executor: FFmpegExecutor,
        file_handler: FileHandler,
        logger,
        get_gpu_preset_and_level=None,
    ):
        self.ffmpeg_executor = ffmpeg_executor
        self.file_handler = file_handler
        self.logger = logger
        self.get_gpu_preset_and_level = get_gpu_preset_and_level

    def create(self, audio_path: str, image_path: str) -> Dict[str, str]:
        """
        Create video from audio and image.

        Args:
            audio_path: Path to audio file
            image_path: Path to image file

        Returns:
            Dictionary with output_path, output_filename, image_used, audio_source

        Raises:
            VideoCreationError: If creation fails
            FileNotFoundError: If input files do not exist
        """
        # Validate inputs
        if not self.file_handler.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        if not self.file_handler.exists(image_path):
            raise FileNotFoundError(f"Image file not found: {image_path}")

        self.logger.info(
            f"🎵 Recibida petición create-from-audio: audio_path={audio_path}, image_path={image_path}"
        )

        # Generate output filename and path
        output_filename = f"video_{uuid.uuid4()}.mp4"
        output_path = os.path.join("/tmp/videos", output_filename)

        # Ensure output directory exists
        os.makedirs("/tmp/videos", exist_ok=True)

        # Build command
        cmd = self._build_command(image_path, audio_path, output_path)

        self.logger.info(f"🎬 Comando: {' '.join(cmd)}")

        # Execute FFmpeg command
        try:
            self.ffmpeg_executor.run_ffmpeg(cmd, timeout=TimeoutConfig.VIDEO_CREATION_TIMEOUT, check=True)
        except subprocess.CalledProcessError as e:
            error_msg = f"FFmpeg command failed with exit code {e.returncode}\nSTDERR:\n{e.stderr}\nSTDOUT:\n{e.stdout}"
            self.logger.error(error_msg)
            raise VideoCreationError(error_msg) from e
        except Exception as e:
            error_msg = f"Unexpected error during video creation: {e}"
            self.logger.error(error_msg)
            raise VideoCreationError(error_msg) from e

        self.logger.info(f"✅ Video creado exitosamente: {output_path}")

        return {
            "success": True,
            "output_path": output_path,
            "output_filename": output_filename,
            "image_used": os.path.basename(image_path),
            "audio_source": os.path.basename(audio_path),
        }

    def _build_command(
        self, image_path: str, audio_path: str, output_path: str
    ) -> list:
        """Build FFmpeg command for creating video from image and audio."""
        # Get GPU configuration
        if self.get_gpu_preset_and_level:
            gpu_config = self.get_gpu_preset_and_level()
        else:
            gpu_config = {
                "preset": "p4",
                "include_level": False,
                "multipass": "none",
                "lookahead": "16",
            }

        cmd = [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            image_path,
            "-i",
            audio_path,
            "-vf",
            "scale=640:360:force_original_aspect_ratio=decrease,pad=640:360:(ow-iw)/2:(oh-ih)/2",
            "-c:v",
            "h264_nvenc",
            "-preset",
            "p1",
            "-tune",
            "hq",
            "-rc",
            "vbr",
            "-cq",
            "28",
            "-b:v",
            "300k",
            "-maxrate",
            "500k",
            "-bufsize",
            "1000k",
            "-g",
            "60",
            "-keyint_min",
            "60",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            "-ac",
            "2",
            "-ar",
            "48000",
            "-shortest",
            output_path,
        ]

        if gpu_config.get("include_level"):
            cmd.extend(["-level", gpu_config["level"]])

        return cmd
