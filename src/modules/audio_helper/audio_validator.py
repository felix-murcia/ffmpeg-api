"""
Audio validator service - validates audio files for transcription suitability.
"""

import json
import re
from typing import Dict, Any, Optional, Tuple
from .base import AudioService
from .exceptions import AudioValidationError
from .ffmpeg_executor import FFmpegExecutor
from .file_handler import FileHandler


class AudioValidator(AudioService):
    """Service for validating audio files for transcription."""

    # Thresholds
    MIN_DURATION = 1.0  # seconds
    MAX_DURATION_ISSUE = 7200.0  # 2 hours - hard limit
    MAX_DURATION_WARNING = 3600.0  # 1 hour - warning
    MIN_SAMPLE_RATE = 8000  # Hz
    RECOMMENDED_SAMPLE_RATE = 16000  # Hz
    MIN_BITRATE = 32000  # bps
    SILENCE_THRESHOLD = 0.5  # 50% silence is an issue
    SILENCE_WARNING_THRESHOLD = 0.3  # 30% silence is a warning
    VOICE_DETECTION_THRESHOLD = 0.9  # 90% silence means no voice
    VOLUME_ISSUE_THRESHOLD = -30.0  # dB
    VOLUME_WARNING_LOWER = -20.0  # dB
    VOLUME_WARNING_UPPER = -5.0  # dB

    # Recommended codecs
    RECOMMENDED_CODECS = ["mp3", "wav", "opus", "aac", "flac"]

    def __init__(
        self,
        ffmpeg_executor: FFmpegExecutor,
        file_handler: FileHandler,
        format_duration_func,
    ):
        self.ffmpeg_executor = ffmpeg_executor
        self.file_handler = file_handler
        self.format_duration = format_duration_func

    def validate(self, file_path: str) -> Dict[str, Any]:
        """
        Validate audio file for transcription suitability.

        Args:
            file_path: Path to audio file

        Returns:
            Validation result dictionary with keys:
                - valid: bool
                - optimal: bool
                - issues: list[str]
                - warnings: list[str]
                - recommendations: list[str]
                - metadata: dict
                - suggested_conversion: dict
        """
        if not self.file_handler.exists(file_path):
            raise AudioValidationError(f"File not found: {file_path}")

        # 1. Get basic info via ffprobe
        try:
            audio_stream, duration, codec, sample_rate, channels, bitrate = (
                self._probe_audio(file_path)
            )
        except Exception as e:
            raise AudioValidationError(f"FFprobe failed: {str(e)}") from e

        if not audio_stream:
            return {
                "valid": False,
                "optimal": False,
                "issues": ["No se encontró stream de audio en el archivo"],
                "warnings": [],
                "recommendations": [],
                "metadata": {},
                "suggested_conversion": None,
            }

        # 2. Basic validations
        issues, warnings, recommendations = self._validate_basic(
            duration, codec, sample_rate, channels, bitrate
        )

        # 3. Quality analysis (volume, silence)
        mean_volume, max_volume, silence_duration = self._analyze_quality(
            file_path, duration
        )

        # 4. Volume checks
        self._check_volume(mean_volume, issues, warnings)

        # 5. Silence checks
        self._check_silence(silence_duration, duration, issues, warnings)

        # 6. Voice detection
        has_voice = self._detect_voice(silence_duration, duration, issues)

        # 7. Format recommendations
        self._check_codec(codec, recommendations)
        self._check_sample_rate(sample_rate, recommendations)
        self._check_channels(channels, recommendations)

        # 8. Final validity
        is_valid = len(issues) == 0
        is_optimal = is_valid and len(warnings) == 0

        # Build metadata
        metadata = self._build_metadata(
            duration,
            codec,
            sample_rate,
            channels,
            bitrate,
            mean_volume,
            max_volume,
            silence_duration,
            has_voice,
        )

        # Build suggested conversion
        suggested_conversion = self._build_suggestion(is_optimal)

        return {
            "valid": is_valid,
            "optimal": is_optimal,
            "issues": issues,
            "warnings": warnings,
            "recommendations": recommendations,
            "metadata": metadata,
            "suggested_conversion": suggested_conversion,
        }

    def _probe_audio(
        self, file_path: str
    ) -> Tuple[Optional[Dict], float, str, int, int, int]:
        """Probe audio file with ffprobe."""
        cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            file_path,
        ]

        _, stdout, _ = self.ffmpeg_executor.run_ffprobe(cmd)
        info = json.loads(stdout)

        # Find audio stream
        audio_stream = None
        for stream in info.get("streams", []):
            if stream.get("codec_type") == "audio":
                audio_stream = stream
                break

        duration = float(info.get("format", {}).get("duration", 0))
        codec = audio_stream.get("codec_name", "unknown") if audio_stream else "unknown"
        sample_rate = int(audio_stream.get("sample_rate", 0)) if audio_stream else 0
        channels = int(audio_stream.get("channels", 0)) if audio_stream else 0
        bitrate = (
            int(audio_stream.get("bit_rate", 0))
            if audio_stream and audio_stream.get("bit_rate")
            else 0
        )

        return audio_stream, duration, codec, sample_rate, channels, bitrate

    def _validate_basic(
        self, duration: float, codec: str, sample_rate: int, channels: int, bitrate: int
    ) -> Tuple[list, list, list]:
        """Perform basic validations."""
        issues = []
        warnings = []
        recommendations = []

        # Duration
        if duration < self.MIN_DURATION:
            issues.append(
                f"El audio es demasiado corto (menos de {self.MIN_DURATION} segundo)"
            )
        elif duration > self.MAX_DURATION_ISSUE:
            issues.append(
                f"El audio es demasiado largo (> {self.MAX_DURATION_ISSUE / 3600:.0f} horas) para transcripción"
            )
        elif duration > self.MAX_DURATION_WARNING:
            warnings.append(
                f"El audio es muy largo (> {self.MAX_DURATION_WARNING / 3600:.0f} horas), puede tardar mucho en transcribirse"
            )

        # Sample rate
        if sample_rate < self.MIN_SAMPLE_RATE:
            issues.append(
                f"Frecuencia de muestreo demasiado baja ({sample_rate} Hz). Mínimo {self.MIN_SAMPLE_RATE} Hz"
            )
        elif sample_rate < self.RECOMMENDED_SAMPLE_RATE:
            warnings.append(
                f"Frecuencia de muestreo baja ({sample_rate} Hz). Se recomienda {self.RECOMMENDED_SAMPLE_RATE} Hz o más"
            )

        # Channels
        if channels == 0:
            issues.append("No se detectaron canales de audio")
        elif channels > 2:
            warnings.append(
                f"Audio con {channels} canales. Se convertirá a mono para transcripción"
            )

        # Bitrate
        if bitrate > 0 and bitrate < self.MIN_BITRATE:
            warnings.append(
                f"Bitrate bajo ({bitrate // 1000} kbps). La calidad podría ser insuficiente"
            )

        return issues, warnings, recommendations

    def _analyze_quality(
        self, file_path: str, duration: float
    ) -> Tuple[Optional[float], Optional[float], float]:
        """Analyze audio quality with ffmpeg filters."""
        cmd = [
            "ffmpeg",
            "-i",
            file_path,
            "-af",
            "volumedetect,silencedetect=noise=-30dB:d=0.5",
            "-f",
            "null",
            "-",
        ]

        try:
            result = self.ffmpeg_executor.run_ffmpeg(cmd, timeout=30)
            stderr = result[2]
        except Exception:
            # If quality analysis fails, return None values
            return None, None, 0.0

        mean_volume = None
        max_volume = None
        silence_duration = 0.0

        for line in stderr.split("\n"):
            if "mean_volume" in line:
                match = re.search(r"mean_volume:\s*(-?\d+\.?\d*)\s*dB", line)
                if match:
                    mean_volume = float(match.group(1))
            elif "max_volume" in line:
                match = re.search(r"max_volume:\s*(-?\d+\.?\d*)\s*dB", line)
                if match:
                    max_volume = float(match.group(1))
            elif "silence_start" in line:
                match = re.search(r"silence_duration:\s*(\d+\.?\d*)", line)
                if match:
                    silence_duration += float(match.group(1))

        return mean_volume, max_volume, silence_duration

    def _check_volume(self, mean_volume: Optional[float], issues: list, warnings: list):
        """Check volume levels."""
        if mean_volume is None:
            return

        if mean_volume < self.VOLUME_ISSUE_THRESHOLD:
            issues.append(
                f"Volumen muy bajo ({mean_volume:.1f} dB). El audio apenas se escucha"
            )
        elif mean_volume < self.VOLUME_WARNING_LOWER:
            warnings.append(
                f"Volumen bajo ({mean_volume:.1f} dB). Puede afectar la transcripción"
            )
        elif mean_volume > self.VOLUME_WARNING_UPPER:
            warnings.append(
                f"Volumen muy alto ({mean_volume:.1f} dB). Puede haber distorsión"
            )

    def _check_silence(
        self, silence_duration: float, duration: float, issues: list, warnings: list
    ):
        """Check silence ratio."""
        if duration <= 0:
            return

        silence_ratio = silence_duration / duration

        if silence_ratio > self.SILENCE_THRESHOLD:
            issues.append(
                f"Demasiado silencio en el audio ({silence_duration:.1f}s de {duration:.1f}s)"
            )
        elif silence_ratio > self.SILENCE_WARNING_THRESHOLD:
            warnings.append(
                f"Mucho silencio en el audio ({silence_duration:.1f}s de {duration:.1f}s)"
            )

    def _detect_voice(
        self, silence_duration: float, duration: float, issues: list
    ) -> bool:
        """Detect if audio likely contains voice."""
        if duration <= 0:
            return True

        silence_ratio = silence_duration / duration

        if silence_ratio > self.VOICE_DETECTION_THRESHOLD:
            issues.append("El audio parece no contener voz (demasiado silencio)")
            return False
        return True

    def _check_codec(self, codec: str, recommendations: list):
        """Check codec suitability."""
        if codec not in self.RECOMMENDED_CODECS:
            recommendations.append(
                f"El códec {codec} puede no ser óptimo. Se recomienda convertir a WAV o MP3"
            )

    def _check_sample_rate(self, sample_rate: int, recommendations: list):
        """Check sample rate."""
        if sample_rate != self.RECOMMENDED_SAMPLE_RATE:
            recommendations.append(
                "Se recomienda convertir a 16kHz para mejor rendimiento de transcripción"
            )

    def _check_channels(self, channels: int, recommendations: list):
        """Check channel count."""
        if channels != 1:
            recommendations.append("Se recomienda convertir a mono para transcripción")

    def _build_metadata(
        self,
        duration: float,
        codec: str,
        sample_rate: int,
        channels: int,
        bitrate: int,
        mean_volume: Optional[float],
        max_volume: Optional[float],
        silence_duration: float,
        has_voice: bool,
    ) -> Dict[str, Any]:
        """Build metadata dictionary."""
        return {
            "duration_seconds": duration,
            "duration_formatted": self.format_duration(duration),
            "codec": codec,
            "sample_rate_hz": sample_rate,
            "channels": channels,
            "bitrate_kbps": bitrate // 1000 if bitrate > 0 else None,
            "mean_volume_db": mean_volume,
            "max_volume_db": max_volume,
            "silence_duration_seconds": silence_duration,
            "silence_percentage": round((silence_duration / duration) * 100, 1)
            if duration > 0
            else 0,
            "has_voice": has_voice,
        }

    def _build_suggestion(self, is_optimal: bool) -> Optional[Dict[str, Any]]:
        """Build suggested conversion dict."""
        if is_optimal:
            return {"needs_conversion": False}
        return {
            "needs_conversion": True,
            "target_format": "wav",
            "target_sample_rate": 16000,
            "target_channels": 1,
            "command": "ffmpeg -i input.wav -ac 1 -ar 16000 output.wav",
        }

    def process(self, file_path: str) -> Dict[str, Any]:
        """Alias for validate to satisfy AudioService interface."""
        return self.validate(file_path)
