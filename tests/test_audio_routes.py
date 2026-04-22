# tests/test_audio_routes.py
import os
import io
import json
import pytest
from unittest.mock import patch, MagicMock, mock_open
from werkzeug.datastructures import FileStorage


class TestConvertToWav16k:
    """Tests for /audio/convert-to-wav16k endpoint."""

    def test_convert_success(self, client, mock_ffmpeg_executor, mock_file_handler):
        """Test successful conversion to WAV 16kHz."""
        test_data = b"fake audio data"
        fake_wav_data = b"fake wav content"

        # Mock file operations
        mock_file_handler.exists.return_value = True
        output_path = "/tmp/test_123.wav"
        mock_file_handler.generate_temp_path.return_value = output_path

        # Mock open for reading output file in audio_converter module
        m = mock_open(read_data=fake_wav_data)

        with patch("modules.audio_helper.audio_converter.open", m):
            response = client.post(
                "/audio/convert-to-wav16k",
                data={"file": (io.BytesIO(test_data), "test.mp3")},
                content_type="multipart/form-data",
            )

        assert response.status_code == 200
        assert response.headers["Content-Type"] == "audio/wav"
        assert "attachment" in response.headers.get("Content-Disposition", "")
        m.assert_called_once_with(output_path, "rb")

    def test_convert_file_too_large(self, client):
        """Test rejection of files exceeding 25MB limit."""
        large_size = (25 * 1024 * 1024) + 1
        large_data = b"x" * large_size

        response = client.post(
            "/audio/convert-to-wav16k",
            data={"file": (io.BytesIO(large_data), "large.mp3")},
            content_type="multipart/form-data",
        )

        assert response.status_code == 413
        json_data = response.get_json()
        assert "max_size_mb" in json_data
        assert json_data["max_size_mb"] == 25

    def test_convert_no_file_provided(self, client):
        """Test request without file."""
        response = client.post("/audio/convert-to-wav16k")

        assert response.status_code == 400
        assert "No se envió ningún archivo" in response.get_json()["error"]

    def test_convert_conversion_error(self, client, mock_ffmpeg_executor):
        """Test handling of conversion failure."""
        mock_ffmpeg_executor.run_ffmpeg.side_effect = Exception("FFmpeg error")

        test_data = b"fake audio"
        response = client.post(
            "/audio/convert-to-wav16k",
            data={"file": (io.BytesIO(test_data), "test.mp3")},
            content_type="multipart/form-data",
        )

        assert response.status_code == 500
        assert "FFmpeg error" in response.get_json()["error"]


class TestConvertToMp3:
    """Tests for /audio/convert-to-mp3 endpoint."""

    def test_convert_success(self, client, mock_ffmpeg_executor, mock_file_handler):
        """Test successful conversion to MP3."""
        request_data = {"path": "/tmp/audio.m4a"}

        with patch("os.path.exists", return_value=True):
            response = client.post("/audio/convert-to-mp3", json=request_data)

        assert response.status_code == 200
        json_data = response.get_json()
        assert "output" in json_data
        assert json_data["output"].endswith(".mp3")

    def test_convert_nonexistent_file(self, client):
        """Test conversion with non-existent file."""
        request_data = {"path": "/nonexistent/file.ogg"}

        with patch("os.path.exists", return_value=False):
            response = client.post("/audio/convert-to-mp3", json=request_data)

        assert response.status_code == 404
        assert "no encontrado" in response.get_json()["error"]

    def test_convert_no_path_provided(self, client):
        """Test request without path."""
        response = client.post("/audio/convert-to-mp3", json={})

        assert response.status_code == 400
        assert "Se requiere la ruta" in response.get_json()["error"]

    def test_convert_deletes_original(
        self, client, mock_ffmpeg_executor, mock_file_handler
    ):
        """Test that original file is deleted on successful conversion."""
        request_data = {"path": "/tmp/to_delete.ogg"}

        with patch("os.path.exists", return_value=True):
            response = client.post("/audio/convert-to-mp3", json=request_data)

        # Verify cleanup was called
        assert mock_file_handler.cleanup.called


