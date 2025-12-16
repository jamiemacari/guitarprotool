"""Tests for the unified format handler.

Tests format detection, GPX handling, and legacy file conversion.
"""

import tempfile
import zipfile
from pathlib import Path

import pytest

from guitarprotool.core.format_handler import (
    GPFileHandler,
    GPFormat,
    detect_format,
    get_supported_extensions,
    is_supported_format,
)
from guitarprotool.utils.exceptions import (
    FormatConversionError,
    GPFileError,
    InvalidGPFileError,
    UnsupportedFormatError,
)


class TestGPFormat:
    """Tests for the GPFormat enum."""

    def test_from_extension_with_dot(self):
        """Test format detection with leading dot."""
        assert GPFormat.from_extension(".gp") == GPFormat.GP8
        assert GPFormat.from_extension(".gpx") == GPFormat.GPX
        assert GPFormat.from_extension(".gp5") == GPFormat.GP5
        assert GPFormat.from_extension(".gp4") == GPFormat.GP4
        assert GPFormat.from_extension(".gp3") == GPFormat.GP3

    def test_from_extension_without_dot(self):
        """Test format detection without leading dot."""
        assert GPFormat.from_extension("gp") == GPFormat.GP8
        assert GPFormat.from_extension("gpx") == GPFormat.GPX
        assert GPFormat.from_extension("gp5") == GPFormat.GP5

    def test_from_extension_case_insensitive(self):
        """Test that extension detection is case insensitive."""
        assert GPFormat.from_extension(".GP") == GPFormat.GP8
        assert GPFormat.from_extension(".GPX") == GPFormat.GPX
        assert GPFormat.from_extension(".Gp5") == GPFormat.GP5

    def test_from_extension_unsupported(self):
        """Test that unsupported extensions raise error."""
        with pytest.raises(UnsupportedFormatError):
            GPFormat.from_extension(".mp3")

        with pytest.raises(UnsupportedFormatError):
            GPFormat.from_extension(".txt")

        with pytest.raises(UnsupportedFormatError):
            GPFormat.from_extension(".gp2")


class TestDetectFormat:
    """Tests for the detect_format function."""

    def test_detect_gp8(self, sample_gp_file):
        """Test detection of GP8 files."""
        fmt = detect_format(sample_gp_file)
        assert fmt == GPFormat.GP8

    def test_detect_gpx(self, temp_dir):
        """Test detection of GPX files."""
        gpx_path = temp_dir / "test.gpx"
        gpx_path.write_bytes(b"dummy content")

        fmt = detect_format(gpx_path)
        assert fmt == GPFormat.GPX

    def test_detect_gp5(self, temp_dir):
        """Test detection of GP5 files."""
        gp5_path = temp_dir / "test.gp5"
        gp5_path.write_bytes(b"dummy content")

        fmt = detect_format(gp5_path)
        assert fmt == GPFormat.GP5

    def test_detect_nonexistent_file(self, temp_dir):
        """Test that nonexistent file raises error."""
        with pytest.raises(InvalidGPFileError, match="File not found"):
            detect_format(temp_dir / "nonexistent.gp")


class TestIsSupportedFormat:
    """Tests for the is_supported_format function."""

    def test_supported_formats(self, temp_dir):
        """Test that all supported formats return True."""
        for ext in [".gp", ".gpx", ".gp5", ".gp4", ".gp3"]:
            path = temp_dir / f"test{ext}"
            assert is_supported_format(path) is True

    def test_unsupported_formats(self, temp_dir):
        """Test that unsupported formats return False."""
        for ext in [".mp3", ".txt", ".pdf", ".gp2", ".gp1"]:
            path = temp_dir / f"test{ext}"
            assert is_supported_format(path) is False


class TestGetSupportedExtensions:
    """Tests for the get_supported_extensions function."""

    def test_returns_all_extensions(self):
        """Test that all extensions are returned."""
        extensions = get_supported_extensions()

        assert ".gp" in extensions
        assert ".gpx" in extensions
        assert ".gp5" in extensions
        assert ".gp4" in extensions
        assert ".gp3" in extensions
        assert len(extensions) == 5


