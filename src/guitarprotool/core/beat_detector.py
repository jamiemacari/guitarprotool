"""Beat detection module for Guitar Pro audio synchronization.

This module handles:
- Loading and analyzing audio files using librosa
- Detecting BPM (tempo) from audio
- Finding beat positions throughout the track
- Generating sync points for GP8 XML injection
"""

from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Callable, List, Optional

import numpy as np
from loguru import logger

from guitarprotool.utils.exceptions import BeatDetectionError, BPMDetectionError

# Try to import librosa, but allow running without it for testing
try:
    import librosa

    LIBROSA_AVAILABLE = True
except ImportError:
    librosa = None  # type: ignore
    LIBROSA_AVAILABLE = False
    logger.warning(
        "librosa not available. Beat detection will not work. "
        "Install librosa with: pip install librosa"
    )


@dataclass
class BeatInfo:
    """Container for beat detection results.

    Attributes:
        bpm: Detected tempo in beats per minute (median of all detected values)
        beat_times: List of beat positions in seconds
        confidence: Overall confidence score (0.0-1.0)
    """

    bpm: float
    beat_times: List[float]
    confidence: float


@dataclass
class SyncPointData:
    """Data for a single sync point, ready for XML injection.

    This maps directly to the SyncPoint class in xml_modifier.py.

    Attributes:
        bar: Bar/measure number (0-indexed)
        frame_offset: Audio frame position relative to first beat (sample number at 44.1kHz)
        modified_tempo: Detected tempo in audio at this point
        original_tempo: Tempo specified in tab
    """

    bar: int
    frame_offset: int
    modified_tempo: float
    original_tempo: float


@dataclass
class SyncResult:
    """Result of sync point generation, including frame padding for alignment.

    Attributes:
        sync_points: List of sync points with relative frame offsets
        frame_padding: Negative frame offset to align audio start with bar 0.
                      This should be set on BackingTrackConfig.frame_padding.
        first_beat_time: Time in seconds where music starts in the audio.
    """

    sync_points: List[SyncPointData]
    frame_padding: int
    first_beat_time: float


# Type alias for progress callbacks
ProgressCallback = Callable[[float, str], None]


