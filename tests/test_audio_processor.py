"""Tests for audio_processor module."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import hashlib

import pytest
from pydub import AudioSegment
from pydub.generators import Sine

from guitarprotool.core.audio_processor import AudioProcessor, AudioInfo
from guitarprotool.utils.exceptions import (
    DownloadError,
    ConversionError,
    AudioValidationError,
)


@pytest.fixture
def audio_processor(temp_dir):
    """Create AudioProcessor instance with temp directory."""
    return AudioProcessor(output_dir=temp_dir)


@pytest.fixture
def sample_audio_file(temp_dir):
    """Create a sample audio file for testing.

    Creates a 2-second sine wave audio file in WAV format.
    """
    audio_path = temp_dir / "test_audio.wav"

    # Generate 2 seconds of 440Hz sine wave
    duration_ms = 2000
    sample_rate = 44100

    audio = Sine(440).to_audio_segment(duration=duration_ms)
    audio = audio.set_frame_rate(sample_rate)
    audio = audio.set_channels(2)  # Stereo

    audio.export(str(audio_path), format="wav")

    return audio_path


@pytest.fixture
def sample_mp3_file(temp_dir):
    """Create a sample MP3 file for testing."""
    audio_path = temp_dir / "test_audio.mp3"

    # Generate 1 second of audio
    audio = Sine(440).to_audio_segment(duration=1000)
    audio = audio.set_frame_rate(44100)
    audio = audio.set_channels(2)

    audio.export(str(audio_path), format="mp3", bitrate="192k")

    return audio_path


class TestAudioProcessorInit:
    """Test AudioProcessor initialization."""

    def test_init_with_custom_output_dir(self, temp_dir):
        """Test initialization with custom output directory."""
        custom_dir = temp_dir / "custom_output"
        processor = AudioProcessor(output_dir=custom_dir)

        assert processor.output_dir == custom_dir
        assert custom_dir.exists()

    def test_init_with_progress_callback(self, temp_dir):
        """Test initialization with progress callback."""
        callback = Mock()
        processor = AudioProcessor(output_dir=temp_dir, progress_callback=callback)

        assert processor.progress_callback == callback

    def test_init_creates_output_dir(self, temp_dir):
        """Test that output directory is created if it doesn't exist."""
        output_dir = temp_dir / "new_output_dir"
        assert not output_dir.exists()

        processor = AudioProcessor(output_dir=output_dir)

        assert output_dir.exists()
        assert output_dir.is_dir()


class TestProcessLocalFile:
    """Test processing local audio files."""

    def test_process_wav_file(self, audio_processor, sample_audio_file):
        """Test processing a WAV file."""
        audio_info = audio_processor.process_local_file(sample_audio_file)

        assert isinstance(audio_info, AudioInfo)
        assert audio_info.file_path.exists()
        assert audio_info.file_path.suffix == ".mp3"
        assert audio_info.sample_rate == 44100
        assert audio_info.channels == 2
        assert audio_info.bitrate == 192
        assert audio_info.duration_ms > 0
        assert len(audio_info.uuid) == 36  # UUID format length
        assert audio_info.title == "test_audio"

    def test_process_mp3_file(self, audio_processor, sample_mp3_file):
        """Test processing an MP3 file (should still normalize)."""
        audio_info = audio_processor.process_local_file(sample_mp3_file)

        assert isinstance(audio_info, AudioInfo)
        assert audio_info.file_path.exists()
        assert audio_info.sample_rate == 44100
        assert audio_info.channels == 2
        assert audio_info.bitrate == 192

    def test_process_with_custom_filename(self, audio_processor, sample_audio_file):
        """Test processing with custom output filename."""
        custom_name = "my_custom_audio"
        audio_info = audio_processor.process_local_file(
            sample_audio_file,
            output_filename=custom_name,
        )

        assert audio_info.file_path.exists()
        # UUID should still be used for actual filename
        assert audio_info.uuid in audio_info.file_path.name

    def test_process_nonexistent_file(self, audio_processor, temp_dir):
        """Test processing a file that doesn't exist."""
        nonexistent = temp_dir / "does_not_exist.wav"

        with pytest.raises(FileNotFoundError):
            audio_processor.process_local_file(nonexistent)

    def test_process_directory_instead_of_file(self, audio_processor, temp_dir):
        """Test processing a directory path instead of file."""
        with pytest.raises(AudioValidationError, match="not a file"):
            audio_processor.process_local_file(temp_dir)

    def test_uuid_generation_consistency(self, audio_processor, sample_audio_file):
        """Test that UUID is consistent for same file."""
        info1 = audio_processor.process_local_file(sample_audio_file)

        # Clean up first output
        info1.file_path.unlink()

        info2 = audio_processor.process_local_file(sample_audio_file)

        assert info1.uuid == info2.uuid

    def test_progress_callback_called(self, temp_dir, sample_audio_file):
        """Test that progress callback is called during processing."""
        callback = Mock()
        processor = AudioProcessor(output_dir=temp_dir, progress_callback=callback)

        processor.process_local_file(sample_audio_file)

        # Callback should be called multiple times with progress updates
        assert callback.call_count > 0
        # Check that it was called with (percent, status) arguments
        for call in callback.call_args_list:
            args = call[0]
            assert len(args) == 2
            assert isinstance(args[0], (int, float))  # percent
            assert isinstance(args[1], str)  # status


