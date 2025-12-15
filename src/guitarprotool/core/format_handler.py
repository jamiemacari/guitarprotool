"""Unified format handler for multiple Guitar Pro file formats.

Supports:
- .gp (GP8) - ZIP-based, native support
- .gpx (GP6/GP7) - BCFZ compressed, requires decompression
- .gp5, .gp4, .gp3 - Binary formats, requires pyguitarpro

For audio injection, files are converted to GP8 format since that's the only
format supporting embedded audio tracks.
"""

import shutil
import tempfile
from enum import Enum
from pathlib import Path
from typing import Optional

from loguru import logger

from guitarprotool.core.bcfz import decompress_bcfz, extract_gpx_files
from guitarprotool.core.gp_file import GPFile
from guitarprotool.utils.exceptions import (
    FormatConversionError,
    GPFileError,
    InvalidGPFileError,
    UnsupportedFormatError,
)


class GPFormat(Enum):
    """Supported Guitar Pro file formats."""

    GP8 = ".gp"  # Guitar Pro 8 (ZIP-based)
    GPX = ".gpx"  # Guitar Pro 6/7 (BCFZ compressed)
    GP5 = ".gp5"  # Guitar Pro 5 (binary)
    GP4 = ".gp4"  # Guitar Pro 4 (binary)
    GP3 = ".gp3"  # Guitar Pro 3 (binary)

    @classmethod
    def from_extension(cls, ext: str) -> "GPFormat":
        """Get format from file extension.

        Args:
            ext: File extension (with or without leading dot)

        Returns:
            GPFormat enum value

        Raises:
            UnsupportedFormatError: If extension is not supported
        """
        ext = ext.lower()
        if not ext.startswith("."):
            ext = f".{ext}"

        for fmt in cls:
            if fmt.value == ext:
                return fmt

        raise UnsupportedFormatError(f"Unsupported file format: {ext}")


def detect_format(filepath: Path | str) -> GPFormat:
    """Detect the format of a Guitar Pro file.

    Args:
        filepath: Path to the file

    Returns:
        GPFormat enum value

    Raises:
        InvalidGPFileError: If file doesn't exist
        UnsupportedFormatError: If format is not supported
    """
    filepath = Path(filepath)

    if not filepath.exists():
        raise InvalidGPFileError(f"File not found: {filepath}")

    return GPFormat.from_extension(filepath.suffix)


