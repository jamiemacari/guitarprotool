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
        tempo_corrected: Whether tempo correction was applied
        original_detected_bpm: Originally detected BPM before correction
        corrected_bpm: BPM after correction (same as original if no correction)
    """

    bar_drifts: List[BarDriftInfo]
    avg_drift_percent: float
    max_drift_percent: float
    max_drift_bar: int
    total_bars_analyzed: int
    bars_with_significant_drift: List[int]
    tempo_stability_score: float
    recommended_sync_interval: int
    # Tempo correction info (optional, with defaults for backward compatibility)
    tempo_corrected: bool = False
    original_detected_bpm: Optional[float] = None
    corrected_bpm: Optional[float] = None
    # Sync point placement info
    bars_with_sync_points: List[int] = None  # type: ignore

    def __post_init__(self):
        """Initialize default values for mutable fields."""
        if self.bars_with_sync_points is None:
            self.bars_with_sync_points = []

    def get_summary_lines(self) -> List[str]:
        """Return formatted summary lines for CLI display."""
        lines = [
            f"Bars analyzed: {self.total_bars_analyzed}",
            f"Average drift: {self.avg_drift_percent:+.2f}%",
            f"Maximum drift: {self.max_drift_percent:+.2f}% at bar {self.max_drift_bar}",
            f"Stability score: {self.tempo_stability_score:.0%}",
            f"Recommended sync interval: every {self.recommended_sync_interval} bar(s)",
        ]
        if self.tempo_corrected and self.original_detected_bpm and self.corrected_bpm:
            lines.append(
                f"Tempo correction: {self.original_detected_bpm:.1f} -> {self.corrected_bpm:.1f} BPM"
            )
        if self.bars_with_significant_drift:
            lines.append(f"Bars needing attention: {len(self.bars_with_significant_drift)}")
        return lines

    def write_to_file(self, file_path: str) -> None:
        """Write detailed drift report to a file.

        Args:
            file_path: Path to write the report file
        """
        from pathlib import Path

        output_path = Path(file_path)

        lines = [
            "=" * 70,
            "TEMPO DRIFT ANALYSIS REPORT",
            "=" * 70,
            "",
        ]

        # Add tempo correction section if applicable
        if self.tempo_corrected and self.original_detected_bpm and self.corrected_bpm:
            lines.extend([
                "TEMPO CORRECTION APPLIED",
                "-" * 40,
                f"Original detected BPM: {self.original_detected_bpm:.1f}",
                f"Corrected BPM:         {self.corrected_bpm:.1f}",
                f"Correction type:       {'Half-time (doubled)' if self.corrected_bpm > self.original_detected_bpm else 'Double-time (halved)'}",
                "",
            ])
        else:
            lines.extend([
                "TEMPO CORRECTION: None applied",
                "-" * 40,
                f"Detected BPM matches expected tempo range",
                "",
            ])

        lines.extend([
            "SUMMARY",
            "-" * 40,
        ])
        lines.extend(self.get_summary_lines())
        if self.bars_with_sync_points:
            lines.append(f"Sync points placed: {len(self.bars_with_sync_points)} bars")
        lines.extend([
            "",
            "=" * 70,
            "BAR-BY-BAR DRIFT ANALYSIS",
            "=" * 70,
            "",
            f"{'Bar':>6} | {'Expected':>10} | {'Actual':>10} | {'Local BPM':>10} | "
            f"{'Drift %':>10} | {'Severity':>12} | {'Sync':>6}",
            "-" * 80,
        ])

        sync_point_set = set(self.bars_with_sync_points) if self.bars_with_sync_points else set()
        for drift in self.bar_drifts:
            has_sync = "<<SYNC" if drift.bar in sync_point_set else ""
            lines.append(
                f"{drift.bar:>6} | {drift.expected_time:>10.3f} | {drift.actual_time:>10.3f} | "
                f"{drift.local_tempo:>10.2f} | {drift.drift_percent:>+10.2f} | "
                f"{drift.severity.value:>12} | {has_sync}"
            )

        lines.extend([
            "",
            "=" * 70,
            "LEGEND",
            "-" * 40,
            "Expected: Time in seconds based on tab tempo",
            "Actual: Time in seconds from detected beats",
            "Local BPM: Detected tempo at this bar position",
            f"Tab BPM: {self.bar_drifts[0].original_tempo if self.bar_drifts else 'N/A'}",
            "Sync: <<SYNC indicates a sync point was placed at this bar",
            "",
            "Severity Levels:",
            "  STABLE:      < 1% drift",
            "  MINOR:       1-3% drift",
            "  MODERATE:    3-5% drift",
            "  SIGNIFICANT: 5-10% drift",
            "  SEVERE:      > 10% drift",
            "",
            "=" * 70,
        ])

        output_path.write_text("\n".join(lines))
        logger.info(f"Drift report written to: {output_path}")


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
    DRIFT_THRESHOLD_PERCENT = 0.5  # Add sync point if drift exceeds this (tighter = more sync points)
    MIN_SYNC_INTERVAL = 1  # Minimum bars between sync points
    MAX_SYNC_INTERVAL = 8  # Maximum bars between sync points (more frequent baseline)

    def __init__(
        self,
        beat_times: List[float],
        original_tempo: float,
        beats_per_bar: int = 4,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        tab_start_bar: int = 0,
    ):
        """Initialize DriftAnalyzer.

        Args:
            beat_times: List of detected beat times in seconds from audio
            original_tempo: Tab tempo in BPM
            beats_per_bar: Beats per bar (4 for 4/4 time)
            sample_rate: Audio sample rate (default 44100)
            tab_start_bar: Bar number where notes begin in the tab (0-indexed).
                          This aligns the first detected beat with this bar instead of bar 0.
                          Used when tabs have intro bars before the actual music starts.

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
        self.tab_start_bar = tab_start_bar

        # Calculate expected beat interval
        self.expected_beat_interval = 60.0 / original_tempo
        self.expected_bar_duration = self.expected_beat_interval * beats_per_bar

        # First beat time is our reference point (aligns with tab_start_bar)
        self.first_beat_time = beat_times[0]

        logger.debug(
            f"DriftAnalyzer initialized: tempo={original_tempo}, "
            f"beats={len(beat_times)}, first_beat={self.first_beat_time:.3f}s, "
            f"tab_start_bar={tab_start_bar}"
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

        When tab_start_bar > 0, adjusts beat index so that bar tab_start_bar
        corresponds to beat 0 (first detected beat).

        Uses nearest-beat matching to find the actual bar position, which is more
        robust to false beat detections that would otherwise shift subsequent bars.

        Args:
            bar: Bar number (0-indexed)

        Returns:
            BarDriftInfo or None if bar is out of range
        """
        # For bars before tab_start_bar, we don't have beat data
        if bar < self.tab_start_bar:
            return None

        # Calculate expected time for this bar (relative to first beat/tab_start_bar)
        bars_from_start = bar - self.tab_start_bar
        expected_time = bars_from_start * self.expected_bar_duration

        # Find nearest beat to expected position (more robust than direct indexing)
        # This handles false beat detections that would otherwise shift timing
        nearest_beat_idx = self._find_nearest_beat_to_expected(bars_from_start)
        if nearest_beat_idx is None:
            return None

        # Actual time relative to first beat
        actual_time = self.beat_times[nearest_beat_idx] - self.first_beat_time

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

        When tab_start_bar > 0, adjusts beat index so that bar tab_start_bar
        corresponds to beat 0 (first detected beat).

        Args:
            bar: Bar number (0-indexed)
            window_beats: Number of beats to consider around the bar

        Returns:
            Local tempo in BPM
        """
        # For bars before tab_start_bar, return original tempo
        if bar < self.tab_start_bar:
            return self.original_tempo

        # Find beat index for this bar (adjusted for tab_start_bar)
        bars_from_start = bar - self.tab_start_bar
        beat_index = bars_from_start * self.beats_per_bar

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

        When tab_start_bar > 0, an intro sync point is added at bar 0 with a
        stretched tempo that makes bars 0 through (tab_start_bar-1) cover the
        audio intro duration (first_beat_time seconds).

        Args:
            max_bars: Maximum bar number from GP file
            base_interval: Base interval between sync points (bars)

        Returns:
            List of SyncPointData with adaptive placement and tempo values
        """
        # Find optimal sync point positions
        positions = self._find_sync_point_positions(max_bars, base_interval)

        sync_points: List[SyncPointData] = []

        # When tab_start_bar > 0, add an intro sync point at bar 0
        # This stretches the intro bars to match the audio intro duration
        if self.tab_start_bar > 0:
            # Calculate stretched tempo for intro bars
            # Expected intro at tab tempo vs actual audio intro
            expected_intro_duration = self.tab_start_bar * self.expected_bar_duration
            # Stretched tempo = original_tempo * (expected / actual)
            intro_tempo = self.original_tempo * (expected_intro_duration / self.first_beat_time)

            intro_sync_point = SyncPointData(
                bar=0,
                frame_offset=0,  # Intro starts at beginning of audio
                modified_tempo=intro_tempo,
                original_tempo=self.original_tempo,
            )
            sync_points.append(intro_sync_point)

            logger.info(
                f"Intro sync point: bar=0, tempo={intro_tempo:.3f} BPM "
                f"(stretches {self.tab_start_bar} bars over {self.first_beat_time:.3f}s)"
            )

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

    def write_debug_beats(self, file_path: str) -> None:
        """Write detailed beat detection data for debugging.

        Outputs raw beat times, intervals, and calculated BPMs for each beat.
        This is useful for diagnosing beat detection accuracy issues.

        Args:
            file_path: Path to write the debug file
        """
        from pathlib import Path

        output_path = Path(file_path)
        lines = [
            "=" * 80,
            "BEAT DETECTION DEBUG DATA",
            "=" * 80,
            "",
            f"Original tempo (from tab): {self.original_tempo:.2f} BPM",
            f"Expected beat interval: {self.expected_beat_interval:.4f}s",
            f"First beat time: {self.first_beat_time:.4f}s",
            f"Total beats detected: {len(self.beat_times)}",
            "",
            "=" * 80,
            "BEAT-BY-BEAT DATA",
            "=" * 80,
            "",
            f"{'Beat':>6} | {'Time (s)':>12} | {'Rel Time':>12} | {'Interval':>10} | "
            f"{'Inst BPM':>10} | {'Bar':>6} | {'Beat in Bar':>12}",
            "-" * 90,
        ]

        prev_time = None
        for i, beat_time in enumerate(self.beat_times):
            rel_time = beat_time - self.first_beat_time
            bar = i // self.beats_per_bar
            beat_in_bar = i % self.beats_per_bar

            if prev_time is not None:
                interval = beat_time - prev_time
                inst_bpm = 60.0 / interval if interval > 0 else 0
                interval_str = f"{interval:.4f}"
                bpm_str = f"{inst_bpm:.2f}"
            else:
                interval_str = "-"
                bpm_str = "-"

            lines.append(
                f"{i:>6} | {beat_time:>12.4f} | {rel_time:>12.4f} | {interval_str:>10} | "
                f"{bpm_str:>10} | {bar:>6} | {beat_in_bar:>12}"
            )
            prev_time = beat_time

        # Add summary statistics
        if len(self.beat_times) >= 2:
            intervals = np.diff(self.beat_times)
            avg_interval = np.mean(intervals)
            std_interval = np.std(intervals)
            min_interval = np.min(intervals)
            max_interval = np.max(intervals)
            avg_bpm = 60.0 / avg_interval if avg_interval > 0 else 0

            lines.extend([
                "",
                "=" * 80,
                "INTERVAL STATISTICS",
                "=" * 80,
                "",
                f"Average interval: {avg_interval:.4f}s (= {avg_bpm:.2f} BPM)",
                f"Std deviation: {std_interval:.4f}s",
                f"Min interval: {min_interval:.4f}s (= {60/min_interval:.2f} BPM)",
                f"Max interval: {max_interval:.4f}s (= {60/max_interval:.2f} BPM)",
                f"Interval variance: {(max_interval - min_interval):.4f}s",
                "",
                f"Expected interval: {self.expected_beat_interval:.4f}s (from tab tempo)",
                f"Deviation from expected: {(avg_interval - self.expected_beat_interval):.4f}s "
                f"({((avg_interval - self.expected_beat_interval) / self.expected_beat_interval * 100):.2f}%)",
                "",
            ])

        output_path.write_text("\n".join(lines))
        logger.info(f"Debug beat data written to: {output_path}")

    def _find_nearest_beat_to_expected(self, bars_from_start: int) -> Optional[int]:
        """Find the beat index nearest to the expected bar position.

        Instead of using direct indexing (bar * beats_per_bar), this finds
        the detected beat closest to where the bar should be based on tempo.
        This is more robust to false beat detections that would otherwise
        shift subsequent bar timings.

        Args:
            bars_from_start: Number of bars from tab_start_bar (0 = first bar with notes)

        Returns:
            Index into beat_times of the nearest beat, or None if beyond audio
        """
        if not self.beat_times:
            return None

        # Calculate expected absolute time for this bar
        expected_absolute_time = self.first_beat_time + (bars_from_start * self.expected_bar_duration)

        # If expected time is beyond our detected beats, return None
        last_beat_time = self.beat_times[-1]
        if expected_absolute_time > last_beat_time + self.expected_bar_duration:
            return None

        # Find the beat closest to expected time
        min_diff = float('inf')
        nearest_idx = 0

        # Start search from an estimated index to be more efficient
        estimated_idx = bars_from_start * self.beats_per_bar
        search_start = max(0, estimated_idx - self.beats_per_bar * 2)
        search_end = min(len(self.beat_times), estimated_idx + self.beats_per_bar * 2)

        for i in range(search_start, search_end):
            diff = abs(self.beat_times[i] - expected_absolute_time)
            if diff < min_diff:
                min_diff = diff
                nearest_idx = i

        # Sanity check: the nearest beat shouldn't be more than half a bar away
        max_tolerance = self.expected_bar_duration / 2
        if min_diff > max_tolerance:
            logger.warning(
                f"Nearest beat for bar {bars_from_start} is {min_diff:.3f}s away "
                f"(tolerance: {max_tolerance:.3f}s)"
            )

        return nearest_idx

    def _find_sync_point_positions(
        self,
        max_bars: int,
        base_interval: int,
    ) -> List[int]:
        """Determine optimal bar positions for sync points.

        Algorithm:
        1. Always place sync point at first bar with notes (tab_start_bar or 0)
        2. Evaluate drift at each bar
        3. If drift exceeds threshold, add sync point
        4. Ensure minimum spacing between sync points
        5. Never exceed max_interval without a sync point

        When tab_start_bar > 0, sync points start from tab_start_bar.
        Intro bars (0 to tab_start_bar-1) are skipped - they play at tab tempo.

        Args:
            max_bars: Maximum bar number
            base_interval: Base interval between sync points

        Returns:
            List of bar numbers for sync point placement
        """
        # Start from tab_start_bar (where notes begin) or 0 if no intro
        start_bar = self.tab_start_bar
        positions = [start_bar]  # Always start at first bar with notes
        last_sync_bar = start_bar

        for bar in range(start_bar + 1, max_bars):
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

        Uses nearest-beat matching instead of direct indexing to be robust
        to false beat detections that would otherwise shift subsequent bars.

        When tab_start_bar > 0:
        - Bars before tab_start_bar should NOT have sync points (handled by caller)
        - Bars at/after tab_start_bar use ABSOLUTE audio positions
        - GP8 interprets FrameOffset as the absolute position in the audio file
          where this bar should sync

        When tab_start_bar is 0 (default), frame offsets are RELATIVE to first beat,
        and FramePadding shifts audio to align bar 0 with the first detected beat.

        Args:
            bar: Bar number (0-indexed)

        Returns:
            Frame offset (samples at 44.1kHz)
        """
        if self.tab_start_bar > 0:
            # For tabs with intro bars, we use ABSOLUTE audio positions
            # GP8 needs to know exactly where in the audio file each bar is

            if bar < self.tab_start_bar:
                # Intro bars: shouldn't normally be called, but calculate anyway
                # These bars don't have beats detected, so extrapolate backward
                bars_before_music = self.tab_start_bar - bar
                absolute_time = self.first_beat_time - (bars_before_music * self.expected_bar_duration)
                return int(max(0, absolute_time) * self.sample_rate)

            # Use nearest-beat matching for robustness against false beats
            adjusted_bar = bar - self.tab_start_bar
            nearest_beat_idx = self._find_nearest_beat_to_expected(adjusted_bar)

            if nearest_beat_idx is not None:
                # Use ABSOLUTE audio position (not relative to first beat)
                absolute_time = self.beat_times[nearest_beat_idx]
                return int(absolute_time * self.sample_rate)
            else:
                # Beyond detected beats - extrapolate from expected position
                expected_absolute_time = self.first_beat_time + (adjusted_bar * self.expected_bar_duration)
                return int(expected_absolute_time * self.sample_rate)
        else:
            # Default behavior: frame offsets are RELATIVE to first beat (bar 0 = 0)
            # Combined with negative FramePadding, this aligns bar 0 with first beat

            # Use nearest-beat matching for robustness against false beats
            nearest_beat_idx = self._find_nearest_beat_to_expected(bar)

            if nearest_beat_idx is not None:
                # Calculate time RELATIVE to first beat (bar 0 = 0)
                relative_time = self.beat_times[nearest_beat_idx] - self.first_beat_time
                return int(relative_time * self.sample_rate)
            else:
                # Beyond detected beats - extrapolate from expected position
                expected_relative_time = bar * self.expected_bar_duration
                return int(expected_relative_time * self.sample_rate)
