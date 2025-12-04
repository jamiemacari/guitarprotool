"""Beat detection module for Guitar Pro audio synchronization.

This module handles:
- Loading and analyzing audio files using aubio
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

# Try to import aubio, but allow running without it for testing
try:
    import aubio

    AUBIO_AVAILABLE = True
except ImportError:
    aubio = None  # type: ignore
    AUBIO_AVAILABLE = False
    logger.warning(
        "aubio not available. Beat detection will not work. "
        "Install aubio with: pip install aubio"
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
        frame_offset: Audio frame position (sample number at 44.1kHz)
        modified_tempo: Detected tempo in audio at this point
        original_tempo: Tempo specified in tab
    """

    bar: int
    frame_offset: int
    modified_tempo: float
    original_tempo: float


# Type alias for progress callbacks
ProgressCallback = Callable[[float, str], None]


class BeatDetector:
    """Detects BPM and beat positions in audio files using aubio.

    aubio is chosen over librosa for its lightweight footprint (20x smaller)
    while providing accurate beat detection for music files.

    Example:
        >>> detector = BeatDetector()
        >>> beat_info = detector.analyze("/path/to/audio.mp3")
        >>> print(f"BPM: {beat_info.bpm}")
        >>> sync_points = detector.generate_sync_points(beat_info, original_tempo=120)

    Attributes:
        sample_rate: Audio sample rate (default 44100 Hz)
        win_s: Analysis window size in samples
        hop_s: Hop size between windows in samples
    """

    DEFAULT_SAMPLE_RATE = 44100
    DEFAULT_WIN_S = 1024
    DEFAULT_HOP_S = 512

    def __init__(
        self,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        win_s: int = DEFAULT_WIN_S,
        hop_s: int = DEFAULT_HOP_S,
    ):
        """Initialize BeatDetector.

        Args:
            sample_rate: Audio sample rate in Hz
            win_s: Analysis window size in samples
            hop_s: Hop size between analysis windows
        """
        self.sample_rate = sample_rate
        self.win_s = win_s
        self.hop_s = hop_s

        logger.debug(f"BeatDetector initialized: sr={sample_rate}, win={win_s}, hop={hop_s}")

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

        if not AUBIO_AVAILABLE:
            raise BeatDetectionError("aubio library not available. Install with: pip install aubio")

        logger.info(f"Analyzing audio: {audio_path}")

        if progress_callback:
            progress_callback(0.0, "Loading audio file...")

        try:
            # Get audio duration for progress tracking
            duration = self._get_audio_duration(audio_path)
            logger.debug(f"Audio duration: {duration:.2f}s")

            # Detect BPM
            if progress_callback:
                progress_callback(0.1, "Detecting tempo...")
            bpm, bpm_confidence = self._detect_bpm(audio_path)

            # Detect beat positions
            if progress_callback:
                progress_callback(0.3, "Finding beat positions...")
            beat_times = self._detect_beats(audio_path, progress_callback)

            # Calculate overall confidence
            beat_consistency = self._calculate_beat_consistency(beat_times, bpm)

            # Combine confidence measures
            confidence = (bpm_confidence + beat_consistency) / 2

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
            Detected BPM (median value)

        Raises:
            FileNotFoundError: If audio file doesn't exist
            BPMDetectionError: If BPM detection fails
        """
        audio_path = Path(audio_path)

        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        if not AUBIO_AVAILABLE:
            raise BPMDetectionError("aubio library not available. Install with: pip install aubio")

        bpm, _ = self._detect_bpm(audio_path)
        return bpm

    def generate_sync_points(
        self,
        beat_info: BeatInfo,
        original_tempo: float,
        beats_per_bar: int = 4,
        sync_interval: int = 16,
        start_offset: float = 0.0,
    ) -> List[SyncPointData]:
        """Generate sync points from beat detection results.

        Creates sync points at regular intervals (every N beats) to handle
        tempo drift in recordings.

        Args:
            beat_info: Beat detection results from analyze()
            original_tempo: Tab tempo in BPM
            beats_per_bar: Beats per bar (4 for 4/4 time)
            sync_interval: Create sync point every N beats
            start_offset: Audio offset in seconds (for intro/count-in)

        Returns:
            List of SyncPointData ready for XML injection

        Raises:
            BeatDetectionError: If not enough beats to generate sync points
        """
        if not beat_info.beat_times:
            raise BeatDetectionError("No beats detected, cannot generate sync points")

        if len(beat_info.beat_times) < 2:
            raise BeatDetectionError("Need at least 2 beats to generate sync points")

        logger.info(
            f"Generating sync points: interval={sync_interval} beats, "
            f"beats_per_bar={beats_per_bar}"
        )

        sync_points: List[SyncPointData] = []

        # Adjust beat times for start offset
        adjusted_beats = [t - start_offset for t in beat_info.beat_times]

        # Find first beat at or after offset (beat index 0)
        first_beat_idx = 0
        for i, t in enumerate(adjusted_beats):
            if t >= 0:
                first_beat_idx = i
                break

        # Generate sync points at intervals
        beat_count = len(adjusted_beats) - first_beat_idx

        for i in range(0, beat_count, sync_interval):
            beat_idx = first_beat_idx + i
            if beat_idx >= len(adjusted_beats):
                break

            beat_time = adjusted_beats[beat_idx]
            if beat_time < 0:
                continue

            # Calculate bar number from beat index
            bar = i // beats_per_bar

            # Calculate frame offset (samples at 44.1kHz)
            frame_offset = int(beat_time * self.sample_rate)

            # Calculate local tempo around this beat
            local_tempo = self._calculate_local_tempo(adjusted_beats, beat_idx, window_beats=8)

            sync_point = SyncPointData(
                bar=bar,
                frame_offset=frame_offset,
                modified_tempo=local_tempo,
                original_tempo=original_tempo,
            )
            sync_points.append(sync_point)

            logger.debug(
                f"Sync point: bar={bar}, frame={frame_offset}, " f"tempo={local_tempo:.3f}"
            )

        # Ensure first sync point is at bar 0
        if sync_points and sync_points[0].bar != 0:
            first_beat_time = max(0, adjusted_beats[first_beat_idx])
            sync_points.insert(
                0,
                SyncPointData(
                    bar=0,
                    frame_offset=int(first_beat_time * self.sample_rate),
                    modified_tempo=beat_info.bpm,
                    original_tempo=original_tempo,
                ),
            )

        logger.success(f"Generated {len(sync_points)} sync points")
        return sync_points

    def _detect_bpm(self, audio_path: Path) -> tuple[float, float]:
        """Detect BPM using aubio tempo detection.

        Returns median BPM for robustness against tempo variations.

        Args:
            audio_path: Path to audio file

        Returns:
            Tuple of (median_bpm, confidence)

        Raises:
            BPMDetectionError: If BPM cannot be detected
        """
        try:
            # Create aubio source and tempo detector
            source = aubio.source(str(audio_path), self.sample_rate, self.hop_s)
            tempo = aubio.tempo("default", self.win_s, self.hop_s, self.sample_rate)

            bpm_values: List[float] = []

            # Process audio in chunks
            while True:
                samples, read = source()
                is_beat = tempo(samples)

                if is_beat:
                    current_bpm = tempo.get_bpm()
                    if current_bpm > 0:
                        bpm_values.append(current_bpm)

                if read < self.hop_s:
                    break

            if not bpm_values:
                raise BPMDetectionError("No BPM detected. Audio may not have a clear beat.")

            # Use median for robustness
            median_bpm = median(bpm_values)

            # Calculate confidence based on consistency
            if len(bpm_values) > 1:
                bpm_array = np.array(bpm_values)
                std_dev = np.std(bpm_array)
                # Lower std dev = higher confidence
                confidence = max(0.0, min(1.0, 1.0 - (std_dev / median_bpm)))
            else:
                confidence = 0.5

            logger.debug(
                f"BPM detection: median={median_bpm:.1f}, "
                f"samples={len(bpm_values)}, confidence={confidence:.2f}"
            )

            return median_bpm, confidence

        except BPMDetectionError:
            raise
        except Exception as e:
            raise BPMDetectionError(f"BPM detection failed: {e}") from e

    def _detect_beats(
        self,
        audio_path: Path,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> List[float]:
        """Detect beat positions throughout the audio.

        Args:
            audio_path: Path to audio file
            progress_callback: Optional progress callback

        Returns:
            List of beat times in seconds
        """
        try:
            source = aubio.source(str(audio_path), self.sample_rate, self.hop_s)
            tempo = aubio.tempo("default", self.win_s, self.hop_s, self.sample_rate)

            beat_times: List[float] = []
            total_frames = 0

            # Get total frames for progress
            duration = self._get_audio_duration(audio_path)
            total_expected_frames = int(duration * self.sample_rate)

            while True:
                samples, read = source()
                is_beat = tempo(samples)

                if is_beat:
                    beat_time = total_frames / self.sample_rate
                    beat_times.append(beat_time)

                total_frames += read

                # Update progress (scale between 0.3 and 0.9)
                if progress_callback and total_expected_frames > 0:
                    progress = 0.3 + (total_frames / total_expected_frames) * 0.6
                    progress_callback(min(0.9, progress), "Detecting beats...")

                if read < self.hop_s:
                    break

            logger.debug(f"Detected {len(beat_times)} beats")
            return beat_times

        except Exception as e:
            raise BeatDetectionError(f"Beat detection failed: {e}") from e

    def _get_audio_duration(self, audio_path: Path) -> float:
        """Get audio file duration in seconds.

        Args:
            audio_path: Path to audio file

        Returns:
            Duration in seconds
        """
        try:
            source = aubio.source(str(audio_path), self.sample_rate, self.hop_s)
            duration = source.duration / source.samplerate
            return duration
        except Exception:
            # Fallback: estimate from file size (rough)
            return 180.0  # Default 3 minutes

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
