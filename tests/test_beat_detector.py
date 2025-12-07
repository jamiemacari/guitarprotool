"""Tests for beat_detector module."""

import sys
from unittest.mock import patch, MagicMock

import pytest
import numpy as np

# Mock aubio before importing beat_detector
mock_aubio = MagicMock()
sys.modules["aubio"] = mock_aubio

# ruff: noqa: E402
from guitarprotool.core.beat_detector import (
    BeatDetector,
    BeatInfo,
    SyncPointData,
    SyncResult,
)
from guitarprotool.utils.exceptions import BeatDetectionError, BPMDetectionError


@pytest.fixture
def beat_detector():
    """Create BeatDetector instance with default settings."""
    return BeatDetector()


@pytest.fixture
def mock_aubio_source():
    """Create a mock aubio source that returns audio data."""
    mock_source = MagicMock()
    mock_source.duration = 220500  # 5 seconds at 44100Hz
    mock_source.samplerate = 44100

    # Simulate reading audio in chunks
    chunks = []
    hop_s = 512
    total_samples = mock_source.duration
    for i in range(0, total_samples, hop_s):
        remaining = min(hop_s, total_samples - i)
        samples = np.zeros(hop_s, dtype=np.float32)
        chunks.append((samples, remaining if remaining < hop_s else hop_s))

    # Add final chunk with less than hop_s samples
    chunks.append((np.zeros(hop_s, dtype=np.float32), 0))

    mock_source.side_effect = chunks
    mock_source.__call__ = MagicMock(side_effect=chunks)

    return mock_source


@pytest.fixture
def mock_aubio_tempo():
    """Create a mock aubio tempo detector."""
    mock_tempo = MagicMock()

    # Track call count to simulate beat detection
    call_count = [0]

    def tempo_call(samples):
        call_count[0] += 1
        # Return beat every 21 calls (roughly every 0.5s at 512 hop)
        return 1 if call_count[0] % 21 == 0 else 0

    mock_tempo.side_effect = tempo_call
    mock_tempo.__call__ = MagicMock(side_effect=tempo_call)
    mock_tempo.get_bpm = MagicMock(return_value=120.0)

    return mock_tempo


class TestBeatDetectorInit:
    """Test BeatDetector initialization."""

    def test_init_default_parameters(self):
        """Test initialization with default parameters."""
        detector = BeatDetector()

        assert detector.sample_rate == 44100
        assert detector.win_s == 1024
        assert detector.hop_s == 512

    def test_init_custom_sample_rate(self):
        """Test initialization with custom sample rate."""
        detector = BeatDetector(sample_rate=48000)

        assert detector.sample_rate == 48000

    def test_init_custom_window_size(self):
        """Test initialization with custom window size."""
        detector = BeatDetector(win_s=2048)

        assert detector.win_s == 2048

    def test_init_custom_hop_size(self):
        """Test initialization with custom hop size."""
        detector = BeatDetector(hop_s=256)

        assert detector.hop_s == 256

    def test_init_all_custom_parameters(self):
        """Test initialization with all custom parameters."""
        detector = BeatDetector(sample_rate=22050, win_s=512, hop_s=128)

        assert detector.sample_rate == 22050
        assert detector.win_s == 512
        assert detector.hop_s == 128


