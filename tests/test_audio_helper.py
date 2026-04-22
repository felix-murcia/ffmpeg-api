# tests/test_audio_helper.py
import os
import json
import pytest
from unittest.mock import patch, MagicMock
from modules.audio_helper.audio_converter import AudioConverter
from modules.audio_helper.audio_stream_detector import AudioStreamDetector
from modules.audio_helper.audio_info_service import AudioInfoService
from modules.audio_helper.audio_validator import AudioValidator
from modules.audio_helper.audio_cleaner import AudioCleaner
from modules.audio_helper.exceptions import AudioConversionError


class TestAudioConverter:
    """Tests for AudioConverter service."""

    def test_convert_to_wav16k_mono_success(
        self, audio_converter, mock_ffmpeg_executor, mock_file_handler
    ):
        """Test successful conversion to WAV 16kHz mono."""
        # Arrange
        input_path = "/tmp/test_input.mp3"
        temp_id = "test123"
        output_path = "/tmp/test_123.wav"
        fake_audio_data = b"fake wav audio data"

        # Mock file existence
        mock_file_handler.exists.return_value = True
        mock_file_handler.generate_temp_path.return_value = output_path

        # Mock open to simulate reading the output file
        mock_open = MagicMock()
        mock_open.return_value.__enter__ = MagicMock(
            return_value=MagicMock(read=MagicMock(return_value=fake_audio_data))
        )
        mock_open.return_value.__exit__ = MagicMock(return_value=False)

        # Act with open patched
        with patch("builtins.open", mock_open):
            audio_data, mime_type, filename = audio_converter.convert_to_wav16k_mono(
                input_path, temp_id
            )

        # Assert
        assert audio_data == fake_audio_data
        assert mime_type == "audio/wav"
        assert filename == "converted.wav"
        mock_ffmpeg_executor.run_ffmpeg.assert_called_once()
        call_args = mock_ffmpeg_executor.run_ffmpeg.call_args[0][0]
        assert "-ac" in call_args and "1" in call_args
        assert "-ar" in call_args and "16000" in call_args

    def test_convert_to_mp3_file_success(
        self, audio_converter, mock_ffmpeg_executor, mock_file_handler
    ):
        """Test successful conversion to MP3 file."""
        input_path = "/tmp/test_input.wav"
        output_path = "/tmp/test_input.mp3"
        fake_mp3_data = b"fake mp3 audio data"

        mock_file_handler.exists.return_value = True
        mock_file_handler.generate_temp_path.return_value = output_path

        # Mock open to simulate reading the output file
        mock_open = MagicMock()
        mock_open.return_value.__enter__ = MagicMock(
            return_value=MagicMock(read=MagicMock(return_value=fake_mp3_data))
        )
        mock_open.return_value.__exit__ = MagicMock(return_value=False)

        # Act
        with patch("builtins.open", mock_open):
            result_path = audio_converter.convert_to_mp3_file(
                input_path, delete_original=False
            )

        # Assert
        assert result_path == output_path
        mock_ffmpeg_executor.run_ffmpeg.assert_called_once()
        call_args = mock_ffmpeg_executor.run_ffmpeg.call_args[0][0]
        assert "-acodec" in call_args and "libmp3lame" in call_args
        assert "-b:a" in call_args and "192k" in call_args

    def test_convert_to_mp3_file_with_delete(
        self, audio_converter, mock_ffmpeg_executor, mock_file_handler
    ):
        """Test MP3 conversion with original deletion."""
        input_path = "/tmp/test_input.ogg"
        output_path = "/tmp/test_input.mp3"

        mock_file_handler.exists.return_value = True
        mock_file_handler.generate_temp_path.return_value = output_path

        # Act
        result_path = audio_converter.convert_to_mp3_file(
            input_path, delete_original=True
        )

        # Assert
        assert result_path == output_path
        mock_file_handler.cleanup.assert_called_with(input_path)

    def test_convert_to_mp3_file_input_not_found(
        self, audio_converter, mock_file_handler
    ):
        """Test MP3 conversion with non-existent input."""
        mock_file_handler.exists.return_value = False

        with pytest.raises(AudioConversionError) as excinfo:
            audio_converter.convert_to_mp3_file("/nonexistent/file.wav")

        assert "not found" in str(excinfo.value).lower()

    def test_convert_unsupported_format(self, audio_converter):
        """Test conversion with unsupported format raises error."""
        with pytest.raises(AudioConversionError) as excinfo:
            audio_converter.convert("/input.wav", "flac", "temp123")

        assert "Unsupported format" in str(excinfo.value)


