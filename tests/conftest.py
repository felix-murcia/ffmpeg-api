# tests/conftest.py
import os
import sys
import pytest
from unittest.mock import MagicMock, patch

# Add src directory to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Mock flask_cors before importing modules to avoid dependency
mock_flask_cors = MagicMock()
sys.modules["flask_cors"] = mock_flask_cors
sys.modules["flask_cors.CORS"] = mock_flask_cors.CORS

# Now safe to import Flask and modules
from flask import Flask
from modules.audio_helper.audio_converter import AudioConverter
from modules.audio_helper.audio_stream_detector import AudioStreamDetector
from modules.audio_helper.audio_info_service import AudioInfoService
from modules.audio_helper.audio_validator import AudioValidator
from modules.audio_helper.audio_cleaner import AudioCleaner
from modules.audio_helper.file_handler import FileHandler
from modules.audio_helper.ffmpeg_executor import FFmpegExecutor
from modules.audio_helper.audio_stream_detector import AudioStreamDetector
from modules.audio_helper.audio_info_service import AudioInfoService
from modules.audio_helper.audio_validator import AudioValidator
from modules.audio_helper.audio_cleaner import AudioCleaner
from modules.audio_helper.file_handler import FileHandler
from modules.audio_helper.ffmpeg_executor import FFmpegExecutor


@pytest.fixture
def mock_ffmpeg_executor():
    """Mock FFmpegExecutor for isolated testing."""
    executor = MagicMock(spec=FFmpegExecutor)

    # Default run_ffprobe returns JSON with audio info (no side_effect, just return_value)
    # Tests can override executor.run_ffprobe.return_value as needed
    executor.run_ffprobe.return_value = (0, "", "")

    # Default run_ffmpeg success
    executor.run_ffmpeg.return_value = (0, "", "")

    return executor


@pytest.fixture
def mock_file_handler():
    """Mock FileHandler for isolated testing."""
    handler = MagicMock(spec=FileHandler)
    handler.save_upload.return_value = "/tmp/test_upload_123"
    handler.generate_temp_path.return_value = "/tmp/test_123"
    handler.exists.return_value = True
    handler.get_size.return_value = 1024
    handler.cleanup.return_value = None
    handler.copy_file.return_value = "/tmp/test_copy_123"
    return handler


@pytest.fixture
def audio_converter(mock_ffmpeg_executor, mock_file_handler):
    """AudioConverter instance with mocked dependencies."""
    return AudioConverter(mock_ffmpeg_executor, mock_file_handler)


@pytest.fixture
def audio_stream_detector(mock_ffmpeg_executor):
    """AudioStreamDetector instance with mocked dependencies."""
    return AudioStreamDetector(mock_ffmpeg_executor)


@pytest.fixture
def audio_info_service(mock_ffmpeg_executor, mock_file_handler):
    """AudioInfoService instance with mocked dependencies."""
    return AudioInfoService(mock_ffmpeg_executor, mock_file_handler)


@pytest.fixture
def audio_validator(mock_ffmpeg_executor, mock_file_handler):
    """AudioValidator instance with mocked dependencies."""
    return AudioValidator(
        mock_ffmpeg_executor,
        mock_file_handler,
        lambda x: f"{int(x // 60):02d}:{int(x % 60):02d}",
    )


@pytest.fixture
def audio_cleaner(mock_ffmpeg_executor, mock_file_handler):
    """AudioCleaner instance with mocked dependencies."""
    mock_logger = MagicMock()
    return AudioCleaner(
        mock_ffmpeg_executor, mock_file_handler, mock_logger, timeout=60
    )


@pytest.fixture
def app():
    """Create isolated Flask app for testing audio routes."""
    from flask import Flask
    import logging

    # Create test app
    app = Flask(__name__)
    app.config["TESTING"] = True

    # Setup logger
    logger = logging.getLogger("test-logger")
    logger.addHandler(logging.NullHandler())

    # Create real instances with mocked dependencies (will be patched later)
    file_handler = FileHandler(temp_dir="/tmp")
    ffmpeg_executor = FFmpegExecutor(logger)

    # Import and register routes
    from modules.audio_routes import register_audio_routes

    register_audio_routes(app)

    return app


@pytest.fixture
def client(app, mock_ffmpeg_executor, mock_file_handler):
    """Flask test client with dependencies mocked."""
    # Patch the global instances in audio_routes module
    with (
        patch("modules.audio_routes._ffmpeg_executor", mock_ffmpeg_executor),
        patch("modules.audio_routes._file_handler", mock_file_handler),
    ):
        with app.test_client() as client:
            yield client