class TestAnalyze:
    """Test BeatDetector.analyze() method."""

    def test_analyze_nonexistent_file(self, beat_detector, temp_dir):
        """Test analyze with file that doesn't exist."""
        nonexistent = temp_dir / "does_not_exist.wav"

        with pytest.raises(FileNotFoundError):
            beat_detector.analyze(nonexistent)

    @patch("guitarprotool.core.beat_detector.AUBIO_AVAILABLE", False)
    def test_analyze_without_aubio(self, temp_dir):
        """Test analyze raises error when aubio not available."""
        # Create a dummy file
        audio_path = temp_dir / "test.wav"
        audio_path.write_bytes(b"dummy")

        detector = BeatDetector()

        with pytest.raises(BeatDetectionError, match="aubio library not available"):
            detector.analyze(audio_path)

    @patch("guitarprotool.core.beat_detector.AUBIO_AVAILABLE", True)
    @patch("guitarprotool.core.beat_detector.aubio")
    def test_analyze_returns_beat_info(self, mock_aubio_module, temp_dir):
        """Test that analyze returns BeatInfo."""
        # Create dummy file
        audio_path = temp_dir / "test.wav"
        audio_path.write_bytes(b"dummy audio data")

        # Setup mock source
        mock_source = MagicMock()
        mock_source.duration = 220500
        mock_source.samplerate = 44100

        call_count = [0]

        def source_call():
            call_count[0] += 1
            if call_count[0] > 100:
                return (np.zeros(512, dtype=np.float32), 0)
            return (np.zeros(512, dtype=np.float32), 512)

        mock_source.side_effect = source_call
        mock_source.__call__ = MagicMock(side_effect=source_call)

        # Setup mock tempo
        mock_tempo = MagicMock()
        beat_count = [0]

        def tempo_call(samples):
            beat_count[0] += 1
            return 1 if beat_count[0] % 21 == 0 else 0

        mock_tempo.side_effect = tempo_call
        mock_tempo.__call__ = MagicMock(side_effect=tempo_call)
        mock_tempo.get_bpm = MagicMock(return_value=120.0)

        mock_aubio_module.source.return_value = mock_source
        mock_aubio_module.tempo.return_value = mock_tempo

        detector = BeatDetector()
        result = detector.analyze(audio_path)

        assert isinstance(result, BeatInfo)
        assert result.bpm > 0

    @patch("guitarprotool.core.beat_detector.AUBIO_AVAILABLE", True)
    @patch("guitarprotool.core.beat_detector.aubio")
    def test_analyze_with_progress_callback(self, mock_aubio_module, temp_dir):
        """Test analyze with progress callback."""
        audio_path = temp_dir / "test.wav"
        audio_path.write_bytes(b"dummy")

        # Setup mocks
        mock_source = MagicMock()
        mock_source.duration = 44100
        mock_source.samplerate = 44100

        call_count = [0]

        def source_call():
            call_count[0] += 1
            if call_count[0] > 50:
                return (np.zeros(512, dtype=np.float32), 0)
            return (np.zeros(512, dtype=np.float32), 512)

        mock_source.side_effect = source_call
        mock_source.__call__ = MagicMock(side_effect=source_call)

        mock_tempo = MagicMock()
        beat_count = [0]

        def tempo_call(samples):
            beat_count[0] += 1
            return 1 if beat_count[0] % 10 == 0 else 0

        mock_tempo.side_effect = tempo_call
        mock_tempo.__call__ = MagicMock(side_effect=tempo_call)
        mock_tempo.get_bpm = MagicMock(return_value=120.0)

        mock_aubio_module.source.return_value = mock_source
        mock_aubio_module.tempo.return_value = mock_tempo

        progress_values = []

        def callback(progress, message):
            progress_values.append((progress, message))

        detector = BeatDetector()
        detector.analyze(audio_path, progress_callback=callback)

        assert len(progress_values) > 0
        assert progress_values[0][0] == 0.0
        assert progress_values[-1][0] == 1.0


class TestDetectBPM:
    """Test BeatDetector.detect_bpm() method."""

    def test_detect_bpm_nonexistent_file(self, beat_detector, temp_dir):
        """Test detect_bpm with nonexistent file."""
        nonexistent = temp_dir / "does_not_exist.wav"

        with pytest.raises(FileNotFoundError):
            beat_detector.detect_bpm(nonexistent)

    @patch("guitarprotool.core.beat_detector.AUBIO_AVAILABLE", False)
    def test_detect_bpm_without_aubio(self, temp_dir):
        """Test detect_bpm raises error when aubio not available."""
        audio_path = temp_dir / "test.wav"
        audio_path.write_bytes(b"dummy")

        detector = BeatDetector()

        with pytest.raises(BPMDetectionError, match="aubio library not available"):
            detector.detect_bpm(audio_path)

    @patch("guitarprotool.core.beat_detector.AUBIO_AVAILABLE", True)
    @patch("guitarprotool.core.beat_detector.aubio")
    def test_detect_bpm_returns_float(self, mock_aubio_module, temp_dir):
        """Test that detect_bpm returns a float."""
        audio_path = temp_dir / "test.wav"
        audio_path.write_bytes(b"dummy")

        # Setup mocks
        mock_source = MagicMock()
        mock_source.duration = 44100
        mock_source.samplerate = 44100

        call_count = [0]

        def source_call():
            call_count[0] += 1
            if call_count[0] > 50:
                return (np.zeros(512, dtype=np.float32), 0)
            return (np.zeros(512, dtype=np.float32), 512)

        mock_source.side_effect = source_call
        mock_source.__call__ = MagicMock(side_effect=source_call)

        mock_tempo = MagicMock()
        beat_count = [0]

        def tempo_call(samples):
            beat_count[0] += 1
            return 1 if beat_count[0] % 10 == 0 else 0

        mock_tempo.side_effect = tempo_call
        mock_tempo.__call__ = MagicMock(side_effect=tempo_call)
        mock_tempo.get_bpm = MagicMock(return_value=120.0)

        mock_aubio_module.source.return_value = mock_source
        mock_aubio_module.tempo.return_value = mock_tempo

        detector = BeatDetector()
        bpm = detector.detect_bpm(audio_path)

        assert isinstance(bpm, float)
        assert bpm > 0