class TestHasAudioStream:
    """Tests for /audio/has-audio-stream endpoint."""

    def test_has_audio_true(self, client, mock_ffmpeg_executor):
        """Test detection of audio stream."""
        request_data = {"path": "/tmp/video.mp4"}

        # Mock file exists
        with patch("os.path.exists", return_value=True):
            # Mock ffprobe to return audio
            mock_ffmpeg_executor.run_ffprobe.return_value = (0, "audio", "")

            response = client.post("/audio/has-audio-stream", json=request_data)

        assert response.status_code == 200
        assert response.get_json()["has_audio"] is True

    def test_has_audio_false(self, client, mock_ffmpeg_executor):
        """Test when no audio stream exists."""
        request_data = {"path": "/tmp/silent.mp4"}

        with patch("os.path.exists", return_value=True):
            # Mock ffprobe returns empty (no audio)
            mock_ffmpeg_executor.run_ffprobe.return_value = (0, "", "")

            response = client.post("/audio/has-audio-stream", json=request_data)

        assert response.status_code == 200
        assert response.get_json()["has_audio"] is False

    def test_has_audio_invalid_path(self, client):
        """Test with non-existent file."""
        request_data = {"path": "/nonexistent/file.mp4"}

        with patch("os.path.exists", return_value=False):
            response = client.post("/audio/has-audio-stream", json=request_data)

        assert response.status_code == 404

    def test_has_audio_no_path(self, client):
        """Test request without path."""
        response = client.post("/audio/has-audio-stream", json={})

        assert response.status_code == 400
        assert "Se requiere la ruta" in response.get_json()["error"]