class TestGPFileHandler:
    """Tests for the GPFileHandler class."""

    def test_init_with_valid_gp8(self, sample_gp_file):
        """Test initialization with a valid GP8 file."""
        handler = GPFileHandler(sample_gp_file)

        assert handler.filepath == sample_gp_file
        assert handler.format == GPFormat.GP8
        assert handler.is_native_gp8 is True

    def test_init_with_nonexistent_file(self, temp_dir):
        """Test that nonexistent file raises error."""
        with pytest.raises(InvalidGPFileError):
            GPFileHandler(temp_dir / "nonexistent.gp")

    def test_init_with_unsupported_format(self, temp_dir):
        """Test that unsupported format raises error."""
        mp3_path = temp_dir / "test.mp3"
        mp3_path.write_bytes(b"fake audio")

        with pytest.raises(UnsupportedFormatError):
            GPFileHandler(mp3_path)

    def test_prepare_gp8_file(self, sample_gp_file):
        """Test preparing a GP8 file for audio injection."""
        handler = GPFileHandler(sample_gp_file)

        try:
            temp_dir = handler.prepare_for_audio_injection()

            assert temp_dir.exists()
            assert handler.get_gpif_path().exists()
            assert handler.get_audio_dir().exists()
        finally:
            handler.cleanup()

    def test_prepare_twice_returns_same_dir(self, sample_gp_file):
        """Test that preparing twice returns the same directory."""
        handler = GPFileHandler(sample_gp_file)

        try:
            dir1 = handler.prepare_for_audio_injection()
            dir2 = handler.prepare_for_audio_injection()

            assert dir1 == dir2
        finally:
            handler.cleanup()

    def test_get_gpif_before_prepare(self, sample_gp_file):
        """Test that getting gpif before prepare raises error."""
        handler = GPFileHandler(sample_gp_file)

        with pytest.raises(GPFileError, match="not prepared"):
            handler.get_gpif_path()

    def test_get_audio_dir_before_prepare(self, sample_gp_file):
        """Test that getting audio dir before prepare raises error."""
        handler = GPFileHandler(sample_gp_file)

        with pytest.raises(GPFileError, match="not prepared"):
            handler.get_audio_dir()

    def test_save_before_prepare(self, sample_gp_file, temp_dir):
        """Test that saving before prepare raises error."""
        handler = GPFileHandler(sample_gp_file)

        with pytest.raises(GPFileError, match="not prepared"):
            handler.save(temp_dir / "output.gp")

    def test_save_adds_gp_extension(self, sample_gp_file, temp_dir):
        """Test that save adds .gp extension if missing."""
        handler = GPFileHandler(sample_gp_file)

        try:
            handler.prepare_for_audio_injection()
            output_path = handler.save(temp_dir / "output")  # No extension

            assert output_path.suffix == ".gp"
            assert output_path.exists()
        finally:
            handler.cleanup()

    def test_context_manager(self, sample_gp_file):
        """Test using handler as context manager."""
        with GPFileHandler(sample_gp_file) as handler:
            assert handler.get_gpif_path().exists()
            temp_dir = handler.temp_dir

        # After context, should be cleaned up
        assert not temp_dir.exists()

    def test_cleanup(self, sample_gp_file):
        """Test that cleanup removes temp files."""
        handler = GPFileHandler(sample_gp_file)
        handler.prepare_for_audio_injection()
        temp_dir = handler.temp_dir

        assert temp_dir.exists()

        handler.cleanup()

        assert not temp_dir.exists()
        assert handler.temp_dir is None

    def test_original_format_property(self, sample_gp_file):
        """Test the original_format property."""
        handler = GPFileHandler(sample_gp_file)
        assert handler.original_format == GPFormat.GP8


class TestGPFileHandlerGPX:
    """Tests for GPX file handling."""

    @pytest.fixture
    def sample_gpx_file(self, temp_dir):
        """Create a minimal GPX file for testing.

        GPX files are BCFZ-compressed containers. For testing,
        we'd need actual BCFZ data, which is complex to generate.
        """
        gpx_path = temp_dir / "test.gpx"
        # Create a file that will fail BCFZ decompression
        # (tests error handling rather than success path)
        gpx_path.write_bytes(b"not valid bcfz data")
        return gpx_path

    def test_init_gpx(self, sample_gpx_file):
        """Test initialization with a GPX file."""
        handler = GPFileHandler(sample_gpx_file)

        assert handler.format == GPFormat.GPX
        assert handler.is_native_gp8 is False

    def test_prepare_invalid_gpx(self, sample_gpx_file):
        """Test that invalid GPX data raises error."""
        handler = GPFileHandler(sample_gpx_file)

        with pytest.raises(Exception):  # BCFZDecompressionError
            handler.prepare_for_audio_injection()


class TestGPFileHandlerLegacy:
    """Tests for legacy GP3/GP4/GP5 file handling."""

    @pytest.fixture
    def sample_gp5_file(self, temp_dir):
        """Create a minimal GP5 file for testing.

        GP5 files are binary format. For testing without pyguitarpro,
        we create a file that will trigger the import error check.
        """
        gp5_path = temp_dir / "test.gp5"
        gp5_path.write_bytes(b"FICHIER GUITAR PRO v5.00")
        return gp5_path

    def test_init_gp5(self, sample_gp5_file):
        """Test initialization with a GP5 file."""
        handler = GPFileHandler(sample_gp5_file)

        assert handler.format == GPFormat.GP5
        assert handler.is_native_gp8 is False

    def test_prepare_gp5_not_yet_supported(self, sample_gp5_file):
        """Test that GP5 handling raises a helpful error."""
        handler = GPFileHandler(sample_gp5_file)

        # GP5 → GP8 conversion is not yet supported
        with pytest.raises(FormatConversionError) as exc_info:
            handler.prepare_for_audio_injection()

        # Should provide helpful instructions
        error_msg = str(exc_info.value)
        assert "not yet supported" in error_msg.lower()
        assert "workaround" in error_msg.lower()
