"""Tests for GPFile class."""

import zipfile
from pathlib import Path

import pytest

from guitarprotool.core.gp_file import GPFile
from guitarprotool.utils.exceptions import (
    GPExtractionError,
    GPFileCorruptedError,
    GPRepackagingError,
    InvalidGPFileError,
)


class TestGPFileInit:
    """Test GPFile initialization."""

    def test_init_with_valid_file(self, sample_gp_file):
        """Test initialization with a valid .gp file."""
        gp = GPFile(sample_gp_file)
        assert gp.filepath == sample_gp_file
        assert not gp.is_extracted
        assert gp.temp_dir is None

    def test_init_with_nonexistent_file(self, temp_dir):
        """Test initialization with a file that doesn't exist."""
        with pytest.raises(InvalidGPFileError, match="File not found"):
            GPFile(temp_dir / "nonexistent.gp")

    def test_init_with_wrong_extension(self, temp_dir):
        """Test initialization with wrong file extension."""
        txt_file = temp_dir / "test.txt"
        txt_file.touch()

        with pytest.raises(InvalidGPFileError, match="Invalid file extension"):
            GPFile(txt_file)

    def test_init_with_path_string(self, sample_gp_file):
        """Test initialization with string path."""
        gp = GPFile(str(sample_gp_file))
        assert gp.filepath == sample_gp_file


class TestGPFileExtract:
    """Test GPFile extraction."""

    def test_extract_valid_file(self, sample_gp_file):
        """Test extracting a valid .gp file."""
        gp = GPFile(sample_gp_file)
        extract_dir = gp.extract()

        assert extract_dir.exists()
        assert gp.is_extracted
        assert gp.temp_dir == extract_dir
        assert (extract_dir / "score.gpif").exists()

        gp.cleanup()

    def test_extract_with_custom_output_dir(self, sample_gp_file, temp_dir):
        """Test extracting to a specific directory."""
        output_dir = temp_dir / "custom_extract"
        gp = GPFile(sample_gp_file)
        extract_dir = gp.extract(output_dir=output_dir)

        assert extract_dir == output_dir
        assert (output_dir / "score.gpif").exists()

        gp.cleanup()

    def test_extract_invalid_zip(self, invalid_zip_file):
        """Test extracting a file that's not a valid ZIP."""
        gp = GPFile(invalid_zip_file)

        with pytest.raises(InvalidGPFileError, match="Not a valid ZIP archive"):
            gp.extract()

    def test_extract_corrupted_gp(self, corrupted_gp_file):
        """Test extracting a .gp file without required score.gpif."""
        gp = GPFile(corrupted_gp_file)

        with pytest.raises(GPFileCorruptedError, match="structure is invalid"):
            gp.extract()

    def test_extract_already_extracted(self, sample_gp_file):
        """Test extracting a file that's already extracted."""
        gp = GPFile(sample_gp_file)
        first_extract = gp.extract()
        second_extract = gp.extract()

        assert first_extract == second_extract

        gp.cleanup()


class TestGPFileValidateStructure:
    """Test structure validation."""

    def test_validate_valid_structure(self, sample_gp_file):
        """Test validating a valid GP file structure."""
        gp = GPFile(sample_gp_file)
        gp.extract()

        assert gp.validate_structure() is True

        gp.cleanup()

    def test_validate_before_extract(self, sample_gp_file):
        """Test validating before extraction."""
        gp = GPFile(sample_gp_file)

        assert gp.validate_structure() is False


class TestGPFileGetters:
    """Test getter methods."""

    def test_get_gpif_path(self, sample_gp_file):
        """Test getting the gpif file path."""
        gp = GPFile(sample_gp_file)
        gp.extract()

        gpif_path = gp.get_gpif_path()
        assert gpif_path.exists()
        assert gpif_path.name == "score.gpif"

        gp.cleanup()

    def test_get_gpif_path_before_extract(self, sample_gp_file):
        """Test getting gpif path before extraction."""
        gp = GPFile(sample_gp_file)

        with pytest.raises(GPFileCorruptedError, match="not extracted"):
            gp.get_gpif_path()

    def test_get_audio_dir(self, sample_gp_file):
        """Test getting the audio directory."""
        gp = GPFile(sample_gp_file)
        gp.extract()

        audio_dir = gp.get_audio_dir()
        assert audio_dir.exists()
        assert audio_dir.name == "Audio"
        assert audio_dir.parent.name == "Content"

        gp.cleanup()

    def test_get_audio_dir_creates_if_missing(self, sample_gp_file):
        """Test that get_audio_dir creates the directory if it doesn't exist."""
        gp = GPFile(sample_gp_file)
        gp.extract()

        # Remove Audio directory if it exists
        audio_dir = gp.temp_dir / "Content" / "Audio"
        if audio_dir.exists():
            import shutil
            shutil.rmtree(audio_dir)

        # get_audio_dir should create it
        audio_dir = gp.get_audio_dir()
        assert audio_dir.exists()

        gp.cleanup()


