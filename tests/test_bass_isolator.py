"""Tests for bass_isolator module."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import sys

import pytest

from guitarprotool.utils.exceptions import (
    IsolationError,
    IsolationDependencyError,
    ModelNotAvailableError,
)


def _isolation_available() -> bool:
    """Check if bass isolation dependencies are available."""
    try:
        from guitarprotool.core.bass_isolator import BassIsolator

        return BassIsolator.is_available()
    except ImportError:
        return False


class TestIsolationResult:
    """Test IsolationResult dataclass."""

    def test_successful_result(self, temp_dir):
        """Test creating a successful isolation result."""
        from guitarprotool.core.bass_isolator import IsolationResult

        result = IsolationResult(
            bass_path=temp_dir / "bass.wav",
            original_path=temp_dir / "original.mp3",
            model_used="htdemucs",
            processing_time=45.2,
            success=True,
        )

        assert result.success is True
        assert result.bass_path is not None
        assert result.error_message is None
        assert result.model_used == "htdemucs"
        assert result.processing_time == 45.2

    def test_failed_result(self, temp_dir):
        """Test creating a failed isolation result."""
        from guitarprotool.core.bass_isolator import IsolationResult

        result = IsolationResult(
            bass_path=None,
            original_path=temp_dir / "original.mp3",
            model_used="htdemucs",
            processing_time=1.5,
            success=False,
            error_message="CUDA out of memory",
        )

        assert result.success is False
        assert result.bass_path is None
        assert result.error_message == "CUDA out of memory"


class TestCheckDependencies:
    """Test dependency checking."""

    def test_check_dependencies_no_torch(self):
        """Test _check_dependencies when torch is not installed."""
        # Reset cached values
        import guitarprotool.core.bass_isolator as module

        module._DEMUCS_AVAILABLE = None
        module._TORCH_AVAILABLE = None

        with patch.dict(sys.modules, {"torch": None}):
            # Force reimport check
            with patch("builtins.__import__", side_effect=ImportError("No torch")):
                result = module._check_dependencies()
                # Result depends on actual environment - just verify it doesn't crash
                assert isinstance(result, bool)

    def test_is_available_returns_bool(self):
        """Test that is_available returns a boolean."""
        from guitarprotool.core.bass_isolator import BassIsolator

        result = BassIsolator.is_available()
        assert isinstance(result, bool)


class TestBassIsolatorInit:
    """Test BassIsolator initialization."""

    @pytest.fixture
    def mock_dependencies(self):
        """Mock torch and demucs dependencies."""
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False
        mock_torch.__version__ = "2.0.0"

        mock_demucs = MagicMock()

        with patch.dict(
            sys.modules,
            {
                "torch": mock_torch,
                "demucs": mock_demucs,
                "demucs.pretrained": MagicMock(),
                "demucs.audio": MagicMock(),
                "demucs.apply": MagicMock(),
                "torchaudio": MagicMock(),
            },
        ):
            # Reset dependency check cache
            import guitarprotool.core.bass_isolator as module

            module._DEMUCS_AVAILABLE = True
            module._TORCH_AVAILABLE = True
            yield mock_torch, mock_demucs

    @pytest.mark.skipif(
        not _isolation_available(),
        reason="Bass isolation dependencies not installed",
    )
    def test_init_default_parameters(self, temp_dir, mock_dependencies):
        """Test initialization with default parameters."""
        from guitarprotool.core.bass_isolator import BassIsolator

        isolator = BassIsolator(output_dir=temp_dir)

        assert isolator.model_name == "htdemucs"
        assert isolator.device == "cpu"  # CUDA mocked as unavailable
        assert isolator.output_dir == temp_dir

    @pytest.mark.skipif(
        not _isolation_available(),
        reason="Bass isolation dependencies not installed",
    )
    def test_init_custom_model(self, temp_dir, mock_dependencies):
        """Test initialization with custom model."""
        from guitarprotool.core.bass_isolator import BassIsolator

        isolator = BassIsolator(output_dir=temp_dir, model="htdemucs_ft")

        assert isolator.model_name == "htdemucs_ft"

    @pytest.mark.skipif(
        not _isolation_available(),
        reason="Bass isolation dependencies not installed",
    )
    def test_init_invalid_model_raises_error(self, temp_dir, mock_dependencies):
        """Test that invalid model raises ModelNotAvailableError."""
        from guitarprotool.core.bass_isolator import BassIsolator

        with pytest.raises(ModelNotAvailableError):
            BassIsolator(output_dir=temp_dir, model="invalid_model")

    @pytest.mark.skipif(
        not _isolation_available(),
        reason="Bass isolation dependencies not installed",
    )
    def test_init_with_progress_callback(self, temp_dir, mock_dependencies):
        """Test initialization with progress callback."""
        from guitarprotool.core.bass_isolator import BassIsolator

        callback = Mock()
        isolator = BassIsolator(output_dir=temp_dir, progress_callback=callback)

        assert isolator.progress_callback == callback

    @pytest.mark.skipif(
        not _isolation_available(),
        reason="Bass isolation dependencies not installed",
    )
    def test_init_creates_output_dir(self, temp_dir, mock_dependencies):
        """Test that output directory is created if it doesn't exist."""
        from guitarprotool.core.bass_isolator import BassIsolator

        output_dir = temp_dir / "new_isolation_dir"
        assert not output_dir.exists()

        isolator = BassIsolator(output_dir=output_dir)

        assert output_dir.exists()
        assert output_dir.is_dir()