class TestProcessYouTube:
    """Test YouTube download and processing."""

    @patch('guitarprotool.core.audio_processor.yt_dlp.YoutubeDL')
    def test_process_youtube_success(self, mock_yt_dlp_class, audio_processor, sample_mp3_file):
        """Test successful YouTube download and processing."""
        # Mock yt-dlp
        mock_yt_dlp = MagicMock()
        mock_yt_dlp_class.return_value.__enter__.return_value = mock_yt_dlp

        mock_info = {
            'title': 'Test Video',
            'ext': 'mp3',
        }
        mock_yt_dlp.extract_info.return_value = mock_info

        # Copy sample MP3 to expected download location
        temp_download = audio_processor.output_dir / "temp_download.mp3"
        with open(sample_mp3_file, 'rb') as src:
            temp_download.write_bytes(src.read())

        url = "https://www.youtube.com/watch?v=test123"
        audio_info = audio_processor.process_youtube(url)

        assert isinstance(audio_info, AudioInfo)
        assert audio_info.title == "Test Video"
        assert audio_info.original_url == url
        assert audio_info.file_path.exists()
        assert mock_yt_dlp.extract_info.called

    @patch('guitarprotool.core.audio_processor.yt_dlp.YoutubeDL')
    def test_process_youtube_download_error(self, mock_yt_dlp_class, audio_processor):
        """Test handling of yt-dlp download errors."""
        import yt_dlp

        mock_yt_dlp = MagicMock()
        mock_yt_dlp_class.return_value.__enter__.return_value = mock_yt_dlp
        mock_yt_dlp.extract_info.side_effect = yt_dlp.utils.DownloadError("Network error")

        url = "https://www.youtube.com/watch?v=invalid"

        with pytest.raises(DownloadError, match="Failed to download from YouTube"):
            audio_processor.process_youtube(url)

    @patch('guitarprotool.core.audio_processor.yt_dlp.YoutubeDL')
    def test_process_youtube_no_info(self, mock_yt_dlp_class, audio_processor):
        """Test handling when yt-dlp returns no info."""
        mock_yt_dlp = MagicMock()
        mock_yt_dlp_class.return_value.__enter__.return_value = mock_yt_dlp
        mock_yt_dlp.extract_info.return_value = None

        url = "https://www.youtube.com/watch?v=test123"

        with pytest.raises(DownloadError, match="Failed to extract info"):
            audio_processor.process_youtube(url)

    @patch('guitarprotool.core.audio_processor.yt_dlp.YoutubeDL')
    def test_process_youtube_file_not_found(self, mock_yt_dlp_class, audio_processor):
        """Test handling when downloaded file is not found."""
        mock_yt_dlp = MagicMock()
        mock_yt_dlp_class.return_value.__enter__.return_value = mock_yt_dlp

        mock_info = {'title': 'Test Video'}
        mock_yt_dlp.extract_info.return_value = mock_info
        # Don't create the expected file

        url = "https://www.youtube.com/watch?v=test123"

        with pytest.raises(DownloadError, match="Downloaded file not found"):
            audio_processor.process_youtube(url)


class TestUUIDGeneration:
    """Test UUID generation."""

    def test_uuid_format(self, audio_processor, sample_audio_file):
        """Test that generated UUID has correct format."""
        uuid = audio_processor._generate_uuid(sample_audio_file)

        # UUID format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
        assert len(uuid) == 36
        assert uuid.count('-') == 4

        parts = uuid.split('-')
        assert len(parts) == 5
        assert len(parts[0]) == 8
        assert len(parts[1]) == 4
        assert len(parts[2]) == 4
        assert len(parts[3]) == 4
        assert len(parts[4]) == 12

    def test_uuid_is_valid_hex(self, audio_processor, sample_audio_file):
        """Test that UUID contains only valid hex characters."""
        uuid = audio_processor._generate_uuid(sample_audio_file)

        # Remove dashes and check if valid hex
        hex_only = uuid.replace('-', '')
        try:
            int(hex_only, 16)
        except ValueError:
            pytest.fail("UUID contains non-hex characters")

    def test_uuid_consistency(self, audio_processor, sample_audio_file):
        """Test that same file produces same UUID."""
        uuid1 = audio_processor._generate_uuid(sample_audio_file)
        uuid2 = audio_processor._generate_uuid(sample_audio_file)

        assert uuid1 == uuid2

    def test_different_files_different_uuids(self, audio_processor, temp_dir):
        """Test that different files produce different UUIDs."""
        file1 = temp_dir / "file1.txt"
        file2 = temp_dir / "file2.txt"

        file1.write_text("content 1")
        file2.write_text("content 2")

        uuid1 = audio_processor._generate_uuid(file1)
        uuid2 = audio_processor._generate_uuid(file2)

        assert uuid1 != uuid2


