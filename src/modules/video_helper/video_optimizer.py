"""
Video optimizer service - handles video optimization with GPU acceleration.
"""

import os
import shutil
import uuid
import time
from multiprocessing import Process
from typing import Dict, Any, Optional

from .file_handler import FileHandler
from .ffmpeg_executor import FFmpegExecutor
from .exceptions import VideoOptimizationError, FileNotFoundError


class VideoOptimizer:
    """Service for optimizing video files using FFmpeg with GPU acceleration."""

    def __init__(
        self,
        ffmpeg_executor: FFmpegExecutor,
        file_handler: FileHandler,
        process_manager,
        get_gpu_config_func,
        logger,
    ):
        self.ffmpeg_executor = ffmpeg_executor
        self.file_handler = file_handler
        self.process_manager = process_manager
        self.get_gpu_config = get_gpu_config_func
        self.logger = logger

    def launch_optimization(self, input_path: str, output_path: str) -> str:
        """
        Start video optimization process.

        Args:
            input_path: Path to input video file
            output_path: Path where output will be saved

        Returns:
            process_id: Unique identifier for the optimization process

        Raises:
            VideoOptimizationError: If optimization cannot be started
            FileNotFoundError: If input file does not exist
        """
        # Validate input exists
        if not self.file_handler.exists(input_path):
            raise FileNotFoundError(f"Input file not found: {input_path}")

        self.logger.info(
            f"📥 Recibida petición optimize: input={input_path}, output={output_path}"
        )

        # Check file size
        file_size = self.file_handler.get_size(input_path) / (1024 * 1024 * 1024)  # GB
        self.logger.info(f"📊 Tamaño del archivo: {file_size:.2f} GB")

        # Generate process ID
        process_id = str(uuid.uuid4())
        self.logger.info(f"🆔 Nuevo proceso: {process_id}")

        # Determine if file needs to be copied to /tmp for better performance
        original_input = input_path
        needs_copy = input_path.startswith("/downloads") or input_path.startswith(
            "~/downloads"
        )
        temp_input = input_path

        if needs_copy:
            filename = os.path.basename(input_path)
            temp_dir = "/tmp/ffmpeg_input"
            os.makedirs(temp_dir, exist_ok=True)
            temp_input = os.path.join(temp_dir, f"{process_id}_{filename}")
            self.logger.info(
                f"📁 Archivo en /downloads detectado - será copiado a {temp_input}"
            )
            try:
                shutil.copy2(input_path, temp_input)
            except Exception as e:
                raise VideoOptimizationError(f"Failed to copy input file: {e}") from e

        # Get GPU configuration
        gpu_config = self.get_gpu_config()

        # Build FFmpeg command
        cmd = self._build_command(
            temp_input if needs_copy else input_path, output_path, gpu_config
        )

        self.logger.info(f"🎬 Comando: {' '.join(cmd)}")

        # Create process entry in process manager
        process_data = {
            "id": process_id,
            "cmd": " ".join(cmd),
            "input": original_input,
            "input_for_ffmpeg": temp_input,
            "output": output_path,
            "status": "starting",
            "progress": 0,
            "start_time": time.time(),
            "logs": [],
            "total_duration": None,
            "gpu_config": gpu_config,
            "needs_copy": needs_copy,
            "copy_progress": 0,
        }
        self.process_manager.set(process_id, process_data)
        self.logger.info(f"[{process_id}] ✅ Proceso creado en diccionario compartido")

        # Attempt to get total duration
        self._set_total_duration(process_id, original_input)

        # Save initial state to file
        self.process_manager.save_to_file(process_id)
        self.logger.info(f"[{process_id}] 💾 Estado inicial guardado en archivo")

        # Start background process
        try:
            from ..ffmpeg_runner import run_ffmpeg

            p = Process(target=run_ffmpeg, args=(process_id, cmd))
            p.daemon = True
            p.start()
        except Exception as e:
            raise VideoOptimizationError(
                f"Failed to start optimization process: {e}"
            ) from e

        return process_id

    def _build_command(
        self, input_file: str, output_file: str, gpu_config: Dict[str, Any]
    ) -> list:
        """Build FFmpeg command with GPU acceleration."""
        cmd = [
            "ffmpeg",
            "-hwaccel",
            "cuda",
            "-hwaccel_output_format",
            "cuda",
            "-i",
            input_file,
            "-map",
            "0:v:0?",
            "-map",
            "0:a:0?",
            "-map",
            "0:s:0?",
            "-c:v",
            "h264_nvenc",
            "-preset",
            gpu_config["preset"],
            "-tune",
            "hq",
            "-rc",
            "vbr",
        ]

        # Multipass
        if gpu_config["multipass"] != "none":
            cmd.extend(["-multipass", gpu_config["multipass"]])

        # Video parameters
        cmd.extend(
            [
                "-cq",
                "28",
                "-b:v",
                "2500k",
                "-minrate",
                "1500k",
                "-maxrate",
                "3500k",
                "-bufsize",
                "7000k",
                "-g",
                "60",
                "-keyint_min",
                "60",
                "-sc_threshold",
                "0",
                "-bf",
                "3",
                "-rc-lookahead",
                gpu_config["lookahead"],
                "-profile:v",
                "high",
            ]
        )

        # Level if needed
        if gpu_config.get("include_level", False):
            cmd.extend(["-level", gpu_config["level"]])

        # Output parameters
        cmd.extend(
            [
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-ac",
                "2",
                "-ar",
                "48000",
                "-c:s",
                "copy",
                "-disposition:a:0",
                "default",
                "-f",
                "matroska",
                "-y",
                output_file,
            ]
        )

        return cmd

    def _set_total_duration(self, process_id: str, input_path: str) -> None:
        """Probe input file to get total duration and store in process info."""
        try:
            duration_cmd = [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                input_path,
            ]
            _, stdout, _ = self.ffmpeg_executor.run_ffprobe(duration_cmd)
            duration = float(stdout.strip())
            process = self.process_manager.get(process_id)
            if process:
                process["total_duration"] = duration
            self.logger.info(f"⏱️ Duración total: {duration:.2f} segundos")
        except Exception as e:
            self.logger.warning(f"⚠️ No se pudo obtener duración: {e}")
