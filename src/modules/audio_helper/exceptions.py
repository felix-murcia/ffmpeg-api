"""
Custom exceptions for audio processing.
"""


class AudioProcessingError(Exception):
    """Base exception for audio processing errors."""

    pass


class AudioValidationError(AudioProcessingError):
    """Raised when audio validation fails."""

    pass


class AudioConversionError(AudioProcessingError):
    """Raised when audio conversion fails."""

    pass


class AudioInfoError(AudioProcessingError):
    """Raised when retrieving audio info fails."""

    pass


class AudioCleanError(AudioProcessingError):
    """Raised when audio cleaning fails."""

    pass


class FileNotFoundError(AudioProcessingError):
    """Raised when a file is not found."""

    pass
