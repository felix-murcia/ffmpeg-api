"""
Audio post-processor service - removes TTS synthesis artifacts and improves quality.

Implements multi-step audio enhancement:
1. Loudness normalization (LUFS-based)
2. Breathing artifact removal (high-pass filter + gate)
3. Plosive/spectral artifact stabilization (EQ)
4. Dynamic range compression and limiting
"""

import os
import tempfile
from pathlib import Path
from typing import Optional, Tuple

from .base import AudioService
from .exceptions import AudioProcessingError
from .ffmpeg_executor import FFmpegExecutor
from .file_handler import FileHandler
from ..config import TimeoutConfig


class AudioPostProcessingError(AudioProcessingError):
    """Raised when audio post-processing fails."""
    pass


class AudioPostProcessor(AudioService):
    """Service for post-processing TTS audio to remove synthesis artifacts."""

    OUTPUT_FORMAT = "wav"
    MIME_TYPE = "audio/wav"
    DEFAULT_FILENAME = "post_processed.wav"

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

    def post_process(
        self,
        input_path: str,
        temp_id: str,
        normalize: bool = True,
        remove_breathing: bool = True,
        stabilize_plosives: bool = True,
        noise_gate_threshold: float = -40.0,
    ) -> Tuple[bytes, str, str]:
        """
        Post-process audio to remove TTS artifacts.

        Args:
            input_path: Path to input audio file
            temp_id: Temporary ID for output files
            normalize: Apply loudness normalization
            remove_breathing: Apply breathing sound reduction
            stabilize_plosives: Apply plosive/artifact stabilization
            noise_gate_threshold: Threshold in dB for noise gate

        Returns:
            Tuple of (audio_bytes, mime_type, filename)

        Raises:
            AudioPostProcessingError: If processing fails
        """
        if not os.path.exists(input_path):
            raise AudioPostProcessingError(f"Input file not found: {input_path}")

        current_path = input_path
        temp_files = []

        try:
            # Step 1: Normalize loudness
            if normalize:
                self.logger.info("[POST-PROCESS] Applying loudness normalization...")
                current_path = self._normalize_loudness(current_path, temp_id, 0, temp_files)
                if not current_path:
                    raise AudioPostProcessingError("Normalization failed")

            # Step 2: Remove breathing sounds
            if remove_breathing:
                self.logger.info("[POST-PROCESS] Removing breathing artifacts...")
                current_path = self._remove_breathing_artifacts(
                    current_path, temp_id, 1, noise_gate_threshold, temp_files
                )
                if not current_path:
                    raise AudioPostProcessingError("Breathing removal failed")

            # Step 3: Stabilize plosives and artifacts
            if stabilize_plosives:
                self.logger.info("[POST-PROCESS] Stabilizing plosives and artifacts...")
                current_path = self._stabilize_artifacts(current_path, temp_id, 2, temp_files)
                if not current_path:
                    raise AudioPostProcessingError("Artifact stabilization failed")

            # Step 4: Apply compression and limiting
            self.logger.info("[POST-PROCESS] Applying compression and limiting...")
            current_path = self._apply_compression(current_path, temp_id, 3, temp_files)
            if not current_path:
                raise AudioPostProcessingError("Compression failed")

            # Read final output
            with open(current_path, "rb") as f:
                data = f.read()

            self.logger.info(f"[POST-PROCESS] Output size: {len(data)} bytes")
            return data, self.MIME_TYPE, self.DEFAULT_FILENAME

        except Exception as e:
            self.logger.error(f"[POST-PROCESS] Processing failed: {e}")
            raise AudioPostProcessingError(str(e)) from e
        finally:
            # Cleanup temp files
            for temp_file in temp_files:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                except Exception as e:
                    self.logger.warning(f"[POST-PROCESS] Failed to cleanup {temp_file}: {e}")

    def _normalize_loudness(
        self, input_path: str, temp_id: str, step: int, temp_files: list
    ) -> Optional[str]:
        """Normalize audio loudness to -23 LUFS (podcast standard)."""
        output_path = self.file_handler.generate_temp_path(
            f"{temp_id}_step{step}_normalized", ".wav"
        )
        temp_files.append(output_path)

        cmd = [
            "ffmpeg",
            "-i", input_path,
            "-af", "loudnorm=I=-23:TP=-1.5:LRA=11",
            "-q:a", "9",
            "-y",
            output_path,
        ]

        try:
            result = self.ffmpeg_executor.run_ffmpeg(cmd, timeout=self.timeout)
            if result[0] == 0 and os.path.exists(output_path):
                return output_path
            else:
                self.logger.error(f"[POST-PROCESS] Normalization error: {result[2]}")
                return None
        except Exception as e:
            self.logger.error(f"[POST-PROCESS] Normalization error: {e}")
            return None

    def _remove_breathing_artifacts(
        self,
        input_path: str,
        temp_id: str,
        step: int,
        noise_gate_threshold: float,
        temp_files: list,
    ) -> Optional[str]:
        """Remove breathing sounds and low-frequency rumble."""
        output_path = self.file_handler.generate_temp_path(
            f"{temp_id}_step{step}_debreathe", ".wav"
        )
        temp_files.append(output_path)

        # Convert threshold from dB to linear scale (0-1)
        # agate filter expects threshold in 0-1 range: 10^(dB/20)
        threshold_linear = 10 ** (noise_gate_threshold / 20)
        # Clamp to valid range [0.001, 1.0]
        threshold_linear = max(0.001, min(1.0, threshold_linear))

        # Try with gate filter first
        filters_with_gate = (
            f"highpass=f=80,"
            f"agate=threshold={threshold_linear:.4f}:ratio=2:attack=5:release=50"
        )

        cmd = [
            "ffmpeg",
            "-i", input_path,
            "-af", filters_with_gate,
            "-q:a", "9",
            "-y",
            output_path,
        ]

        try:
            result = self.ffmpeg_executor.run_ffmpeg(cmd, timeout=self.timeout)
            if result[0] == 0 and os.path.exists(output_path):
                self.logger.debug("[POST-PROCESS] Breathing removal with gate filter applied")
                return output_path
            else:
                # Fallback to high-pass only
                self.logger.warning("[POST-PROCESS] Gate filter unavailable, using high-pass only")
                return self._remove_breathing_fallback(input_path, temp_id, step, temp_files)
        except Exception as e:
            self.logger.warning(f"[POST-PROCESS] Gate filter error, using fallback: {e}")
            return self._remove_breathing_fallback(input_path, temp_id, step, temp_files)

    def _remove_breathing_fallback(
        self, input_path: str, temp_id: str, step: int, temp_files: list
    ) -> Optional[str]:
        """Fallback: high-pass filter only without gate."""
        output_path = self.file_handler.generate_temp_path(
            f"{temp_id}_step{step}_debreathe_fallback", ".wav"
        )
        temp_files.append(output_path)

        cmd = [
            "ffmpeg",
            "-i", input_path,
            "-af", "highpass=f=80",
            "-q:a", "9",
            "-y",
            output_path,
        ]

        try:
            result = self.ffmpeg_executor.run_ffmpeg(cmd, timeout=self.timeout)
            if result[0] == 0 and os.path.exists(output_path):
                return output_path
            else:
                self.logger.error(f"[POST-PROCESS] Fallback breathing removal error: {result[2]}")
                return None
        except Exception as e:
            self.logger.error(f"[POST-PROCESS] Fallback breathing removal error: {e}")
            return None

    def _stabilize_artifacts(
        self, input_path: str, temp_id: str, step: int, temp_files: list
    ) -> Optional[str]:
        """Stabilize plosives, spectral artifacts, and glitches with EQ."""
        output_path = self.file_handler.generate_temp_path(
            f"{temp_id}_step{step}_stabilized", ".wav"
        )
        temp_files.append(output_path)

        filters = (
            "equalizer=f=3500:t=q:w=2:g=-2,"  # Reduce harshness peak
            "equalizer=f=2500:t=q:w=1.5:g=1.5,"  # Presence boost
            "equalizer=f=100:t=q:w=0.7:g=-1"  # Reduce very low rumble
        )

        cmd = [
            "ffmpeg",
            "-i", input_path,
            "-af", filters,
            "-q:a", "9",
            "-y",
            output_path,
        ]

        try:
            result = self.ffmpeg_executor.run_ffmpeg(cmd, timeout=self.timeout)
            if result[0] == 0 and os.path.exists(output_path):
                self.logger.debug("[POST-PROCESS] Artifact stabilization applied")
                return output_path
            else:
                self.logger.error(f"[POST-PROCESS] Stabilization error: {result[2]}")
                return None
        except Exception as e:
            self.logger.error(f"[POST-PROCESS] Stabilization error: {e}")
            return None

    def _apply_compression(
        self, input_path: str, temp_id: str, step: int, temp_files: list
    ) -> Optional[str]:
        """Apply dynamic range compression and limiting."""
        output_path = self.file_handler.generate_temp_path(
            f"{temp_id}_step{step}_compressed", ".wav"
        )
        temp_files.append(output_path)

        filters = (
            "compand=attacks=0.005:decays=0.1:points=-80/-80|-20/-15|0/-10:soft-knee=6:gain=2"
        )

        cmd = [
            "ffmpeg",
            "-i", input_path,
            "-af", filters,
            "-q:a", "9",
            "-y",
            output_path,
        ]

        try:
            result = self.ffmpeg_executor.run_ffmpeg(cmd, timeout=self.timeout)
            if result[0] == 0 and os.path.exists(output_path):
                self.logger.debug("[POST-PROCESS] Compression applied")
                return output_path
            else:
                self.logger.error(f"[POST-PROCESS] Compression error: {result[2]}")
                return None
        except Exception as e:
            self.logger.error(f"[POST-PROCESS] Compression error: {e}")
            return None

    def process(self, input_path: str, temp_id: str) -> Tuple[bytes, str, str]:
        """Alias for post_process to satisfy AudioService interface."""
        return self.post_process(input_path, temp_id)
