"""Tempo drift analysis for Guitar Pro audio synchronization.

This module analyzes tempo drift between audio recordings and tab notation,
enabling adaptive sync point placement for better alignment throughout songs
with tempo variation.
"""

from dataclasses import dataclass, field
from enum import Enum
from statistics import median
from typing import List, Optional

import numpy as np
from loguru import logger

from guitarprotool.core.beat_detector import SyncPointData
from guitarprotool.utils.exceptions import DriftAnalysisError, InsufficientBeatsError


class DriftSeverity(Enum):
    """Classification of tempo drift severity."""

    STABLE = "stable"  # < 1% drift
    MINOR = "minor"  # 1-3% drift
    MODERATE = "moderate"  # 3-5% drift
    SIGNIFICANT = "significant"  # 5-10% drift
    SEVERE = "severe"  # > 10% drift


@dataclass
class BarDriftInfo:
    """Drift information for a specific bar.

    Attributes:
        bar: Bar number (0-indexed)
        expected_time: Expected time based on tab tempo (seconds)
        actual_time: Actual time from beat detection (seconds)
        local_tempo: Detected tempo at this position (BPM)
        original_tempo: Tab tempo (BPM)
    """

    bar: int
    expected_time: float
    actual_time: float
    local_tempo: float
    original_tempo: float

    @property
    def drift_seconds(self) -> float:
        """Time drift (actual - expected) in seconds."""
        return self.actual_time - self.expected_time

    @property
    def drift_percent(self) -> float:
        """Percentage drift from expected tempo."""
        if self.original_tempo <= 0:
            return 0.0
        return ((self.local_tempo - self.original_tempo) / self.original_tempo) * 100

    @property
    def severity(self) -> DriftSeverity:
        """Classification of drift severity."""
        abs_drift = abs(self.drift_percent)
        if abs_drift < 1.0:
            return DriftSeverity.STABLE
        elif abs_drift < 3.0:
            return DriftSeverity.MINOR
        elif abs_drift < 5.0:
            return DriftSeverity.MODERATE
        elif abs_drift < 10.0:
            return DriftSeverity.SIGNIFICANT
        else:
            return DriftSeverity.SEVERE


@dataclass
class DriftReport:
    """Summary report of tempo drift analysis.

    Attributes:
        bar_drifts: Drift info for each analyzed bar
        avg_drift_percent: Average absolute drift percentage
        max_drift_percent: Maximum absolute drift percentage
        max_drift_bar: Bar with maximum drift
        total_bars_analyzed: Number of bars analyzed
        bars_with_significant_drift: Bars with >= MODERATE drift
        tempo_stability_score: 0.0-1.0 score (higher = more stable)
        recommended_sync_interval: Suggested bar interval for sync points
    """

    bar_drifts: List[BarDriftInfo]
    avg_drift_percent: float
    max_drift_percent: float
    max_drift_bar: int
    total_bars_analyzed: int
    bars_with_significant_drift: List[int]
    tempo_stability_score: float
    recommended_sync_interval: int

    def get_summary_lines(self) -> List[str]:
        """Return formatted summary lines for CLI display."""
        lines = [
            f"Bars analyzed: {self.total_bars_analyzed}",
            f"Average drift: {self.avg_drift_percent:+.2f}%",
            f"Maximum drift: {self.max_drift_percent:+.2f}% at bar {self.max_drift_bar}",
            f"Stability score: {self.tempo_stability_score:.0%}",
            f"Recommended sync interval: every {self.recommended_sync_interval} bar(s)",
        ]
        if self.bars_with_significant_drift:
            lines.append(f"Bars needing attention: {len(self.bars_with_significant_drift)}")
        return lines