class TestFilenameSanitization:
    """Test filename sanitization."""

    def test_sanitize_valid_filename(self, audio_processor):
        """Test that valid filenames are unchanged."""
        valid = "My_Song-01_Mix"
        sanitized = audio_processor._sanitize_filename(valid)

        assert sanitized == valid

    def test_sanitize_removes_invalid_chars(self, audio_processor):
        """Test that invalid characters are removed."""
        invalid = 'Song: "Best Version" <Mix #1>'
        sanitized = audio_processor._sanitize_filename(invalid)

        assert '<' not in sanitized
        assert '>' not in sanitized
        assert ':' not in sanitized
        assert '"' not in sanitized
        assert '_' in sanitized  # Should be replaced with underscore

    def test_sanitize_long_filename(self, audio_processor):
        """Test that long filenames are truncated."""
        long_name = "a" * 300
        sanitized = audio_processor._sanitize_filename(long_name)

        assert len(sanitized) <= 200

    def test_sanitize_strips_whitespace(self, audio_processor):
        """Test that leading/trailing whitespace is stripped."""
        name = "  My Song  "
        sanitized = audio_processor._sanitize_filename(name)

        assert sanitized == "My Song"


class TestCleanup:
    """Test cleanup functionality."""

    def test_cleanup_removes_non_uuid_files(self, audio_processor, temp_dir):
        """Test that cleanup removes non-UUID files."""
        # Create UUID file
        uuid_file = temp_dir / "12345678-1234-1234-1234-123456789012.mp3"
        uuid_file.write_text("uuid file")

        # Create non-UUID file
        temp_file = temp_dir / "temp_download.mp3"
        temp_file.write_text("temp file")

        audio_processor.cleanup()

        assert uuid_file.exists()
        assert not temp_file.exists()

    def test_cleanup_preserves_uuid_files(self, audio_processor, temp_dir):
        """Test that cleanup preserves UUID-named files."""
        uuid_files = [
            temp_dir / "12345678-1234-1234-1234-123456789012.mp3",
            temp_dir / "abcdefab-cdef-abcd-efab-cdefabcdefab.mp3",
        ]

        for f in uuid_files:
            f.write_text("uuid file")

        audio_processor.cleanup()

        for f in uuid_files:
            assert f.exists()


class TestUUIDFilenameCheck:
    """Test UUID filename validation."""

    def test_is_uuid_filename_valid(self, audio_processor):
        """Test valid UUID filenames are recognized."""
        valid_uuids = [
            "12345678-1234-1234-1234-123456789012",
            "abcdefab-cdef-abcd-efab-cdefabcdefab",
            "00000000-0000-0000-0000-000000000000",
        ]

        for uuid in valid_uuids:
            assert audio_processor._is_uuid_filename(uuid) is True

    def test_is_uuid_filename_invalid(self, audio_processor):
        """Test invalid filenames are not recognized as UUIDs."""
        invalid = [
            "not-a-uuid",
            "12345678-1234-1234-1234",  # Too short
            "12345678-1234-1234-1234-123456789012-extra",  # Extra part
            "temp_download",
            "song_title",
        ]

        for filename in invalid:
            assert audio_processor._is_uuid_filename(filename) is False


class TestAudioInfo:
    """Test AudioInfo dataclass."""

    def test_audio_info_creation(self, temp_dir):
        """Test creating AudioInfo instance."""
        file_path = temp_dir / "test.mp3"
        file_path.write_text("fake audio")

        info = AudioInfo(
            file_path=file_path,
            uuid="12345678-1234-1234-1234-123456789012",
            duration_ms=5000,
            sample_rate=44100,
            channels=2,
            bitrate=192,
            title="Test Song",
        )

        assert info.file_path == file_path
        assert info.uuid == "12345678-1234-1234-1234-123456789012"
        assert info.duration_ms == 5000
        assert info.sample_rate == 44100
        assert info.channels == 2
        assert info.bitrate == 192
        assert info.title == "Test Song"
        assert info.original_url is None

    def test_audio_info_with_youtube_url(self, temp_dir):
        """Test AudioInfo with YouTube URL."""
        file_path = temp_dir / "test.mp3"
        file_path.write_text("fake audio")

        info = AudioInfo(
            file_path=file_path,
            uuid="12345678-1234-1234-1234-123456789012",
            duration_ms=5000,
            sample_rate=44100,
            channels=2,
            bitrate=192,
            title="Test Song",
            original_url="https://youtube.com/watch?v=abc123",
        )

        assert info.original_url == "https://youtube.com/watch?v=abc123"
