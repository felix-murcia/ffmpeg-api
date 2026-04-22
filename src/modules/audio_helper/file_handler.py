"""
File handler for temporary file management.
"""

import os
import uuid
import shutil
from typing import Optional


class FileHandler:
    """Handles temporary file operations for audio processing."""

    def __init__(self, temp_dir: str = "/tmp"):
        self.temp_dir = temp_dir

    def save_upload(self, file_storage, temp_id: str) -> str:
        """Save uploaded file to temporary location."""
        input_path = self.generate_temp_path(temp_id)
        file_storage.save(input_path)
        return input_path

    def save_upload_with_suffix(self, file_storage, temp_id: str, suffix: str) -> str:
        """Save uploaded file with specific suffix."""
        input_path = self.generate_temp_path(temp_id, suffix)
        file_storage.save(input_path)
        return input_path

    def copy_file(self, source_path: str, temp_id: str) -> str:
        """Copy a file to temporary location."""
        dest_path = self.generate_temp_path(temp_id, os.path.splitext(source_path)[1])
        shutil.copy2(source_path, dest_path)
        return dest_path

    def generate_temp_path(self, temp_id: str, suffix: str = "") -> str:
        """Generate a temporary file path."""
        return os.path.join(self.temp_dir, f"audio_{temp_id}{suffix}")

    def cleanup(self, *file_paths: str, raise_error: bool = False):
        """Remove temporary files."""
        for path in file_paths:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception as e:
                if raise_error:
                    raise e
                # Silently ignore cleanup errors

    def exists(self, path: str) -> bool:
        """Check if file exists."""
        return os.path.exists(path)

    def get_size(self, path: str) -> int:
        """Get file size in bytes."""
        return os.path.getsize(path)
