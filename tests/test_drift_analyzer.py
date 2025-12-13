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
