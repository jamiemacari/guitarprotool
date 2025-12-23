"""Tests for the DriftAnalyzer module."""

import pytest
from guitarprotool.core.drift_analyzer import (
    DriftAnalyzer,
    DriftReport,
    DriftSeverity,
    BarDriftInfo,
)
from guitarprotool.core.beat_detector import SyncPointData
from guitarprotool.utils.exceptions import InsufficientBeatsError


class TestDriftSeverity:
    """Tests for DriftSeverity enum."""

    def test_severity_values(self):
        """Test severity enum has expected values."""
        assert DriftSeverity.STABLE.value == "stable"
        assert DriftSeverity.MINOR.value == "minor"
        assert DriftSeverity.MODERATE.value == "moderate"
        assert DriftSeverity.SIGNIFICANT.value == "significant"
        assert DriftSeverity.SEVERE.value == "severe"


class TestBarDriftInfo:
    """Tests for BarDriftInfo dataclass."""

    def test_drift_calculation(self):
        """Test drift calculations are correct."""
        info = BarDriftInfo(
            bar=0,
            expected_time=0.0,
            actual_time=0.1,
            local_tempo=122.0,
            original_tempo=120.0,
        )
        assert info.drift_seconds == pytest.approx(0.1)
        assert info.drift_percent == pytest.approx(1.67, rel=0.1)
        assert info.severity == DriftSeverity.MINOR

    def test_severity_stable(self):
        """Test stable tempo classification."""
        info = BarDriftInfo(
            bar=0,
            expected_time=0.0,
            actual_time=0.0,
            local_tempo=120.5,
            original_tempo=120.0,
        )
        assert info.severity == DriftSeverity.STABLE

    def test_severity_severe(self):
        """Test severe drift classification."""
        info = BarDriftInfo(
            bar=0,
            expected_time=0.0,
            actual_time=1.0,
            local_tempo=140.0,
            original_tempo=120.0,
        )
        assert info.severity == DriftSeverity.SEVERE


class TestDriftAnalyzerInit:
    """Tests for DriftAnalyzer initialization."""

    def test_init_requires_minimum_beats(self):
        """Test that init requires at least 4 beats."""
        with pytest.raises(InsufficientBeatsError):
            DriftAnalyzer(beat_times=[0.0, 0.5, 1.0], original_tempo=120.0)

    def test_init_with_valid_beats(self):
        """Test successful initialization."""
        beat_times = [i * 0.5 for i in range(10)]  # 120 BPM
        analyzer = DriftAnalyzer(beat_times, original_tempo=120.0)
        assert analyzer.original_tempo == 120.0
        assert analyzer.beats_per_bar == 4
        assert len(analyzer.beat_times) == 10


class TestDriftAnalyzerAnalyze:
    """Tests for DriftAnalyzer.analyze()."""

    def test_analyze_stable_tempo(self):
        """Test analysis with perfectly stable tempo."""
        # Beat times at exactly 120 BPM (0.5s per beat)
        beat_times = [i * 0.5 for i in range(100)]
        analyzer = DriftAnalyzer(beat_times, original_tempo=120.0)
        report = analyzer.analyze()

        assert report.tempo_stability_score > 0.9
        assert report.avg_drift_percent < 1.0
        assert len(report.bars_with_significant_drift) == 0

    def test_analyze_drifting_tempo(self):
        """Test analysis with tempo drift."""
        # Simulate gradual tempo increase from 120 to 130 BPM
        beat_times = []
        current_time = 0.0
        for i in range(100):
            tempo = 120.0 + (i / 100) * 10  # 120 -> 130 BPM
            interval = 60.0 / tempo
            beat_times.append(current_time)
            current_time += interval

        analyzer = DriftAnalyzer(beat_times, original_tempo=120.0)
        report = analyzer.analyze()

        assert report.tempo_stability_score < 0.9
        assert len(report.bars_with_significant_drift) > 0
        assert report.max_drift_percent > 0

    def test_analyze_returns_drift_report(self):
        """Test that analyze returns a DriftReport."""
        beat_times = [i * 0.5 for i in range(20)]
        analyzer = DriftAnalyzer(beat_times, original_tempo=120.0)
        report = analyzer.analyze()

        assert isinstance(report, DriftReport)
        assert report.total_bars_analyzed > 0