class TestGPFileRepackage:
    """Test repackaging functionality."""

    def test_repackage_unmodified(self, sample_gp_file, temp_dir):
        """Test repackaging an unmodified file."""
        gp = GPFile(sample_gp_file)
        gp.extract()

        output_path = temp_dir / "repackaged.gp"
        result_path = gp.repackage(output_path)

        assert result_path.exists()
        assert result_path == output_path
        assert zipfile.is_zipfile(result_path)

        # Verify contents
        with zipfile.ZipFile(result_path, "r") as zf:
            assert "score.gpif" in zf.namelist()

        gp.cleanup()

    def test_repackage_adds_gp_extension(self, sample_gp_file, temp_dir):
        """Test that repackage adds .gp extension if missing."""
        gp = GPFile(sample_gp_file)
        gp.extract()

        output_path = temp_dir / "repackaged"
        result_path = gp.repackage(output_path)

        assert result_path.suffix == ".gp"

        gp.cleanup()

    def test_repackage_before_extract(self, sample_gp_file, temp_dir):
        """Test repackaging before extraction."""
        gp = GPFile(sample_gp_file)
        output_path = temp_dir / "output.gp"

        with pytest.raises(GPFileCorruptedError, match="not extracted"):
            gp.repackage(output_path)

    def test_repackage_with_added_audio(self, sample_gp_file, temp_dir):
        """Test repackaging after adding audio file."""
        gp = GPFile(sample_gp_file)
        gp.extract()

        # Add a fake audio file
        audio_dir = gp.get_audio_dir()
        audio_file = audio_dir / "test_audio.mp3"
        audio_file.write_bytes(b"fake audio data")

        output_path = temp_dir / "with_audio.gp"
        result_path = gp.repackage(output_path)

        # Verify audio is in the repackaged file
        with zipfile.ZipFile(result_path, "r") as zf:
            assert "Content/Audio/test_audio.mp3" in zf.namelist()

        gp.cleanup()


class TestGPFileCleanup:
    """Test cleanup functionality."""

    def test_cleanup(self, sample_gp_file):
        """Test cleanup removes temp directory."""
        gp = GPFile(sample_gp_file)
        extract_dir = gp.extract()

        assert extract_dir.exists()

        gp.cleanup()

        assert not extract_dir.exists()
        assert gp.temp_dir is None
        assert not gp.is_extracted

    def test_cleanup_without_extract(self, sample_gp_file):
        """Test cleanup before extraction doesn't error."""
        gp = GPFile(sample_gp_file)
        gp.cleanup()  # Should not raise


class TestGPFileContextManager:
    """Test context manager functionality."""

    def test_context_manager(self, sample_gp_file):
        """Test using GPFile as a context manager."""
        with GPFile(sample_gp_file) as gp:
            assert gp.is_extracted
            assert gp.temp_dir.exists()
            temp_dir = gp.temp_dir

        # After context exit, should be cleaned up
        assert not temp_dir.exists()

    def test_context_manager_with_exception(self, sample_gp_file):
        """Test context manager cleanup even with exception."""
        try:
            with GPFile(sample_gp_file) as gp:
                temp_dir = gp.temp_dir
                raise ValueError("Test exception")
        except ValueError:
            pass

        # Should still be cleaned up
        assert not temp_dir.exists()


class TestGPFileIntegration:
    """Integration tests for complete workflows."""

    def test_extract_modify_repackage(self, sample_gp_file, temp_dir):
        """Test complete workflow: extract, modify, repackage."""
        gp = GPFile(sample_gp_file)

        # Extract
        gp.extract()

        # Modify score.gpif
        gpif_path = gp.get_gpif_path()
        original_content = gpif_path.read_text()
        modified_content = original_content.replace("Test Song", "Modified Song")
        gpif_path.write_text(modified_content)

        # Repackage
        output_path = temp_dir / "modified.gp"
        gp.repackage(output_path)

        # Verify modification persisted
        gp.cleanup()

        # Re-extract the repackaged file
        gp2 = GPFile(output_path)
        gp2.extract()
        new_gpif_path = gp2.get_gpif_path()
        new_content = new_gpif_path.read_text()

        assert "Modified Song" in new_content
        assert "Test Song" not in new_content

        gp2.cleanup()
