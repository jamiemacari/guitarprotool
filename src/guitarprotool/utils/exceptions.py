"""Custom exception classes for guitarprotool.

This module defines a hierarchy of exceptions used throughout the application
for more precise error handling and better user feedback.
"""


class GuitarProToolError(Exception):
    """Base exception for all guitarprotool errors."""

    pass


class GPFileError(GuitarProToolError):
    """Base class for errors related to Guitar Pro file handling."""

    pass


class InvalidGPFileError(GPFileError):
    """Raised when a file is not a valid Guitar Pro file."""

    pass


class GPFileCorruptedError(GPFileError):
    """Raised when a Guitar Pro file is corrupted or malformed."""

    pass


class GPExtractionError(GPFileError):
    """Raised when extraction of .gp file fails."""

    pass


class GPRepackagingError(GPFileError):
    """Raised when repackaging of .gp file fails."""

    pass


class AudioProcessingError(GuitarProToolError):
    """Base class for errors during audio download/processing."""

    pass


class DownloadError(AudioProcessingError):
    """Raised when audio download fails."""

    pass


class ConversionError(AudioProcessingError):
    """Raised when audio format conversion fails."""

    pass


class AudioValidationError(AudioProcessingError):
    """Raised when audio file validation fails."""

    pass


class BeatDetectionError(GuitarProToolError):
    """Base class for errors during beat detection."""

    pass


class BPMDetectionError(BeatDetectionError):
    """Raised when BPM detection fails."""

    pass


class XMLModificationError(GuitarProToolError):
    """Base class for errors during XML parsing/modification."""

    pass


class XMLParseError(XMLModificationError):
    """Raised when XML parsing fails."""

    pass


class XMLStructureError(XMLModificationError):
    """Raised when XML structure is not as expected."""

    pass


class XMLInjectionError(XMLModificationError):
    """Raised when injecting AudioTrack element fails."""

    pass


class ValidationError(GuitarProToolError):
    """Raised for input validation errors."""

    pass


class ConfigurationError(GuitarProToolError):
    """Raised for configuration-related errors."""

    pass