class TestAudioStreamDetector:
    """Tests for AudioStreamDetector service."""

    def test_has_audio_stream_with_audio(
        self, audio_stream_detector, mock_ffmpeg_executor
    ):
        """Test detection when audio stream exists."""
        file_path = "/tmp/video_with_audio.mp4"

        # Mock file existence
        with patch("os.path.exists", return_value=True):
            # Mock returns stdout with audio indication
            mock_ffmpeg_executor.run_ffprobe.return_value = (0, "audio", "")

            # Act
            result = audio_stream_detector.has_audio_stream(file_path)

        # Assert
        assert result is True
        mock_ffmpeg_executor.run_ffprobe.assert_called_once()

    def test_has_audio_stream_without_audio(
        self, audio_stream_detector, mock_ffmpeg_executor
    ):
        """Test detection when no audio stream exists."""
        file_path = "/tmp/video_no_audio.mp4"

        with patch("os.path.exists", return_value=True):
            # Mock returns empty stdout (no audio)
            mock_ffmpeg_executor.run_ffprobe.return_value = (0, "", "")

            result = audio_stream_detector.has_audio_stream(file_path)

        assert result is False

    def test_has_audio_stream_ffprobe_fails_fallback(
        self, audio_stream_detector, mock_ffmpeg_executor
    ):
        """Test fallback when ffprobe fails."""
        file_path = "/tmp/video.mp4"

        # Make ffprobe raise exception
        mock_ffmpeg_executor.run_ffprobe.side_effect = Exception("FFprobe error")

        # Mock file exists and size > 10KB
        with (
            patch("os.path.exists", return_value=True),
            patch("os.path.getsize", return_value=15000),
        ):
            result = audio_stream_detector.has_audio_stream(file_path)

        assert result is True  # Fallback: file > 10KB

    def test_has_audio_stream_ffprobe_fails_small_file(
        self, audio_stream_detector, mock_ffmpeg_executor
    ):
        """Test fallback for small file when ffprobe fails."""
        file_path = "/tmp/tiny_video.mp4"

        mock_ffmpeg_executor.run_ffprobe.side_effect = Exception("FFprobe error")

        # Mock file exists and size < 10KB
        with (
            patch("os.path.exists", return_value=True),
            patch("os.path.getsize", return_value=5000),
        ):
            result = audio_stream_detector.has_audio_stream(file_path)

        assert result is False

    def test_has_audio_stream_nonexistent_file(self, audio_stream_detector):
        """Test detection with non-existent file."""
        result = audio_stream_detector.has_audio_stream("/nonexistent/file.mp4")
        assert result is False


class TestAudioInfoService:
    """Tests for AudioInfoService."""

    def test_get_audio_info_success(
        self, audio_info_service, mock_ffmpeg_executor, mock_file_handler
    ):
        """Test successful audio info extraction."""
        file_path = "/tmp/test_audio.mp3"

        mock_file_handler.exists.return_value = True

        # Mock ffprobe response with audio data
        mock_response = {
            "format": {"duration": "120.5"},
            "streams": [
                {
                    "codec_type": "audio",
                    "codec_name": "mp3",
                    "sample_rate": "44100",
                    "channels": "2",
                }
            ],
        }
        mock_ffmpeg_executor.run_ffprobe.return_value = (
            0,
            json.dumps(mock_response),
            "",
        )

        result = audio_info_service.get_audio_info(file_path)

        assert result["duration"] == 120.5
        assert result["codec"] == "mp3"
        assert result["sample_rate"] == "44100"
        assert result["channels"] == "2"

    def test_get_audio_info_no_audio_stream(
        self, audio_info_service, mock_ffmpeg_executor, mock_file_handler
    ):
        """Test audio info when no audio stream present."""
        file_path = "/tmp/video_only.mp4"

        mock_file_handler.exists.return_value = True
        mock_response = {
            "format": {"duration": "60.0"},
            "streams": [{"codec_type": "video"}],  # No audio
        }
        mock_ffmpeg_executor.run_ffprobe.return_value = (
            0,
            json.dumps(mock_response),
            "",
        )

        result = audio_info_service.get_audio_info(file_path)

        assert result["codec"] is None
        assert result["sample_rate"] is None
        assert result["channels"] is None