class DriftAnalyzer:
    """Analyzes tempo drift between audio and tab notation.

    This class compares detected beat positions in audio against expected
    positions based on the tab's tempo, identifying where tempo varies and
    calculating appropriate modified_tempo values for sync points.

    Example:
        >>> analyzer = DriftAnalyzer(beat_times, original_tempo=120.0, beats_per_bar=4)
        >>> drift_report = analyzer.analyze()
        >>> sync_points = analyzer.generate_adaptive_sync_points(max_bars=100)

    Attributes:
        beat_times: List of detected beat times in seconds from audio
        original_tempo: Tab tempo in BPM
        beats_per_bar: Beats per bar (4 for 4/4 time)
        sample_rate: Audio sample rate (default 44100)
    """

    DEFAULT_SAMPLE_RATE = 44100

    # Thresholds for adaptive sync point placement
    DRIFT_THRESHOLD_PERCENT = 2.0  # Add sync point if drift exceeds this
    MIN_SYNC_INTERVAL = 2  # Minimum bars between sync points
    MAX_SYNC_INTERVAL = 16  # Maximum bars between sync points

    def __init__(
        self,
        beat_times: List[float],
        original_tempo: float,
        beats_per_bar: int = 4,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
    ):
        """Initialize DriftAnalyzer.

        Args:
            beat_times: List of detected beat times in seconds from audio
            original_tempo: Tab tempo in BPM
            beats_per_bar: Beats per bar (4 for 4/4 time)
            sample_rate: Audio sample rate (default 44100)

        Raises:
            InsufficientBeatsError: If not enough beats for analysis
        """
        if len(beat_times) < 4:
            raise InsufficientBeatsError(
                f"Need at least 4 beats for drift analysis, got {len(beat_times)}"
            )

        self.beat_times = beat_times
        self.original_tempo = original_tempo
        self.beats_per_bar = beats_per_bar
        self.sample_rate = sample_rate

        # Calculate expected beat interval
        self.expected_beat_interval = 60.0 / original_tempo
        self.expected_bar_duration = self.expected_beat_interval * beats_per_bar

        # First beat time is our reference point (bar 0)
        self.first_beat_time = beat_times[0]

        logger.debug(
            f"DriftAnalyzer initialized: tempo={original_tempo}, "
            f"beats={len(beat_times)}, first_beat={self.first_beat_time:.3f}s"
        )

    def analyze(self, max_bars: Optional[int] = None) -> DriftReport:
        """Analyze tempo drift across the audio.

        Args:
            max_bars: Maximum bars to analyze (None = all available)

        Returns:
            DriftReport with comprehensive drift statistics
        """
        # Estimate max bars from audio if not provided
        if max_bars is None:
            audio_duration = self.beat_times[-1] - self.first_beat_time
            max_bars = int(audio_duration / self.expected_bar_duration) + 1

        bar_drifts: List[BarDriftInfo] = []
        abs_drift_values: List[float] = []

        for bar in range(max_bars):
            drift_info = self.get_drift_at_bar(bar)
            if drift_info is not None:
                bar_drifts.append(drift_info)
                abs_drift_values.append(abs(drift_info.drift_percent))

        if not bar_drifts:
            # No bars could be analyzed
            return DriftReport(
                bar_drifts=[],
                avg_drift_percent=0.0,
                max_drift_percent=0.0,
                max_drift_bar=0,
                total_bars_analyzed=0,
                bars_with_significant_drift=[],
                tempo_stability_score=1.0,
                recommended_sync_interval=self.MAX_SYNC_INTERVAL,
            )

        # Calculate statistics
        avg_drift = sum(abs_drift_values) / len(abs_drift_values)
        max_drift = max(abs_drift_values)
        max_drift_bar = bar_drifts[abs_drift_values.index(max_drift)].bar

        # Find bars with significant drift (MODERATE or worse)
        significant_bars = [
            d.bar
            for d in bar_drifts
            if d.severity in (DriftSeverity.MODERATE, DriftSeverity.SIGNIFICANT, DriftSeverity.SEVERE)
        ]

        # Calculate stability score (0-1, higher = more stable)
        # Based on how many bars are stable or minor drift
        stable_count = sum(
            1 for d in bar_drifts if d.severity in (DriftSeverity.STABLE, DriftSeverity.MINOR)
        )
        stability_score = stable_count / len(bar_drifts) if bar_drifts else 1.0

        # Recommend sync interval based on stability
        if stability_score >= 0.9:
            recommended_interval = 8  # Very stable, can use wider intervals
        elif stability_score >= 0.7:
            recommended_interval = 4  # Mostly stable
        elif stability_score >= 0.5:
            recommended_interval = 2  # Some drift
        else:
            recommended_interval = 1  # Significant drift, sync every bar

        logger.info(
            f"Drift analysis complete: avg={avg_drift:.2f}%, max={max_drift:.2f}%, "
            f"stability={stability_score:.0%}"
        )

        return DriftReport(
            bar_drifts=bar_drifts,
            avg_drift_percent=avg_drift,
            max_drift_percent=max_drift,
            max_drift_bar=max_drift_bar,
            total_bars_analyzed=len(bar_drifts),
            bars_with_significant_drift=significant_bars,
            tempo_stability_score=stability_score,
            recommended_sync_interval=recommended_interval,
        )

    def get_drift_at_bar(self, bar: int) -> Optional[BarDriftInfo]:
        """Get drift information for a specific bar.

        Args:
            bar: Bar number (0-indexed)

        Returns:
            BarDriftInfo or None if bar is out of range
        """
        # Calculate expected time for this bar (relative to first beat)
        expected_time = bar * self.expected_bar_duration

        # Find actual time from beat detection
        beat_index = bar * self.beats_per_bar
        if beat_index >= len(self.beat_times):
            return None

        # Actual time relative to first beat
        actual_time = self.beat_times[beat_index] - self.first_beat_time

        # Calculate local tempo at this position
        local_tempo = self.calculate_local_tempo_at_bar(bar)

        return BarDriftInfo(
            bar=bar,
            expected_time=expected_time,
            actual_time=actual_time,
            local_tempo=local_tempo,
            original_tempo=self.original_tempo,
        )

    def calculate_local_tempo_at_bar(self, bar: int, window_beats: int = 8) -> float:
        """Calculate the local tempo at a specific bar position.

        Uses a sliding window of beats around the bar start to calculate
        the median tempo, which is more robust to outliers.

        Args:
            bar: Bar number (0-indexed)
            window_beats: Number of beats to consider around the bar

        Returns:
            Local tempo in BPM
        """
        # Find beat index for this bar
        beat_index = bar * self.beats_per_bar

        if beat_index >= len(self.beat_times):
            # Beyond detected beats, return original tempo
            return self.original_tempo

        # Use sliding window approach
        start_idx = max(0, beat_index - window_beats // 2)
        end_idx = min(len(self.beat_times), beat_index + window_beats // 2 + 1)

        window_beats_list = self.beat_times[start_idx:end_idx]

        if len(window_beats_list) < 2:
            return self.original_tempo

        intervals = np.diff(window_beats_list)
        if len(intervals) == 0:
            return self.original_tempo

        median_interval = median(intervals.tolist())
        if median_interval <= 0:
            return self.original_tempo

        return 60.0 / median_interval

    def generate_adaptive_sync_points(
        self,
        max_bars: int,
        base_interval: int = 4,
    ) -> List[SyncPointData]:
        """Generate sync points with adaptive frequency based on drift.

        Places more sync points where tempo drifts significantly, and fewer
        where tempo is stable. Each sync point includes the calculated
        modified_tempo for that position.

        Args:
            max_bars: Maximum bar number from GP file
            base_interval: Base interval between sync points (bars)

        Returns:
            List of SyncPointData with adaptive placement and tempo values
        """
        # Find optimal sync point positions
        positions = self._find_sync_point_positions(max_bars, base_interval)

        sync_points: List[SyncPointData] = []

        for bar in positions:
            local_tempo = self.calculate_local_tempo_at_bar(bar)
            frame_offset = self._calculate_frame_offset_for_bar(bar)

            sync_point = SyncPointData(
                bar=bar,
                frame_offset=frame_offset,
                modified_tempo=local_tempo,
                original_tempo=self.original_tempo,
            )
            sync_points.append(sync_point)

            logger.debug(
                f"Adaptive sync point: bar={bar}, frame={frame_offset}, "
                f"tempo={local_tempo:.3f} (original={self.original_tempo:.3f})"
            )

        logger.success(f"Generated {len(sync_points)} adaptive sync points")
        return sync_points

    def _find_sync_point_positions(
        self,
        max_bars: int,
        base_interval: int,
    ) -> List[int]:
        """Determine optimal bar positions for sync points.

        Algorithm:
        1. Always place sync point at bar 0
        2. Evaluate drift at each bar
        3. If drift exceeds threshold, add sync point
        4. Ensure minimum spacing between sync points
        5. Never exceed max_interval without a sync point

        Args:
            max_bars: Maximum bar number
            base_interval: Base interval between sync points

        Returns:
            List of bar numbers for sync point placement
        """
        positions = [0]  # Always start at bar 0
        last_sync_bar = 0

        for bar in range(1, max_bars):
            bars_since_last = bar - last_sync_bar

            # Check if we must place a sync point (max interval reached)
            if bars_since_last >= self.MAX_SYNC_INTERVAL:
                positions.append(bar)
                last_sync_bar = bar
                continue

            # Check if drift threshold exceeded (and min interval passed)
            if bars_since_last >= self.MIN_SYNC_INTERVAL:
                drift_info = self.get_drift_at_bar(bar)
                if drift_info and abs(drift_info.drift_percent) >= self.DRIFT_THRESHOLD_PERCENT:
                    positions.append(bar)
                    last_sync_bar = bar
                    continue

            # Check if base interval reached
            if bars_since_last >= base_interval:
                positions.append(bar)
                last_sync_bar = bar

        return positions

    def _calculate_frame_offset_for_bar(self, bar: int) -> int:
        """Calculate audio frame offset for a given bar.

        Frame offsets are relative to the first beat (bar 0 = frame 0),
        calculated based on the original tempo (expected timing).

        Args:
            bar: Bar number (0-indexed)

        Returns:
            Frame offset (samples at 44.1kHz)
        """
        # Calculate time position relative to first beat based on original tempo
        relative_time = bar * self.expected_bar_duration
        return int(relative_time * self.sample_rate)