class TestDriftAnalyzerLocalTempo:
    """Tests for local tempo calculation."""

    def test_calculate_local_tempo_at_bar(self):
        """Test local tempo calculation."""
        beat_times = [i * 0.5 for i in range(20)]  # 120 BPM
        analyzer = DriftAnalyzer(beat_times, original_tempo=120.0)

        local_tempo = analyzer.calculate_local_tempo_at_bar(0)
        assert local_tempo == pytest.approx(120.0, rel=0.05)

    def test_local_tempo_beyond_beats(self):
        """Test local tempo for bar beyond detected beats."""
        beat_times = [i * 0.5 for i in range(8)]  # Only 8 beats (2 bars at 4/4)
        analyzer = DriftAnalyzer(beat_times, original_tempo=120.0)

        # Bar 10 is beyond our beats, should return original tempo
        local_tempo = analyzer.calculate_local_tempo_at_bar(10)
        assert local_tempo == 120.0


class TestDriftAnalyzerSyncPoints:
    """Tests for adaptive sync point generation."""

    def test_generate_adaptive_sync_points(self):
        """Test adaptive sync point generation."""
        beat_times = [i * 0.5 for i in range(100)]
        analyzer = DriftAnalyzer(beat_times, original_tempo=120.0)

        sync_points = analyzer.generate_adaptive_sync_points(max_bars=20, base_interval=4)

        assert len(sync_points) > 0
        assert all(isinstance(sp, SyncPointData) for sp in sync_points)
        # First sync point should be at bar 0
        assert sync_points[0].bar == 0

    def test_sync_points_have_local_tempo(self):
        """Test that sync points have local tempo values."""
        beat_times = [i * 0.5 for i in range(100)]
        analyzer = DriftAnalyzer(beat_times, original_tempo=120.0)

        sync_points = analyzer.generate_adaptive_sync_points(max_bars=20)

        for sp in sync_points:
            assert sp.modified_tempo > 0
            assert sp.original_tempo == 120.0

    def test_sync_points_frame_offset(self):
        """Test frame offset calculation."""
        beat_times = [i * 0.5 for i in range(100)]
        analyzer = DriftAnalyzer(beat_times, original_tempo=120.0)

        sync_points = analyzer.generate_adaptive_sync_points(max_bars=20)

        # Bar 0 should have frame_offset 0
        assert sync_points[0].frame_offset == 0

        # Later bars should have positive frame offsets
        if len(sync_points) > 1:
            assert sync_points[1].frame_offset > 0

    def test_frame_offset_uses_nearest_beat(self):
        """Test that frame offsets use nearest detected beat, not direct indexing.

        This is critical for handling false beat detections that would otherwise
        shift subsequent bar timings. The algorithm finds the beat nearest to
        the expected bar position based on tab tempo.
        """
        # Create beat times with tempo drift (faster than expected 120 BPM)
        # Beat at 130 BPM = 60/130 = 0.4615s per beat
        # But expected at 120 BPM = 0.5s per beat
        beat_times = [i * 0.4615 for i in range(100)]  # Actual: 130 BPM
        analyzer = DriftAnalyzer(beat_times, original_tempo=120.0)

        sync_points = analyzer.generate_adaptive_sync_points(max_bars=20, base_interval=4)

        # Find sync point at bar 4
        bar_4_sync = next((sp for sp in sync_points if sp.bar == 4), None)
        assert bar_4_sync is not None

        # Expected time at 120 BPM: 4 bars * 4 beats * 0.5s = 8.0s
        expected_position = 8.0
        expected_frame_at_120bpm = int(expected_position * 44100)  # 352800 frames

        # With nearest-beat matching, we find the beat closest to 8.0s:
        # Beat 17 at 7.846s (diff 0.154s) vs Beat 16 at 7.384s (diff 0.616s)
        # Beat 17 is closer, so we use it
        nearest_beat_time = beat_times[17] - beat_times[0]
        nearest_beat_frame = int(nearest_beat_time * 44100)

        # Frame offset should be based on NEAREST beat to expected position
        assert bar_4_sync.frame_offset == nearest_beat_frame
        # And should definitely not be the tab-tempo expected time
        assert bar_4_sync.frame_offset != expected_frame_at_120bpm

    def test_frame_offset_extrapolates_beyond_detected_beats(self):
        """Test frame offset extrapolation when bar is beyond detected beats."""
        # Only 20 beats (5 bars at 4/4, 120 BPM)
        beat_times = [i * 0.5 for i in range(20)]
        analyzer = DriftAnalyzer(beat_times, original_tempo=120.0)

        # Try to get sync point at bar 10 (beyond our 5 bars of beats)
        sync_points = analyzer.generate_adaptive_sync_points(max_bars=12, base_interval=4)

        # Find sync point at bar 8 (beyond our detected beats)
        bar_8_sync = next((sp for sp in sync_points if sp.bar == 8), None)
        assert bar_8_sync is not None

        # Should extrapolate from last known beat
        # Last beat (idx 19) is at 9.5s, bar 8 needs beat index 32
        # Extra beats: 32 - 19 = 13 beats * 0.5s = 6.5s
        # Total: 9.5s + 6.5s = 16.0s
        last_beat_time = beat_times[19] - beat_times[0]  # 9.5s
        extrapolated_time = last_beat_time + (13 * 0.5)  # 16.0s
        expected_frame = int(extrapolated_time * 44100)

        assert bar_8_sync.frame_offset == expected_frame