class TestAudioInfoEndpoint:
    """Tests for existing /audio/info endpoint (backward compatibility)."""

    def test_info_success(self, client, mock_ffmpeg_executor):
        """Test audio info retrieval."""
        test_data = b"fake audio"

        mock_response = {
            "format": {"duration": "65.3"},
            "streams": [
                {
                    "codec_type": "audio",
                    "codec_name": "aac",
                    "sample_rate": "48000",
                    "channels": "2",
                }
            ],
        }
        mock_ffmpeg_executor.run_ffprobe.return_value = (
            0,
            json.dumps(mock_response),
            "",
        )

        response = client.post(
            "/audio/info",
            data={"file": ("test.m4a", io.BytesIO(test_data))},
            content_type="multipart/form-data",
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["duration"] == 65.3
        assert data["codec"] == "aac"
        assert data["sample_rate"] == "48000"
        assert data["channels"] == "2"

    def test_info_no_file(self, client):
        """Test info endpoint without file."""
        response = client.post("/audio/info")
        assert response.status_code == 400


class TestValidateAudioEndpoint:
    """Tests for /audio/validate endpoint."""

    def test_validate_success(self, client, mock_ffmpeg_executor):
        """Test audio validation."""
        test_data = b"fake audio"

        mock_probe = {
            "format": {"duration": "30.0"},
            "streams": [
                {
                    "codec_type": "audio",
                    "codec_name": "mp3",
                    "sample_rate": "44100",
                    "channels": "2",
                    "bit_rate": "128000",
                }
            ],
        }

        def mock_run_ffprobe(cmd, timeout=None):
            if "-show_streams" in cmd:
                return (0, json.dumps(mock_probe), "")
            return (0, "", "")

        mock_ffmpeg_executor.run_ffprobe.side_effect = mock_run_ffprobe
        mock_ffmpeg_executor.run_ffmpeg.return_value = (0, "", "")

        response = client.post(
            "/audio/validate",
            data={"file": ("test.mp3", io.BytesIO(test_data))},
            content_type="multipart/form-data",
        )

        assert response.status_code == 200
        data = response.get_json()
        assert "valid" in data
        assert "optimal" in data
        assert "issues" in data
        assert "warnings" in data
        assert "metadata" in data


class TestCleanAudioEndpoint:
    """Tests for /audio/clean endpoint."""

    def test_clean_success(self, client, mock_ffmpeg_executor, mock_file_handler):
        """Test successful audio cleaning."""
        test_data = b"fake audio"
        fake_wav_data = b"fake cleaned wav"

        # Mock successful ffmpeg
        mock_ffmpeg_executor.run_ffmpeg.return_value = (0, "", "")

        # Mock file operations
        mock_file_handler.exists.return_value = True
        mock_file_handler.get_size.return_value = 1024000
        output_path = "/tmp/test_123.wav"
        mock_file_handler.generate_temp_path.return_value = output_path

        # Mock open for reading output in audio_cleaner module
        m = mock_open(read_data=fake_wav_data)

        with patch("modules.audio_helper.audio_cleaner.open", m):
            response = client.post(
                "/audio/clean",
                data={"file": (io.BytesIO(test_data), "test.mp3")},
                content_type="multipart/form-data",
            )

        assert response.status_code == 200
        assert response.headers["Content-Type"] == "audio/wav"

    def test_clean_failure_returns_original(
        self, client, mock_ffmpeg_executor, mock_file_handler
    ):
        """Test that clean returns original file when conversion fails."""
        test_data = b"fake audio"
        fake_original_data = b"original audio data"

        # Mock ffmpeg failure
        mock_ffmpeg_executor.run_ffmpeg.return_value = (1, "", "FFmpeg error")

        # Mock file exists for input
        mock_file_handler.exists.return_value = True

        # Mock open for reading original in audio_cleaner module
        m = mock_open(read_data=fake_original_data)

        with patch("modules.audio_helper.audio_cleaner.open", m):
            response = client.post(
                "/audio/clean",
                data={"file": (io.BytesIO(test_data), "test.mp3")},
                content_type="multipart/form-data",
            )

        # Should still return 200 with original file
        assert response.status_code == 200
        assert response.headers["Content-Type"] == "audio/wav"

    def test_clean_failure_returns_original(
        self, client, mock_ffmpeg_executor, mock_file_handler
    ):
        """Test that clean returns original file when conversion fails."""
        test_data = b"fake audio"
        fake_original_data = b"original audio data"

        # Mock ffmpeg failure
        mock_ffmpeg_executor.run_ffmpeg.return_value = (1, "", "FFmpeg error")

        # Mock file exists for input
        mock_file_handler.exists.return_value = True

        # Mock open for reading original in audio_cleaner module
        m = mock_open(read_data=fake_original_data)

        with patch("modules.audio_helper.audio_cleaner.open", m):
            response = client.post(
                "/audio/clean",
                data={"file": ("test.mp3", io.BytesIO(test_data))},
                content_type="multipart/form-data",
            )

        # Should still return 200 with original file
        assert response.status_code == 200
        assert response.headers["Content-Type"] == "audio/wav"

    def test_clean_failure_returns_original(
        self, client, mock_ffmpeg_executor, mock_file_handler
    ):
        """Test that clean returns original file when conversion fails."""
        test_data = b"fake audio"
        fake_original_data = b"original audio data"

        # Mock ffmpeg failure
        mock_ffmpeg_executor.run_ffmpeg.return_value = (1, "", "FFmpeg error")

        # Mock file exists for input
        mock_file_handler.exists.return_value = True

        # Mock open for reading original
        m = mock_open(read_data=fake_original_data)

        with patch("builtins.open", m):
            response = client.post(
                "/audio/clean",
                data={"file": ("test.mp3", io.BytesIO(test_data))},
                content_type="multipart/form-data",
            )

        # Should still return 200 with original file
        assert response.status_code == 200
        assert response.headers["Content-Type"] == "audio/wav"

    def test_clean_failure_returns_original(
        self, client, mock_ffmpeg_executor, mock_file_handler
    ):
        """Test that clean returns original file when conversion fails."""
        test_data = b"fake audio"
        fake_original_data = b"original audio data"

        # Mock ffmpeg failure
        mock_ffmpeg_executor.run_ffmpeg.return_value = (1, "", "FFmpeg error")

        # Mock file exists for input
        mock_file_handler.exists.return_value = True

        # Mock open for reading original
        m = mock_open(read_data=fake_original_data)

        with patch("builtins.open", m):
            response = client.post(
                "/audio/clean",
                data={"file": (io.BytesIO(test_data), "test.mp3")},
                content_type="multipart/form-data",
            )

        # Should still return 200 with original file
        assert response.status_code == 200
        assert response.headers["Content-Type"] == "audio/wav"
        assert response.headers["Content-Type"] == "audio/wav"

    def test_clean_failure_returns_original(
        self, client, mock_ffmpeg_executor, mock_file_handler
    ):
        """Test that clean returns original file when conversion fails."""
        test_data = b"fake audio"
        fake_original_data = b"original audio data"

        # Mock ffmpeg failure
        mock_ffmpeg_executor.run_ffmpeg.return_value = (1, "", "FFmpeg error")

        # Mock file exists for input
        mock_file_handler.exists.return_value = True

        # Mock open for reading original
        mock_open = MagicMock()
        mock_open.return_value.__enter__ = MagicMock(
            return_value=MagicMock(read=MagicMock(return_value=fake_original_data))
        )
        mock_open.return_value.__exit__ = MagicMock(return_value=False)

        with patch("builtins.open", mock_open):
            response = client.post(
                "/audio/clean",
                data={"file": (io.BytesIO(test_data), "test.mp3")},
                content_type="multipart/form-data",
            )

        # Should still return 200 with original file
        assert response.status_code == 200
        assert response.headers["Content-Type"] == "audio/wav"
        assert response.headers["Content-Type"] == "audio/wav"

    def test_clean_failure_returns_original(
        self, client, mock_ffmpeg_executor, mock_file_handler
    ):
        """Test that clean returns original when conversion fails."""
        test_data = b"fake audio"

        # Simulate ffmpeg failure
        mock_ffmpeg_executor.run_ffmpeg.return_value = (1, "", "FFmpeg error")

        response = client.post(
            "/audio/clean",
            data={"file": (io.BytesIO(test_data), "test.mp3")},
            content_type="multipart/form-data",
        )

        # Should still return 200 with original file
        assert response.status_code == 200