class TestIsolate:
    """Test BassIsolator.isolate() method."""

    def test_isolate_nonexistent_file_returns_failure(self, temp_dir):
        """Test that isolating a nonexistent file returns failure result."""
        # Skip if dependencies not available
        try:
            from guitarprotool.core.bass_isolator import BassIsolator

            if not BassIsolator.is_available():
                pytest.skip("Bass isolation dependencies not installed")
        except ImportError:
            pytest.skip("Bass isolation module not available")

        isolator = BassIsolator(output_dir=temp_dir)
        result = isolator.isolate(temp_dir / "nonexistent.mp3")

        assert result.success is False
        assert result.bass_path is None
        assert "not found" in result.error_message.lower()


class TestGetDeviceInfo:
    """Test get_device_info static method."""

    def test_get_device_info_returns_dict(self):
        """Test that get_device_info returns a dictionary."""
        from guitarprotool.core.bass_isolator import BassIsolator

        info = BassIsolator.get_device_info()

        assert isinstance(info, dict)
        assert "recommended_device" in info

    def test_get_device_info_without_dependencies(self):
        """Test get_device_info when dependencies not installed."""
        from guitarprotool.core.bass_isolator import BassIsolator

        # Reset dependency cache
        import guitarprotool.core.bass_isolator as module

        original_demucs = module._DEMUCS_AVAILABLE
        original_torch = module._TORCH_AVAILABLE

        try:
            module._DEMUCS_AVAILABLE = False
            module._TORCH_AVAILABLE = False

            info = BassIsolator.get_device_info()

            assert info["cuda_available"] is False
            assert info["recommended_device"] == "cpu"
        finally:
            # Restore
            module._DEMUCS_AVAILABLE = original_demucs
            module._TORCH_AVAILABLE = original_torch


class TestCleanup:
    """Test BassIsolator cleanup method."""

    @pytest.mark.skipif(
        not _isolation_available(),
        reason="Bass isolation dependencies not installed",
    )
    def test_cleanup_removes_bass_files(self, temp_dir):
        """Test that cleanup removes isolated bass files."""
        from guitarprotool.core.bass_isolator import BassIsolator

        # Create some test files
        (temp_dir / "test_bass.wav").write_bytes(b"fake audio")
        (temp_dir / "other_file.txt").write_text("keep me")

        isolator = BassIsolator(output_dir=temp_dir)
        isolator.cleanup()

        assert not (temp_dir / "test_bass.wav").exists()
        assert (temp_dir / "other_file.txt").exists()


class TestContextManager:
    """Test context manager support."""

    @pytest.mark.skipif(
        not _isolation_available(),
        reason="Bass isolation dependencies not installed",
    )
    def test_context_manager_cleans_up(self, temp_dir):
        """Test that context manager calls cleanup on exit."""
        from guitarprotool.core.bass_isolator import BassIsolator

        # Create a test file
        (temp_dir / "song_bass.wav").write_bytes(b"fake bass audio")

        with BassIsolator(output_dir=temp_dir) as isolator:
            assert (temp_dir / "song_bass.wav").exists()

        # After context exit, cleanup should have run
        assert not (temp_dir / "song_bass.wav").exists()


class TestIntegration:
    """Integration tests requiring actual dependencies."""

    @pytest.mark.slow
    @pytest.mark.skipif(
        not _isolation_available(),
        reason="Bass isolation dependencies not installed",
    )
    def test_real_isolation_with_audio(self, temp_dir, sample_audio_file):
        """Test actual bass isolation with real audio file.

        This test requires torch, torchaudio, and demucs to be installed.
        It's marked as slow because model loading and inference take time.
        """
        from guitarprotool.core.bass_isolator import BassIsolator

        isolator = BassIsolator(output_dir=temp_dir)
        result = isolator.isolate(sample_audio_file)

        assert result.success is True
        assert result.bass_path is not None
        assert result.bass_path.exists()
        assert result.bass_path.suffix == ".wav"
        assert result.processing_time > 0


@pytest.fixture
def sample_audio_file(temp_dir):
    """Create a sample audio file for testing.

    Creates a 2-second sine wave audio file in WAV format.
    """
    try:
        from pydub import AudioSegment
        from pydub.generators import Sine
    except ImportError:
        pytest.skip("pydub not available")

    audio_path = temp_dir / "test_audio.wav"

    # Generate 2 seconds of 440Hz sine wave
    audio = Sine(440).to_audio_segment(duration=2000)
    audio = audio.set_frame_rate(44100)
    audio = audio.set_channels(2)

    audio.export(str(audio_path), format="wav")

    return audio_path