class TestGenerateSyncPoints:
    """Test BeatDetector.generate_sync_points() method."""

    @pytest.fixture
    def sample_beat_info(self):
        """Create sample BeatInfo for testing."""
        # Simulate beats at 120 BPM for 30 seconds (60 beats)
        beat_interval = 0.5  # 120 BPM
        beat_times = [i * beat_interval for i in range(60)]
        return BeatInfo(bpm=120.0, beat_times=beat_times, confidence=0.9)

    def test_generate_sync_points_returns_sync_result(self, beat_detector, sample_beat_info):
        """Test that generate_sync_points returns a SyncResult."""
        result = beat_detector.generate_sync_points(sample_beat_info, original_tempo=120.0)

        assert isinstance(result, SyncResult)
        assert isinstance(result.sync_points, list)
        assert len(result.sync_points) > 0
        assert all(isinstance(sp, SyncPointData) for sp in result.sync_points)
        assert isinstance(result.frame_padding, int)
        assert isinstance(result.first_beat_time, float)

    def test_generate_sync_points_first_bar_zero(self, beat_detector, sample_beat_info):
        """Test that first sync point is at bar 0."""
        result = beat_detector.generate_sync_points(sample_beat_info, original_tempo=120.0)

        assert result.sync_points[0].bar == 0

    def test_generate_sync_points_frame_offset_at_sample_rate(
        self, beat_detector, sample_beat_info
    ):
        """Test that frame_offset is calculated relative to first beat."""
        result = beat_detector.generate_sync_points(sample_beat_info, original_tempo=120.0)

        # Bar 0 should have frame_offset 0 (relative to first beat)
        assert result.sync_points[0].frame_offset == 0

    def test_generate_sync_points_interval(self, beat_detector, sample_beat_info):
        """Test sync points are created at correct intervals."""
        result = beat_detector.generate_sync_points(
            sample_beat_info,
            original_tempo=120.0,
            beats_per_bar=4,
            sync_interval=16,  # Every 16 beats = 4 bars
        )

        # With 60 beats and 16-beat intervals, we should have multiple sync points
        assert len(result.sync_points) >= 1

    def test_generate_sync_points_custom_interval(self, beat_detector, sample_beat_info):
        """Test sync points with custom interval."""
        result_8 = beat_detector.generate_sync_points(
            sample_beat_info, original_tempo=120.0, sync_interval=8
        )
        result_32 = beat_detector.generate_sync_points(
            sample_beat_info, original_tempo=120.0, sync_interval=32
        )

        # More frequent interval = more sync points
        assert len(result_8.sync_points) > len(result_32.sync_points)

    def test_generate_sync_points_contains_tempo(self, beat_detector, sample_beat_info):
        """Test that sync points contain tempo information."""
        result = beat_detector.generate_sync_points(sample_beat_info, original_tempo=120.0)

        for sp in result.sync_points:
            assert sp.original_tempo == 120.0
            assert sp.modified_tempo > 0

    def test_generate_sync_points_empty_beats_raises(self, beat_detector):
        """Test that empty beat list raises error."""
        empty_beat_info = BeatInfo(bpm=120.0, beat_times=[], confidence=0.5)

        with pytest.raises(BeatDetectionError, match="No beats detected"):
            beat_detector.generate_sync_points(empty_beat_info, original_tempo=120.0)

    def test_generate_sync_points_single_beat_raises(self, beat_detector):
        """Test that single beat raises error."""
        single_beat_info = BeatInfo(bpm=120.0, beat_times=[0.0], confidence=0.5)

        with pytest.raises(BeatDetectionError, match="at least 2 beats"):
            beat_detector.generate_sync_points(single_beat_info, original_tempo=120.0)

    def test_generate_sync_points_with_start_offset(self, beat_detector, sample_beat_info):
        """Test sync points with start offset."""
        result = beat_detector.generate_sync_points(
            sample_beat_info,
            original_tempo=120.0,
            start_offset=1.0,  # Additional offset of 1 second
        )

        # Frame offset for bar 0 should still be 0 (relative)
        # But frame_padding should be more negative due to offset
        assert result.sync_points[0].frame_offset == 0
        # With first beat at 0.0s + 1.0s offset, frame_padding should be -44100
        assert result.frame_padding == -44100

    def test_generate_sync_points_different_beats_per_bar(self, beat_detector):
        """Test sync points with different time signatures."""
        # 24 beats for testing
        beat_times = [i * 0.5 for i in range(24)]
        beat_info = BeatInfo(bpm=120.0, beat_times=beat_times, confidence=0.9)

        # 3/4 time (3 beats per bar)
        result_3 = beat_detector.generate_sync_points(
            beat_info,
            original_tempo=120.0,
            beats_per_bar=3,
            sync_interval=12,  # Every 4 bars
        )

        # 4/4 time (4 beats per bar)
        result_4 = beat_detector.generate_sync_points(
            beat_info,
            original_tempo=120.0,
            beats_per_bar=4,
            sync_interval=16,  # Every 4 bars
        )

        # Both should generate sync points
        assert len(result_3.sync_points) >= 1
        assert len(result_4.sync_points) >= 1

    def test_generate_sync_points_frame_padding_with_late_start(self, beat_detector):
        """Test frame_padding is calculated correctly for audio starting late."""
        # Audio with music starting at 2 seconds
        beat_times = [2.0 + i * 0.5 for i in range(20)]
        beat_info = BeatInfo(bpm=120.0, beat_times=beat_times, confidence=0.9)

        result = beat_detector.generate_sync_points(beat_info, original_tempo=120.0)

        # frame_padding should be negative, equal to -2.0 * 44100 = -88200
        assert result.frame_padding == -88200
        assert result.first_beat_time == 2.0
        # Bar 0 frame_offset should still be 0 (relative to first beat)
        assert result.sync_points[0].frame_offset == 0


