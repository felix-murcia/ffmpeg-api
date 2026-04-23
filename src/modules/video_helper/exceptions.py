"""
Custom exceptions for video processing.
"""


class VideoProcessingError(Exception):
    """Base exception for video processing errors."""

    pass


class VideoOptimizationError(VideoProcessingError):
    """Raised when video optimization fails."""

    pass


class VideoCreationError(VideoProcessingError):
    """Raised when video creation fails."""

    pass


class VideoValidationError(VideoProcessingError):
    """Raised when video validation fails."""

    pass


class VideoInfoError(VideoProcessingError):
    """Raised when retrieving video info fails."""

    pass


class FileNotFoundError(VideoProcessingError):
    """Raised when a file is not found."""

    pass