class BeatDetector:
    """Detects BPM and beat positions in audio files using librosa.

    librosa provides accurate beat detection for music files with
    excellent Python compatibility.

    Example:
        >>> detector = BeatDetector()
        >>> beat_info = detector.analyze("/path/to/audio.mp3")
        >>> print(f"BPM: {beat_info.bpm}")
        >>> sync_points = detector.generate_sync_points(beat_info, original_tempo=120)

    Attributes:
        sample_rate: Audio sample rate (default 44100 Hz)
        hop_length: Hop size between analysis frames in samples
    """

    DEFAULT_SAMPLE_RATE = 44100
    DEFAULT_HOP_LENGTH = 512

    def __init__(
        self,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        hop_length: int = DEFAULT_HOP_LENGTH,
    ):
        """Initialize BeatDetector.

        Args:
            sample_rate: Audio sample rate in Hz
            hop_length: Hop size between analysis frames
        """
        self.sample_rate = sample_rate
        self.hop_length = hop_length

        logger.debug(f"BeatDetector initialized: sr={sample_rate}, hop={hop_length}")

    def analyze(
        self,
        audio_path: Path | str,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> BeatInfo:
        """Analyze audio file to detect BPM and beat positions.

        Args:
            audio_path: Path to the audio file (MP3, WAV, etc.)
            progress_callback: Optional callback for progress updates.
                              Receives (progress: float 0-1, message: str)

        Returns:
            BeatInfo containing BPM, beat times, and confidence

        Raises:
            FileNotFoundError: If audio file doesn't exist
            BeatDetectionError: If analysis fails
            BPMDetectionError: If no BPM can be detected
        """
        audio_path = Path(audio_path)

        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        if not LIBROSA_AVAILABLE:
            raise BeatDetectionError(
                "librosa library not available. Install with: pip install librosa"
            )

        logger.info(f"Analyzing audio: {audio_path}")

        if progress_callback:
            progress_callback(0.0, "Loading audio file...")

        try:
            # Load audio file
            if progress_callback:
                progress_callback(0.1, "Loading audio...")
            y, sr = librosa.load(str(audio_path), sr=self.sample_rate, mono=True)

            duration = len(y) / sr
            logger.debug(f"Audio duration: {duration:.2f}s")

            # Detect BPM and beats
            if progress_callback:
                progress_callback(0.3, "Detecting tempo and beats...")

            tempo, beat_frames = librosa.beat.beat_track(
                y=y, sr=sr, hop_length=self.hop_length
            )

            # Convert tempo to float (librosa may return array)
            if isinstance(tempo, np.ndarray):
                bpm = float(tempo[0]) if len(tempo) > 0 else float(tempo)
            else:
                bpm = float(tempo)

            if bpm <= 0:
                raise BPMDetectionError("No BPM detected. Audio may not have a clear beat.")

            # Detect onsets to find the first note more accurately
            if progress_callback:
                progress_callback(0.5, "Detecting first onset...")

            onset_frames = librosa.onset.onset_detect(
                y=y, sr=sr, hop_length=self.hop_length
            )
            onset_times = librosa.frames_to_time(
                onset_frames, sr=sr, hop_length=self.hop_length
            ).tolist()

            # Convert beat frames to times
            beat_times = librosa.frames_to_time(
                beat_frames, sr=sr, hop_length=self.hop_length
            ).tolist()

            # Use the first onset as the starting point
            # This is more accurate than beat detection for finding when music starts
            if onset_times:
                first_onset = onset_times[0]
                if beat_times:
                    first_beat = beat_times[0]
                    logger.debug(
                        f"First onset: {first_onset:.3f}s, first beat: {first_beat:.3f}s"
                    )
                # Always use the first onset as the starting point for bar 0
                # Insert it at the beginning of beat_times so generate_sync_points uses it
                if not beat_times or first_onset != beat_times[0]:
                    beat_times.insert(0, first_onset)
                    logger.debug(f"Using first onset ({first_onset:.3f}s) as start point")

            if progress_callback:
                progress_callback(0.7, "Calculating confidence...")

            # Calculate confidence based on beat regularity
            confidence = self._calculate_beat_consistency(beat_times, bpm)

            if progress_callback:
                progress_callback(1.0, "Analysis complete")

            beat_info = BeatInfo(bpm=bpm, beat_times=beat_times, confidence=confidence)

            logger.success(
                f"Analysis complete: BPM={bpm:.1f}, beats={len(beat_times)}, "
                f"confidence={confidence:.2f}"
            )

            return beat_info

        except (BeatDetectionError, BPMDetectionError):
            raise
        except Exception as e:
            raise BeatDetectionError(f"Failed to analyze audio: {e}") from e

    def detect_bpm(self, audio_path: Path | str) -> float:
        """Detect BPM only (without full beat analysis).

        Args:
            audio_path: Path to the audio file

        Returns:
            Detected BPM

        Raises:
            FileNotFoundError: If audio file doesn't exist
            BPMDetectionError: If BPM detection fails
        """
        audio_path = Path(audio_path)

        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        if not LIBROSA_AVAILABLE:
            raise BPMDetectionError(
                "librosa library not available. Install with: pip install librosa"
            )

        try:
            y, sr = librosa.load(str(audio_path), sr=self.sample_rate, mono=True)
            tempo, _ = librosa.beat.beat_track(y=y, sr=sr, hop_length=self.hop_length)

            # Convert tempo to float (librosa may return array)
            if isinstance(tempo, np.ndarray):
                bpm = float(tempo[0]) if len(tempo) > 0 else float(tempo)
            else:
                bpm = float(tempo)

            if bpm <= 0:
                raise BPMDetectionError("No BPM detected. Audio may not have a clear beat.")

            return bpm

        except BPMDetectionError:
            raise
        except Exception as e:
            raise BPMDetectionError(f"BPM detection failed: {e}") from e

    def generate_sync_points(
        self,
        beat_info: BeatInfo,
        original_tempo: float,
        beats_per_bar: int = 4,
        sync_interval: int = 16,
        start_offset: float = 0.0,
        max_bars: Optional[int] = None,
        adaptive: bool = True,
    ) -> SyncResult:
        """Generate sync points for audio alignment with the tab.

        Creates sync points for aligning audio playback with tab notation.
        When adaptive=True (default), uses DriftAnalyzer to detect local tempo
        at each sync point and place sync points more frequently where tempo
        drifts significantly.

        The first detected beat/onset in the audio is used as the starting point.
        The frame_padding value returned should be set on BackingTrackConfig to
        align the audio with bar 0 of the tab.

        Args:
            beat_info: Beat detection results from analyze()
            original_tempo: Tab tempo in BPM
            beats_per_bar: Beats per bar (4 for 4/4 time)
            sync_interval: Create sync point every N beats (used for bar interval)
            start_offset: Additional audio offset in seconds (for manual adjustment)
            max_bars: Maximum bar number (from GP file bar count). If None, uses
                      audio duration to estimate.
            adaptive: If True (default), use adaptive sync point placement with
                     local tempo detection. If False, use static intervals with
                     original_tempo for all sync points.

        Returns:
            SyncResult containing sync points and frame_padding for alignment

        Raises:
            BeatDetectionError: If not enough beats to generate sync points
        """
        if not beat_info.beat_times:
            raise BeatDetectionError("No beats detected, cannot generate sync points")

        if len(beat_info.beat_times) < 2:
            raise BeatDetectionError("Need at least 2 beats to generate sync points")

        # Use the first detected beat/onset as the starting point for bar 0
        first_beat_time = beat_info.beat_times[0] + start_offset

        # Calculate frame_padding as negative offset to align audio with bar 0
        frame_padding = -int(first_beat_time * self.sample_rate)

        # Calculate bar interval from sync_interval
        bar_interval = sync_interval // beats_per_bar

        # Calculate max_bars if not provided
        if max_bars is None:
            audio_duration = beat_info.beat_times[-1] - beat_info.beat_times[0]
            seconds_per_beat = 60.0 / original_tempo
            seconds_per_bar = seconds_per_beat * beats_per_bar
            max_bars = int(audio_duration / seconds_per_bar) + 1

        if adaptive:
            sync_points = self._generate_adaptive_sync_points(
                beat_info, original_tempo, beats_per_bar, bar_interval, max_bars
            )
        else:
            sync_points = self._generate_static_sync_points(
                original_tempo, beats_per_bar, bar_interval, max_bars
            )

        logger.success(
            f"Generated {len(sync_points)} sync points "
            f"({'adaptive' if adaptive else 'static'}), "
            f"frame_padding={frame_padding} ({first_beat_time:.3f}s offset)"
        )

        return SyncResult(
            sync_points=sync_points,
            frame_padding=frame_padding,
            first_beat_time=first_beat_time,
        )

    def _generate_adaptive_sync_points(
        self,
        beat_info: BeatInfo,
        original_tempo: float,
        beats_per_bar: int,
        bar_interval: int,
        max_bars: int,
    ) -> List[SyncPointData]:
        """Generate sync points with adaptive tempo detection.

        Uses DriftAnalyzer to calculate local tempo at each sync point
        and place sync points more frequently where drift is significant.
        """
        from guitarprotool.core.drift_analyzer import DriftAnalyzer
        from guitarprotool.utils.exceptions import InsufficientBeatsError

        try:
            analyzer = DriftAnalyzer(
                beat_times=beat_info.beat_times,
                original_tempo=original_tempo,
                beats_per_bar=beats_per_bar,
                sample_rate=self.sample_rate,
            )
            sync_points = analyzer.generate_adaptive_sync_points(
                max_bars=max_bars,
                base_interval=bar_interval,
            )
            logger.info(f"Adaptive sync: {len(sync_points)} sync points generated")
            return sync_points

        except InsufficientBeatsError:
            # Fall back to static generation if not enough beats
            logger.warning("Not enough beats for adaptive sync, using static mode")
            return self._generate_static_sync_points(
                original_tempo, beats_per_bar, bar_interval, max_bars
            )

    def _generate_static_sync_points(
        self,
        original_tempo: float,
        beats_per_bar: int,
        bar_interval: int,
        max_bars: int,
    ) -> List[SyncPointData]:
        """Generate sync points with static interval (legacy behavior).

        Creates sync points at regular bar intervals, all with the same
        modified_tempo equal to original_tempo.
        """
        sync_points: List[SyncPointData] = []

        seconds_per_beat = 60.0 / original_tempo
        seconds_per_bar = seconds_per_beat * beats_per_bar

        for bar in range(0, max_bars, bar_interval):
            relative_time = bar * seconds_per_bar
            frame_offset = int(relative_time * self.sample_rate)

            sync_point = SyncPointData(
                bar=bar,
                frame_offset=frame_offset,
                modified_tempo=original_tempo,
                original_tempo=original_tempo,
            )
            sync_points.append(sync_point)

            logger.debug(
                f"Static sync point: bar={bar}, frame={frame_offset}, "
                f"tempo={original_tempo:.3f}"
            )

        return sync_points

    def _calculate_bpm_from_beats(self, beat_times: List[float]) -> float:
        """Calculate BPM from beat intervals.

        Args:
            beat_times: List of beat times in seconds

        Returns:
            Calculated BPM
        """
        if len(beat_times) < 2:
            return 0.0

        intervals = np.diff(beat_times)
        if len(intervals) == 0:
            return 0.0

        median_interval = median(intervals.tolist())
        if median_interval <= 0:
            return 0.0

        return 60.0 / median_interval

    def _calculate_beat_consistency(self, beat_times: List[float], expected_bpm: float) -> float:
        """Calculate how consistent beat intervals are with expected BPM.

        Args:
            beat_times: List of beat times in seconds
            expected_bpm: Expected BPM to compare against

        Returns:
            Consistency score 0.0-1.0
        """
        if len(beat_times) < 2 or expected_bpm <= 0:
            return 0.5

        expected_interval = 60.0 / expected_bpm
        intervals = np.diff(beat_times)

        # Calculate deviation from expected interval
        deviations = np.abs(intervals - expected_interval) / expected_interval
        mean_deviation = np.mean(deviations)

        # Convert to 0-1 score (lower deviation = higher score)
        consistency = max(0.0, min(1.0, 1.0 - mean_deviation))
        return consistency

    def _calculate_local_tempo(
        self,
        beat_times: List[float],
        center_idx: int,
        window_beats: int = 8,
    ) -> float:
        """Calculate local tempo around a specific beat.

        Args:
            beat_times: List of all beat times
            center_idx: Index of the center beat
            window_beats: Number of beats to consider (on each side)

        Returns:
            Local tempo in BPM
        """
        if len(beat_times) < 2:
            return 120.0  # Default fallback

        # Get window of beats around center
        start_idx = max(0, center_idx - window_beats // 2)
        end_idx = min(len(beat_times), center_idx + window_beats // 2 + 1)

        window_beats_list = beat_times[start_idx:end_idx]

        if len(window_beats_list) < 2:
            # Fall back to global calculation
            return self._calculate_bpm_from_beats(beat_times)

        intervals = np.diff(window_beats_list)
        if len(intervals) == 0:
            return self._calculate_bpm_from_beats(beat_times)

        median_interval = median(intervals.tolist())
        if median_interval <= 0:
            return 120.0

        return 60.0 / median_interval