class TestSyncPointData:
    """Test SyncPointData dataclass."""

    def test_sync_point_data_creation(self):
        """Test SyncPointData can be created."""
        sp = SyncPointData(
            bar=5,
            frame_offset=220500,
            modified_tempo=119.5,
            original_tempo=120.0,
        )

        assert sp.bar == 5
        assert sp.frame_offset == 220500
        assert sp.modified_tempo == 119.5
        assert sp.original_tempo == 120.0

    def test_sync_point_data_defaults(self):
        """Test SyncPointData has no default values (all required)."""
        # All fields are required
        with pytest.raises(TypeError):
            SyncPointData()  # type: ignore


class TestBeatInfo:
    """Test BeatInfo dataclass."""

    def test_beat_info_creation(self):
        """Test BeatInfo can be created."""
        info = BeatInfo(
            bpm=120.0,
            beat_times=[0.0, 0.5, 1.0],
            confidence=0.85,
        )

        assert info.bpm == 120.0
        assert info.beat_times == [0.0, 0.5, 1.0]
        assert info.confidence == 0.85

    def test_beat_info_required_fields(self):
        """Test BeatInfo requires all fields."""
        with pytest.raises(TypeError):
            BeatInfo()  # type: ignore


class TestPrivateMethods:
    """Test private helper methods."""

    def test_calculate_bpm_from_beats(self, beat_detector):
        """Test _calculate_bpm_from_beats."""
        # 120 BPM = 0.5s intervals
        beat_times = [0.0, 0.5, 1.0, 1.5, 2.0]
        bpm = beat_detector._calculate_bpm_from_beats(beat_times)

        assert 115 <= bpm <= 125  # Allow some tolerance

    def test_calculate_bpm_from_beats_empty(self, beat_detector):
        """Test _calculate_bpm_from_beats with empty list."""
        bpm = beat_detector._calculate_bpm_from_beats([])

        assert bpm == 0.0

    def test_calculate_bpm_from_beats_single(self, beat_detector):
        """Test _calculate_bpm_from_beats with single beat."""
        bpm = beat_detector._calculate_bpm_from_beats([0.0])

        assert bpm == 0.0

    def test_calculate_beat_consistency(self, beat_detector):
        """Test _calculate_beat_consistency."""
        # Perfectly consistent beats at 120 BPM
        beat_times = [i * 0.5 for i in range(10)]
        consistency = beat_detector._calculate_beat_consistency(beat_times, 120.0)

        assert 0.9 <= consistency <= 1.0

    def test_calculate_beat_consistency_inconsistent(self, beat_detector):
        """Test _calculate_beat_consistency with irregular beats."""
        # Irregular beats
        beat_times = [0.0, 0.3, 0.8, 1.0, 1.6]
        consistency = beat_detector._calculate_beat_consistency(beat_times, 120.0)

        assert consistency < 0.9

    def test_calculate_local_tempo(self, beat_detector):
        """Test _calculate_local_tempo."""
        # Beats at 120 BPM
        beat_times = [i * 0.5 for i in range(20)]
        local_tempo = beat_detector._calculate_local_tempo(beat_times, center_idx=10)

        assert 115 <= local_tempo <= 125

    def test_calculate_local_tempo_edge_start(self, beat_detector):
        """Test _calculate_local_tempo at start of beat list."""
        beat_times = [i * 0.5 for i in range(20)]
        local_tempo = beat_detector._calculate_local_tempo(beat_times, center_idx=0)

        assert local_tempo > 0

    def test_calculate_local_tempo_edge_end(self, beat_detector):
        """Test _calculate_local_tempo at end of beat list."""
        beat_times = [i * 0.5 for i in range(20)]
        local_tempo = beat_detector._calculate_local_tempo(beat_times, center_idx=19)

        assert local_tempo > 0

    def test_calculate_local_tempo_few_beats(self, beat_detector):
        """Test _calculate_local_tempo with few beats."""
        beat_times = [0.0, 0.5]
        local_tempo = beat_detector._calculate_local_tempo(beat_times, center_idx=0)

        assert local_tempo > 0