class TestAudioValidator:
    """Tests for AudioValidator service."""

    def test_validate_valid_audio(
        self, audio_validator, mock_ffmpeg_executor, mock_file_handler
    ):
        """Test validation of good quality audio."""
        file_path = "/tmp/good_audio.wav"

        mock_file_handler.exists.return_value = True

        # Mock ffprobe
        mock_probe = {
            "format": {"duration": "30.0"},
            "streams": [
                {
                    "codec_type": "audio",
                    "codec_name": "wav",
                    "sample_rate": "16000",
                    "channels": "1",
                    "bit_rate": "128000",
                }
            ],
        }
        mock_ffmpeg_executor.run_ffprobe.return_value = (0, json.dumps(mock_probe), "")

        # Mock quality analysis (no issues)
        mock_ffmpeg_executor.run_ffmpeg.return_value = (0, "", "")

        result = audio_validator.validate(file_path)

        assert result["valid"] is True
        assert result["optimal"] is True
        assert len(result["issues"]) == 0
        assert len(result["warnings"]) == 0

    def test_validate_short_audio_issue(
        self, audio_validator, mock_ffmpeg_executor, mock_file_handler
    ):
        """Test validation fails for very short audio."""
        file_path = "/tmp/short_audio.wav"

        mock_file_handler.exists.return_value = True

        mock_probe = {
            "format": {"duration": "0.5"},  # Less than 1 second
            "streams": [
                {
                    "codec_type": "audio",
                    "codec_name": "wav",
                    "sample_rate": "16000",
                    "channels": "1",
                }
            ],
        }
        mock_ffmpeg_executor.run_ffprobe.return_value = (0, json.dumps(mock_probe), "")

        result = audio_validator.validate(file_path)

        assert result["valid"] is False
        assert any("demasiado corto" in issue for issue in result["issues"])


class TestAudioCleaner:
    """Tests for AudioCleaner service."""

    def test_clean_success(self, mock_ffmpeg_executor, mock_file_handler):
        """Test successful audio cleaning."""
        from modules.audio_helper.audio_cleaner import AudioCleaner

        input_path = "/tmp/noisy_audio.mp3"
        temp_id = "test123"
        output_path = "/tmp/test_123.wav"
        fake_wav_data = b"fake cleaned wav data"

        mock_file_handler.exists.return_value = True
        mock_file_handler.get_size.return_value = 1024000
        mock_file_handler.generate_temp_path.return_value = output_path

        # Mock open to simulate reading cleaned output
        mock_open = MagicMock()
        mock_open.return_value.__enter__ = MagicMock(
            return_value=MagicMock(read=MagicMock(return_value=fake_wav_data))
        )
        mock_open.return_value.__exit__ = MagicMock(return_value=False)

        # Create service after mock configuration
        mock_logger = MagicMock()
        audio_cleaner = AudioCleaner(
            mock_ffmpeg_executor, mock_file_handler, mock_logger, timeout=60
        )

        # Act
        with patch("builtins.open", mock_open):
            audio_data, mime_type, filename = audio_cleaner.clean(input_path, temp_id)

        # Assert
        assert audio_data == fake_wav_data
        assert mime_type == "audio/wav"
        assert filename == "cleaned.wav"
        mock_ffmpeg_executor.run_ffmpeg.assert_called_once()

    def test_clean_ffmpeg_failure_returns_original(
        self, mock_ffmpeg_executor, mock_file_handler
    ):
        """Test that clean returns original file when ffmpeg fails."""
        from modules.audio_helper.audio_cleaner import AudioCleaner

        input_path = "/tmp/bad_audio.mp3"
        temp_id = "test123"
        fake_original_data = b"original audio data"

        mock_file_handler.exists.return_value = True
        # Make ffmpeg fail
        mock_ffmpeg_executor.run_ffmpeg.return_value = (1, "", "FFmpeg error")

        # Mock open to simulate reading original file
        mock_open = MagicMock()
        mock_open.return_value.__enter__ = MagicMock(
            return_value=MagicMock(read=MagicMock(return_value=fake_original_data))
        )
        mock_open.return_value.__exit__ = MagicMock(return_value=False)

        # Create service after mock configuration
        mock_logger = MagicMock()
        audio_cleaner = AudioCleaner(
            mock_ffmpeg_executor, mock_file_handler, mock_logger, timeout=60
        )

        # Act
        with patch("builtins.open", mock_open):
            audio_data, mime_type, filename = audio_cleaner.clean(input_path, temp_id)

        # Assert - should return original
        assert audio_data == fake_original_data
        assert filename == "original.wav"
