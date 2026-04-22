"""
FFmpeg/FFprobe executor abstraction.
"""

import subprocess
from typing import Tuple, Optional, List


class FFmpegExecutor:
    """Executes FFmpeg and FFprobe commands with consistent error handling."""

    def __init__(self, logger):
        self.logger = logger

    def run_ffmpeg(
        self, cmd: List[str], timeout: Optional[int] = None, check: bool = True
    ) -> Tuple[int, str, str]:
        """
        Run ffmpeg command.

        Returns:
            Tuple of (returncode, stdout, stderr)

        Raises:
            subprocess.CalledProcessError: if check=True and command fails
            subprocess.TimeoutExpired: if timeout occurs
        """
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout, check=check
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.CalledProcessError as e:
            self.logger.error(f"FFmpeg error: {e.stderr}")
            raise
        except subprocess.TimeoutExpired as e:
            self.logger.error(f"FFmpeg timeout after {timeout}s")
            raise
        except Exception as e:
            self.logger.error(f"FFmpeg unexpected error: {e}")
            raise

    def run_ffprobe(
        self, cmd: List[str], timeout: Optional[int] = None
    ) -> Tuple[int, str, str]:
        """
        Run ffprobe command.

        Returns:
            Tuple of (returncode, stdout, stderr)

        Raises:
            subprocess.CalledProcessError: if command fails
            subprocess.TimeoutExpired: if timeout occurs
        """
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout, check=True
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.CalledProcessError as e:
            self.logger.error(f"FFprobe error: {e.stderr}")
            raise
        except subprocess.TimeoutExpired as e:
            self.logger.error(f"FFprobe timeout after {timeout}s")
            raise
        except Exception as e:
            self.logger.error(f"FFprobe unexpected error: {e}")
            raise

    def run_ffmpeg_capture_output(self, cmd: List[str]) -> Tuple[str, str]:
        """
        Run ffmpeg and capture output (convenience method).

        Returns:
            Tuple of (stdout, stderr)

        Raises:
            subprocess.CalledProcessError: if command fails
        """
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout, result.stderr
