"""Guitar Pro file handling.

This module provides functionality to extract, validate, modify, and repackage
Guitar Pro 8 (.gp) files, which are ZIP archives containing XML and audio data.
"""

import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

from loguru import logger

from guitarprotool.utils.exceptions import (
    GPExtractionError,
    GPFileCorruptedError,
    GPRepackagingError,
    InvalidGPFileError,
)


class GPFile:
    """Handle Guitar Pro 8 file extraction, validation, and repackaging.

    Guitar Pro .gp files are ZIP archives with the following structure:
    - Content/
        - Audio/       (optional, contains audio tracks)
    - score.gpif       (main XML file with tab data)
    - other metadata files

    Attributes:
        filepath: Path to the original .gp file
        temp_dir: Temporary directory where file is extracted
        is_extracted: Whether the file has been extracted

    Example:
        >>> gp = GPFile("mysong.gp")
        >>> gp.extract()
        >>> gpif_path = gp.get_gpif_path()
        >>> # ... modify contents ...
        >>> gp.repackage("mysong_modified.gp")
        >>> gp.cleanup()
    """

    def __init__(self, filepath: Path | str):
        """Initialize GPFile handler.

        Args:
            filepath: Path to the .gp file

        Raises:
            InvalidGPFileError: If file doesn't exist or isn't a .gp file
        """
        self.filepath = Path(filepath)

        if not self.filepath.exists():
            raise InvalidGPFileError(f"File not found: {self.filepath}")

        if not self.filepath.suffix.lower() == ".gp":
            raise InvalidGPFileError(
                f"Invalid file extension: {self.filepath.suffix}. Expected .gp"
            )

        self.temp_dir: Optional[Path] = None
        self.is_extracted = False
        self._compression_info = {}

        logger.debug(f"Initialized GPFile for: {self.filepath}")

    def extract(self, output_dir: Optional[Path] = None) -> Path:
        """Extract .gp file to a temporary directory.

        Args:
            output_dir: Optional directory to extract to. If None, uses system temp dir

        Returns:
            Path to the extraction directory

        Raises:
            InvalidGPFileError: If file is not a valid ZIP archive
            GPExtractionError: If extraction fails
            GPFileCorruptedError: If required files are missing
        """
        if self.is_extracted:
            logger.warning("File already extracted, returning existing temp_dir")
            return self.temp_dir

        try:
            # Verify it's a valid ZIP file
            if not zipfile.is_zipfile(self.filepath):
                raise InvalidGPFileError(f"Not a valid ZIP archive: {self.filepath}")

            # Create temp directory
            if output_dir:
                output_dir.mkdir(parents=True, exist_ok=True)
                self.temp_dir = output_dir
            else:
                self.temp_dir = Path(tempfile.mkdtemp(prefix="guitarprotool_"))

            logger.info(f"Extracting {self.filepath} to {self.temp_dir}")

            # Extract and store compression info
            with zipfile.ZipFile(self.filepath, "r") as zip_ref:
                # Store compression info for each file (to replicate on repackaging)
                for info in zip_ref.filelist:
                    self._compression_info[info.filename] = {
                        "compress_type": info.compress_type,
                        "create_system": info.create_system,
                        "create_version": info.create_version,
                        "extract_version": info.extract_version,
                        "flag_bits": info.flag_bits,
                    }

                zip_ref.extractall(self.temp_dir)

            # Validate structure
            if not self.validate_structure():
                raise GPFileCorruptedError(
                    f"Extracted file structure is invalid. Missing required files."
                )

            self.is_extracted = True
            logger.success(f"Successfully extracted to {self.temp_dir}")
            return self.temp_dir

        except zipfile.BadZipFile as e:
            raise InvalidGPFileError(f"Corrupted ZIP file: {self.filepath}") from e
        except (InvalidGPFileError, GPFileCorruptedError):
            # Re-raise our specific exceptions without wrapping
            if self.temp_dir and self.temp_dir.exists():
                shutil.rmtree(self.temp_dir, ignore_errors=True)
            raise
        except Exception as e:
            if self.temp_dir and self.temp_dir.exists():
                shutil.rmtree(self.temp_dir, ignore_errors=True)
            raise GPExtractionError(f"Failed to extract {self.filepath}: {e}") from e

    def validate_structure(self) -> bool:
        """Validate that extracted directory has required GP file structure.

        Returns:
            True if structure is valid, False otherwise
        """
        if not self.temp_dir or not self.temp_dir.exists():
            logger.warning("Cannot validate: file not extracted")
            return False

        # Check for required score.gpif file (can be at root or in Content/)
        gpif_path = self._find_gpif_path()
        if gpif_path is None:
            logger.error("Missing required file: score.gpif")
            return False

        # Content directory should exist (may be empty)
        content_dir = self.temp_dir / "Content"
        if not content_dir.exists():
            logger.warning("Content directory not found (may be optional)")

        logger.debug("GP file structure validation passed")
        return True

    def _find_gpif_path(self) -> Optional[Path]:
        """Find the score.gpif file in the extracted directory.

        GP8 files may have score.gpif at root level or inside Content/ folder.

        Returns:
            Path to score.gpif if found, None otherwise
        """
        if not self.temp_dir:
            return None

        # Check root level first (original expected location)
        root_path = self.temp_dir / "score.gpif"
        if root_path.exists():
            return root_path

        # Check Content/ folder (alternate location found in some GP8 files)
        content_path = self.temp_dir / "Content" / "score.gpif"
        if content_path.exists():
            return content_path

        return None

    def get_gpif_path(self) -> Path:
        """Get path to the score.gpif XML file.

        Returns:
            Path to score.gpif

        Raises:
            GPFileCorruptedError: If file is not extracted or score.gpif doesn't exist
        """
        if not self.is_extracted or not self.temp_dir:
            raise GPFileCorruptedError("File not extracted. Call extract() first.")

        gpif_path = self._find_gpif_path()
        if gpif_path is None:
            raise GPFileCorruptedError("score.gpif not found in extracted files")

        return gpif_path

    def get_audio_dir(self) -> Path:
        """Get path to the Content/Audio directory (creates if doesn't exist).

        Returns:
            Path to Content/Audio directory

        Raises:
            GPFileCorruptedError: If file is not extracted
        """
        if not self.is_extracted or not self.temp_dir:
            raise GPFileCorruptedError("File not extracted. Call extract() first.")

        audio_dir = self.temp_dir / "Content" / "Audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        return audio_dir

    def repackage(self, output_path: Path | str) -> Path:
        """Repackage the extracted directory back into a .gp file.

        Args:
            output_path: Path for the output .gp file

        Returns:
            Path to the created .gp file

        Raises:
            GPFileCorruptedError: If file is not extracted
            GPRepackagingError: If repackaging fails
        """
        if not self.is_extracted or not self.temp_dir:
            raise GPFileCorruptedError("File not extracted. Call extract() first.")

        output_path = Path(output_path)

        # Ensure output has .gp extension
        if output_path.suffix.lower() != ".gp":
            output_path = output_path.with_suffix(".gp")

        try:
            logger.info(f"Repackaging to {output_path}")

            # Create parent directory if it doesn't exist
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Create new ZIP file with same compression as original
            with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zip_out:
                # Walk through all files in temp directory
                for file_path in self.temp_dir.rglob("*"):
                    if file_path.is_file():
                        # Get relative path for archive
                        arcname = file_path.relative_to(self.temp_dir)
                        arcname_str = str(arcname).replace("\\", "/")  # Normalize path separators

                        # Get compression info for this file if we have it
                        compress_type = zipfile.ZIP_DEFLATED
                        if arcname_str in self._compression_info:
                            compress_type = self._compression_info[arcname_str].get(
                                "compress_type", zipfile.ZIP_DEFLATED
                            )

                        # Add file to archive
                        zip_out.write(
                            file_path,
                            arcname=arcname_str,
                            compress_type=compress_type,
                        )

            logger.success(f"Successfully repackaged to {output_path}")
            return output_path

        except Exception as e:
            raise GPRepackagingError(f"Failed to repackage file: {e}") from e

    def cleanup(self) -> None:
        """Clean up temporary directory and extracted files."""
        if self.temp_dir and self.temp_dir.exists():
            logger.debug(f"Cleaning up temporary directory: {self.temp_dir}")
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            self.temp_dir = None
            self.is_extracted = False

    def __enter__(self):
        """Context manager entry: extract file."""
        self.extract()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit: cleanup temp files."""
        self.cleanup()

    def __del__(self):
        """Destructor: ensure cleanup on object deletion."""
        # Guard against partial initialization
        if hasattr(self, "temp_dir"):
            self.cleanup()