class TestIntegration:
    """Integration tests with mocked librosa."""

    def test_full_workflow(self, beat_detector):
        """Test complete workflow: analyze -> generate sync points."""
        # Create beat info manually (simulating what analyze would return)
        # This tests the workflow without needing librosa
        beat_times = [i * 0.5 for i in range(20)]  # 10 seconds at 120 BPM
        beat_info = BeatInfo(bpm=120.0, beat_times=beat_times, confidence=0.9)

        assert beat_info.bpm > 0
        assert len(beat_info.beat_times) > 0

        # Generate sync points
        result = beat_detector.generate_sync_points(
            beat_info,
            original_tempo=beat_info.bpm,
            sync_interval=8,
        )

        # Should generate at least one sync point
        assert len(result.sync_points) >= 1
        assert result.sync_points[0].bar == 0
        assert result.frame_padding == 0  # First beat at time 0

    def test_workflow_with_different_original_tempo(self, beat_detector):
        """Test workflow where original tempo differs from detected."""
        # Create beat info manually
        beat_times = [i * 0.5 for i in range(20)]  # 120 BPM beats
        beat_info = BeatInfo(bpm=120.0, beat_times=beat_times, confidence=0.9)

        # Use different original tempo
        result = beat_detector.generate_sync_points(
            beat_info,
            original_tempo=100.0,  # Different from detected
        )

        # Modified tempo should reflect detected, original should be 100
        for sp in result.sync_points:
            assert sp.original_tempo == 100.0


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_very_few_beats(self, beat_detector):
        """Test with minimum valid beats."""
        beat_times = [0.0, 0.5]  # Only 2 beats
        beat_info = BeatInfo(bpm=120.0, beat_times=beat_times, confidence=0.5)

        result = beat_detector.generate_sync_points(
            beat_info, original_tempo=120.0, sync_interval=4  # Every 1 bar
        )

        assert len(result.sync_points) >= 1

    def test_sync_points_frame_offset_calculation(self, beat_detector):
        """Test frame offset is calculated correctly (relative to first beat)."""
        beat_times = [0.0, 0.5, 1.0, 1.5]
        beat_info = BeatInfo(bpm=120.0, beat_times=beat_times, confidence=0.9)

        result = beat_detector.generate_sync_points(
            beat_info, original_tempo=120.0, sync_interval=4  # Every 1 bar
        )

        # First sync point at bar 0 has relative frame_offset 0
        assert result.sync_points[0].frame_offset == 0
        assert result.frame_padding == 0  # First beat at time 0

    def test_large_sync_interval(self, beat_detector):
        """Test with sync interval larger than beat count."""
        beat_times = [i * 0.5 for i in range(10)]  # 10 beats
        beat_info = BeatInfo(bpm=120.0, beat_times=beat_times, confidence=0.9)

        result = beat_detector.generate_sync_points(
            beat_info, original_tempo=120.0, sync_interval=100  # Larger than beat count
        )

        # Should still have at least one sync point (at bar 0)
        assert len(result.sync_points) >= 1
        assert result.sync_points[0].bar == 0