class TestDriftAnalyzerDebug:
    """Tests for debug output functionality."""

    def test_write_debug_beats(self, tmp_path):
        """Test debug beat data output."""
        beat_times = [i * 0.5 for i in range(20)]  # 120 BPM
        analyzer = DriftAnalyzer(beat_times, original_tempo=120.0)

        output_file = tmp_path / "debug_beats.txt"
        analyzer.write_debug_beats(str(output_file))

        assert output_file.exists()
        content = output_file.read_text()
        assert "BEAT DETECTION DEBUG DATA" in content
        assert "BEAT-BY-BEAT DATA" in content
        assert "INTERVAL STATISTICS" in content
        assert "120.00" in content  # Original tempo

    def test_write_debug_beats_with_drift(self, tmp_path):
        """Test debug output shows interval variations."""
        # Create beats with varying intervals
        beat_times = [0.0, 0.48, 1.0, 1.52, 2.0]  # Slightly varying tempo
        analyzer = DriftAnalyzer(beat_times, original_tempo=120.0)

        output_file = tmp_path / "debug_drift.txt"
        analyzer.write_debug_beats(str(output_file))

        content = output_file.read_text()
        # Should show interval variance
        assert "Interval variance:" in content


class TestDriftReport:
    """Tests for DriftReport dataclass."""

    def test_get_summary_lines(self):
        """Test summary line generation."""
        report = DriftReport(
            bar_drifts=[],
            avg_drift_percent=1.5,
            max_drift_percent=3.2,
            max_drift_bar=10,
            total_bars_analyzed=20,
            bars_with_significant_drift=[10, 15],
            tempo_stability_score=0.85,
            recommended_sync_interval=4,
        )

        lines = report.get_summary_lines()
        assert len(lines) >= 5
        assert any("20" in line for line in lines)  # Total bars
        assert any("1.5" in line or "+1.50" in line for line in lines)  # Avg drift

    def test_write_to_file(self, tmp_path):
        """Test writing drift report to file."""
        # Create sample drift info
        drift_info = BarDriftInfo(
            bar=0,
            expected_time=0.0,
            actual_time=0.0,
            local_tempo=120.0,
            original_tempo=120.0,
        )
        report = DriftReport(
            bar_drifts=[drift_info],
            avg_drift_percent=0.5,
            max_drift_percent=1.0,
            max_drift_bar=0,
            total_bars_analyzed=1,
            bars_with_significant_drift=[],
            tempo_stability_score=0.95,
            recommended_sync_interval=8,
        )

        # Write to file
        output_file = tmp_path / "drift_report.txt"
        report.write_to_file(str(output_file))

        # Verify file was created and contains expected content
        assert output_file.exists()
        content = output_file.read_text()
        assert "TEMPO DRIFT ANALYSIS REPORT" in content
        assert "BAR-BY-BAR DRIFT ANALYSIS" in content
        assert "120.00" in content  # Tab BPM
        assert "LEGEND" in content