class GPFileHandler:
    """Unified handler for all Guitar Pro file formats.

    This class provides a common interface for working with GP files
    regardless of their format. For audio injection, files are converted
    to GP8 format.

    Attributes:
        filepath: Path to the original file
        format: Detected file format
        temp_dir: Temporary directory for extracted/converted files
        gp8_file: The underlying GPFile instance (after conversion)

    Example:
        >>> handler = GPFileHandler("song.gpx")
        >>> handler.prepare_for_audio_injection()  # Converts to GP8 internally
        >>> gpif_path = handler.get_gpif_path()
        >>> audio_dir = handler.get_audio_dir()
        >>> handler.save("song_with_audio.gp")  # Always saves as GP8
    """

    def __init__(self, filepath: Path | str):
        """Initialize handler for a Guitar Pro file.

        Args:
            filepath: Path to the Guitar Pro file

        Raises:
            InvalidGPFileError: If file doesn't exist
            UnsupportedFormatError: If format is not supported
        """
        self.filepath = Path(filepath)

        if not self.filepath.exists():
            raise InvalidGPFileError(f"File not found: {self.filepath}")

        self.format = detect_format(self.filepath)
        self.temp_dir: Optional[Path] = None
        self._extract_dir: Optional[Path] = None
        self._gp8_file: Optional[GPFile] = None
        self._converted_path: Optional[Path] = None
        self._is_prepared = False

        logger.debug(f"Initialized GPFileHandler for {self.filepath} (format: {self.format.name})")

    def prepare_for_audio_injection(self) -> Path:
        """Prepare the file for audio injection.

        For GP8 files, this extracts the ZIP.
        For other formats, this converts to GP8 first.

        Returns:
            Path to the extracted temporary directory

        Raises:
            FormatConversionError: If conversion fails
            GPFileError: If extraction fails
        """
        if self._is_prepared:
            logger.warning("File already prepared, returning existing extract_dir")
            return self._extract_dir

        self.temp_dir = Path(tempfile.mkdtemp(prefix="guitarprotool_"))
        self._extract_dir = self.temp_dir / "extracted"
        logger.debug(f"Created temp directory: {self.temp_dir}")

        try:
            if self.format == GPFormat.GP8:
                self._prepare_gp8()
            elif self.format == GPFormat.GPX:
                self._prepare_gpx()
            elif self.format in (GPFormat.GP5, GPFormat.GP4, GPFormat.GP3):
                self._prepare_legacy()
            else:
                raise UnsupportedFormatError(f"No handler for format: {self.format}")

            self._is_prepared = True
            return self._extract_dir

        except Exception:
            # Cleanup on failure
            if self.temp_dir and self.temp_dir.exists():
                shutil.rmtree(self.temp_dir, ignore_errors=True)
            raise

    def _prepare_gp8(self) -> None:
        """Prepare a GP8 file (extract ZIP directly)."""
        logger.info(f"Preparing GP8 file: {self.filepath}")

        # Create a temporary GP8 file path for GPFile
        self._converted_path = self.temp_dir / "converted.gp"
        shutil.copy2(self.filepath, self._converted_path)

        # Use GPFile to extract
        self._gp8_file = GPFile(self._converted_path)
        self._gp8_file.extract(self._extract_dir)

    def _prepare_gpx(self) -> None:
        """Prepare a GPX file (decompress BCFZ, extract files, create GP8 structure)."""
        logger.info(f"Preparing GPX file: {self.filepath}")

        # Read and decompress BCFZ data
        compressed_data = self.filepath.read_bytes()
        decompressed = decompress_bcfz(compressed_data)

        # Extract files from BCFS container
        files = extract_gpx_files(decompressed)

        logger.info(f"Extracted {len(files)} files from GPX container")
        for name in files:
            logger.debug(f"  - {name}")

        # Create GP8 structure
        self._create_gp8_from_gpx(files)

    def _fix_gpx_xml(self, content: bytes) -> bytes:
        """Fix known XML issues in GPX score.gpif files.

        Some GPX files have malformed XML, such as:
        - <Parameters>...</Params> (mismatched closing tag)
        - Boolean attributes without values (e.g., accidentNatural"/>)

        Args:
            content: Raw XML content as bytes

        Returns:
            Fixed XML content as bytes
        """
        import re

        # Decode to string for manipulation
        try:
            xml_str = content.decode("utf-8")
        except UnicodeDecodeError:
            xml_str = content.decode("latin-1")

        # Fix mismatched Parameters/Params tags
        # Some GPX files have <Parameters>...</Params> instead of </Parameters>
        xml_str = xml_str.replace("</Params>", "</Parameters>")

        # Fix boolean attributes without values (with stray quote)
        # Pattern: space + attribute_name + " + /> (where there's no = before the ")
        # e.g., accidentNatural"/> becomes accidentNatural="true"/>
        # The stray " is consumed and replaced with ="true"
        xml_str = re.sub(
            r' ([a-zA-Z_][a-zA-Z0-9_]*)"(/>)',
            r' \1="true"\2',
            xml_str
        )
        xml_str = re.sub(
            r' ([a-zA-Z_][a-zA-Z0-9_]*)"( )',
            r' \1="true"\2',
            xml_str
        )

        # Re-encode to bytes
        return xml_str.encode("utf-8")

    def _create_gp8_from_gpx(self, files: dict[str, bytes]) -> None:
        """Create GP8 file structure from extracted GPX files.

        GPX files contain:
        - score.gpif (the main XML)
        - Content.xml (metadata, optional)
        - misc.xml (optional)

        We create a GP8-compatible structure.
        """
        self._extract_dir.mkdir(parents=True, exist_ok=True)

        # Find and write score.gpif
        gpif_content = None
        for name, content in files.items():
            if name.lower() == "score.gpif":
                gpif_content = content
                break

        if gpif_content is None:
            raise FormatConversionError("No score.gpif found in GPX container")

        # Fix known XML issues in GPX files
        gpif_content = self._fix_gpx_xml(gpif_content)

        # Write score.gpif to root (GP8 structure)
        gpif_path = self._extract_dir / "score.gpif"
        gpif_path.write_bytes(gpif_content)

        # Create Content directory
        content_dir = self._extract_dir / "Content"
        content_dir.mkdir(exist_ok=True)

        # Create Audio directory (for audio injection)
        audio_dir = content_dir / "Audio"
        audio_dir.mkdir(exist_ok=True)

        # Create a minimal GPFile wrapper pointing to a temporary .gp file
        self._converted_path = self.temp_dir / "converted.gp"

        # We need to create a valid .gp file that GPFile can work with
        # For now, we'll create a dummy one and set up the GPFile manually
        import zipfile

        with zipfile.ZipFile(self._converted_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("score.gpif", gpif_content)
            zf.writestr("Content/", "")

        self._gp8_file = GPFile(self._converted_path)
        self._gp8_file.temp_dir = self._extract_dir
        self._gp8_file.is_extracted = True

    def _prepare_legacy(self) -> None:
        """Prepare a legacy GP3/GP4/GP5 file.

        Note: Full GP5→GP8 conversion is not yet supported because it requires
        building the XML structure from scratch. For now, we raise a helpful error.
        """
        logger.info(f"Preparing legacy file: {self.filepath} (format: {self.format.name})")

        # GP5/GP4/GP3 → GP8 conversion is complex because:
        # 1. pyguitarpro can read GP5 but only writes GP3/GP4/GP5, not GP8
        # 2. GP8 uses XML (score.gpif) which has a different structure
        # 3. Full conversion would require mapping all Song fields to XML

        raise FormatConversionError(
            f"Direct conversion from {self.format.name} to GP8 is not yet supported.\n\n"
            f"Workaround: Open '{self.filepath.name}' in Guitar Pro 8, then:\n"
            f"  1. File → Save As\n"
            f"  2. Choose '.gp' format (Guitar Pro 8)\n"
            f"  3. Use the saved .gp file with this tool\n\n"
            f"Alternatively, if you have a .gpx version (GP6/GP7), that format is supported."
        )

    def _create_gp8_from_song(self, song) -> None:
        """Create GP8 file structure from pyguitarpro Song object.

        Args:
            song: guitarpro.Song object
        """
        try:
            import guitarpro
        except ImportError:
            raise FormatConversionError("pyguitarpro is required")

        self._extract_dir.mkdir(parents=True, exist_ok=True)

        # Create Content directory structure
        content_dir = self._extract_dir / "Content"
        content_dir.mkdir(exist_ok=True)
        audio_dir = content_dir / "Audio"
        audio_dir.mkdir(exist_ok=True)

        # Save as GP8 format using pyguitarpro
        # pyguitarpro supports saving to .gp format
        self._converted_path = self.temp_dir / "converted.gp"

        try:
            guitarpro.write(song, str(self._converted_path))
            logger.debug(f"Wrote converted GP8 file: {self._converted_path}")
        except Exception as e:
            raise FormatConversionError(f"Failed to convert to GP8 format: {e}") from e

        # Now extract the converted file
        self._gp8_file = GPFile(self._converted_path)
        self._gp8_file.extract(self._extract_dir)

    def get_gpif_path(self) -> Path:
        """Get path to the score.gpif XML file.

        Returns:
            Path to score.gpif

        Raises:
            GPFileError: If file is not prepared
        """
        if not self._is_prepared or not self._gp8_file:
            raise GPFileError("File not prepared. Call prepare_for_audio_injection() first.")

        return self._gp8_file.get_gpif_path()

    def get_audio_dir(self) -> Path:
        """Get path to the Content/Audio directory.

        Returns:
            Path to Content/Audio directory

        Raises:
            GPFileError: If file is not prepared
        """
        if not self._is_prepared or not self._gp8_file:
            raise GPFileError("File not prepared. Call prepare_for_audio_injection() first.")

        return self._gp8_file.get_audio_dir()

    def save(self, output_path: Path | str) -> Path:
        """Save the modified file as GP8 format.

        Args:
            output_path: Path for the output file (will be saved as .gp)

        Returns:
            Path to the saved file

        Raises:
            GPFileError: If file is not prepared or save fails
        """
        if not self._is_prepared or not self._gp8_file:
            raise GPFileError("File not prepared. Call prepare_for_audio_injection() first.")

        output_path = Path(output_path)

        # Ensure .gp extension
        if output_path.suffix.lower() != ".gp":
            output_path = output_path.with_suffix(".gp")

        return self._gp8_file.repackage(output_path)

    def cleanup(self) -> None:
        """Clean up temporary files and directories."""
        if self._gp8_file:
            self._gp8_file.cleanup()

        if self.temp_dir and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            self.temp_dir = None

        self._is_prepared = False
        self._gp8_file = None
        self._converted_path = None
        self._extract_dir = None

    @property
    def original_format(self) -> GPFormat:
        """Get the original file format."""
        return self.format

    @property
    def is_native_gp8(self) -> bool:
        """Check if the original file is GP8 format."""
        return self.format == GPFormat.GP8

    def __enter__(self):
        """Context manager entry: prepare file."""
        self.prepare_for_audio_injection()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit: cleanup."""
        self.cleanup()

    def __del__(self):
        """Destructor: ensure cleanup."""
        # Guard against partial initialization
        if hasattr(self, "_gp8_file"):
            self.cleanup()


def is_supported_format(filepath: Path | str) -> bool:
    """Check if a file has a supported Guitar Pro format.

    Args:
        filepath: Path to the file

    Returns:
        True if format is supported, False otherwise
    """
    filepath = Path(filepath)
    ext = filepath.suffix.lower()

    supported = {fmt.value for fmt in GPFormat}
    return ext in supported


def get_supported_extensions() -> list[str]:
    """Get list of supported file extensions.

    Returns:
        List of extensions (e.g., ['.gp', '.gpx', '.gp5', '.gp4', '.gp3'])
    """
    return [fmt.value for fmt in GPFormat]
