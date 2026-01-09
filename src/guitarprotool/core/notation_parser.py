"""Notation parser for extracting note positions from Guitar Pro files.

This module parses GP file XML to extract note onset positions within each bar,
enabling notation-guided audio alignment that handles syncopation and weak beats.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from lxml import etree

from guitarprotool.utils.logger import logger


# Rhythm duration in beats (for 4/4 time where quarter note = 1 beat)
RHYTHM_DURATIONS: dict[str, float] = {
    "Whole": 4.0,
    "Half": 2.0,
    "Quarter": 1.0,
    "Eighth": 0.5,
    "16th": 0.25,
    "32nd": 0.125,
    "64th": 0.0625,
}


@dataclass
class BarNotation:
    """Notation information for a single bar."""

    bar_index: int
    time_signature: tuple[int, int]  # (numerator, denominator) e.g., (4, 4)
    note_onsets: list[float] = field(default_factory=list)  # Beat positions with notes
    first_onset: Optional[float] = None  # First note position (None if all rests)

    @property
    def has_notes(self) -> bool:
        """True if bar has any notes (not all rests)."""
        return len(self.note_onsets) > 0

    @property
    def beats_per_bar(self) -> float:
        """Number of beats in this bar based on time signature."""
        # In 4/4, there are 4 quarter note beats
        # In 6/8, there are 6 eighth note beats = 3 quarter note beats
        num, denom = self.time_signature
        return num * (4 / denom)


@dataclass
class NotationMap:
    """Complete notation map for a track in the score."""

    bars: list[BarNotation] = field(default_factory=list)
    track_id: int = 0

    @property
    def total_bars(self) -> int:
        """Total number of bars in the notation map."""
        return len(self.bars)

    def get_bar(self, bar_index: int) -> Optional[BarNotation]:
        """Get notation for a specific bar."""
        if 0 <= bar_index < len(self.bars):
            return self.bars[bar_index]
        return None

    def get_expected_onsets(self, bar_index: int) -> list[float]:
        """Get expected onset positions (in beats) for a bar.

        Returns list of beat positions where notes occur.
        E.g., [0.0, 2.5, 3.0] for notes on beat 1, beat 2.5, and beat 3.
        """
        bar = self.get_bar(bar_index)
        if bar:
            return bar.note_onsets
        return []


class NotationParser:
    """Parses Guitar Pro XML to extract note onset positions.

    This class traverses the GP file structure:
    MasterBars -> Bars -> Voices -> Beats -> Rhythms

    To build a map of where notes occur within each bar.

    Example:
        >>> parser = NotationParser(Path("score.gpif"))
        >>> notation_map = parser.parse(track_id=0)
        >>> bar_5_onsets = notation_map.get_expected_onsets(5)
        >>> print(bar_5_onsets)  # [0.0, 1.0, 2.0, 3.0] for notes on all beats
    """

    def __init__(self, gpif_path: Path):
        """Initialize with path to score.gpif.

        Args:
            gpif_path: Path to the score.gpif XML file
        """
        self.gpif_path = gpif_path
        self._root: Optional[etree._Element] = None
        self._rhythms: dict[str, tuple[str, int]] = {}  # id -> (note_value, dots)
        self._beats: dict[str, tuple[str, bool]] = {}  # id -> (rhythm_id, has_notes)
        self._voices: dict[str, list[str]] = {}  # id -> [beat_ids]
        self._bars: dict[str, list[str]] = {}  # id -> [voice_ids]
        self._track_bars: dict[str, list[str]] = {}  # track_id -> [bar_ids per master bar]

    def _load_xml(self) -> None:
        """Load and parse the XML file."""
        if self._root is not None:
            return

        try:
            parser = etree.XMLParser(remove_blank_text=False)
            tree = etree.parse(str(self.gpif_path), parser)
            self._root = tree.getroot()
        except Exception as e:
            logger.error(f"Failed to parse notation XML: {e}")
            raise

    def _build_rhythm_map(self) -> None:
        """Build mapping of rhythm IDs to durations."""
        if self._root is None:
            return

        rhythms_section = self._root.find("Rhythms")
        if rhythms_section is None:
            logger.warning("No Rhythms section found in XML")
            return

        for rhythm in rhythms_section.findall("Rhythm"):
            rhythm_id = rhythm.get("id")
            if rhythm_id is None:
                continue

            note_value_elem = rhythm.find("NoteValue")
            note_value = note_value_elem.text if note_value_elem is not None else "Quarter"

            # Check for dotted notes
            dots = 0
            aug_dot = rhythm.find("AugmentationDot")
            if aug_dot is not None:
                count = aug_dot.get("count")
                dots = int(count) if count else 1

            self._rhythms[rhythm_id] = (note_value, dots)

    def _build_beat_map(self) -> None:
        """Build mapping of beat IDs to rhythm and note status."""
        if self._root is None:
            return

        beats_section = self._root.find("Beats")
        if beats_section is None:
            logger.warning("No Beats section found in XML")
            return

        for beat in beats_section.findall("Beat"):
            beat_id = beat.get("id")
            if beat_id is None:
                continue

            # Get rhythm reference
            rhythm_elem = beat.find("Rhythm")
            rhythm_id = rhythm_elem.get("ref") if rhythm_elem is not None else None

            # Check if beat has notes (not a rest)
            notes_elem = beat.find("Notes")
            has_notes = notes_elem is not None and notes_elem.text and notes_elem.text.strip()

            self._beats[beat_id] = (rhythm_id, has_notes)

    def _build_voice_map(self) -> None:
        """Build mapping of voice IDs to beat sequences."""
        if self._root is None:
            return

        voices_section = self._root.find("Voices")
        if voices_section is None:
            logger.warning("No Voices section found in XML")
            return

        for voice in voices_section.findall("Voice"):
            voice_id = voice.get("id")
            if voice_id is None:
                continue

            beats_elem = voice.find("Beats")
            if beats_elem is not None and beats_elem.text:
                beat_ids = beats_elem.text.strip().split()
                self._voices[voice_id] = beat_ids
            else:
                self._voices[voice_id] = []

    def _build_bar_map(self) -> None:
        """Build mapping of bar IDs to voice references."""
        if self._root is None:
            return

        bars_section = self._root.find("Bars")
        if bars_section is None:
            logger.warning("No Bars section found in XML")
            return

        for bar in bars_section.findall("Bar"):
            bar_id = bar.get("id")
            if bar_id is None:
                continue

            voices_elem = bar.find("Voices")
            if voices_elem is not None and voices_elem.text:
                # Voice IDs, -1 means unused voice slot
                voice_ids = [v for v in voices_elem.text.strip().split() if v != "-1"]
                self._bars[bar_id] = voice_ids
            else:
                self._bars[bar_id] = []

    def _get_rhythm_duration(self, rhythm_id: Optional[str]) -> float:
        """Get duration in beats for a rhythm ID."""
        if rhythm_id is None or rhythm_id not in self._rhythms:
            return 1.0  # Default to quarter note

        note_value, dots = self._rhythms[rhythm_id]
        base_duration = RHYTHM_DURATIONS.get(note_value, 1.0)

        # Apply dotted note multiplier
        # 1 dot = 1.5x, 2 dots = 1.75x, 3 dots = 1.875x
        if dots > 0:
            multiplier = 2.0 - (1.0 / (2**dots))
            base_duration *= multiplier

        return base_duration

    def _get_bar_onsets_for_track(
        self, bar_id: str, track_bar_ids: list[str]
    ) -> list[float]:
        """Get note onset positions for a specific bar and track.

        Args:
            bar_id: The bar ID to analyze
            track_bar_ids: List of bar IDs for the track at each master bar position

        Returns:
            List of beat positions where notes occur
        """
        if bar_id not in self._bars:
            return []

        onsets: list[float] = []
        voice_ids = self._bars[bar_id]

        for voice_id in voice_ids:
            if voice_id not in self._voices:
                continue

            beat_ids = self._voices[voice_id]
            current_position = 0.0

            for beat_id in beat_ids:
                if beat_id not in self._beats:
                    continue

                rhythm_id, has_notes = self._beats[beat_id]
                duration = self._get_rhythm_duration(rhythm_id)

                if has_notes:
                    onsets.append(current_position)

                current_position += duration

        # Sort and deduplicate (multiple voices may have notes at same position)
        return sorted(set(onsets))

    def _get_time_signature(self, master_bar: etree._Element) -> tuple[int, int]:
        """Extract time signature from MasterBar element."""
        time_elem = master_bar.find("Time")
        if time_elem is not None and time_elem.text:
            try:
                parts = time_elem.text.strip().split("/")
                if len(parts) == 2:
                    return (int(parts[0]), int(parts[1]))
            except ValueError:
                pass
        return (4, 4)  # Default to 4/4

    def _find_track_bar_index(self, track_id: int) -> int:
        """Find which bar index to use for a track in MasterBar.

        In GP files, each MasterBar can have multiple Bars elements,
        one per track. This finds the correct index for our track.
        """
        if self._root is None:
            return 0

        tracks_section = self._root.find("Tracks")
        if tracks_section is None:
            return 0

        # Track index is the position of the track in the Tracks list
        for idx, track in enumerate(tracks_section.findall("Track")):
            if track.get("id") == str(track_id):
                return idx

        return 0

    def parse(self, track_id: int = 0) -> NotationMap:
        """Parse the score and return notation map for specified track.

        Args:
            track_id: Which track to analyze (default 0 = first track, typically bass)

        Returns:
            NotationMap containing all bar notation data
        """
        self._load_xml()
        if self._root is None:
            logger.error("Failed to load XML for notation parsing")
            return NotationMap(track_id=track_id)

        # Build all lookup maps
        self._build_rhythm_map()
        self._build_beat_map()
        self._build_voice_map()
        self._build_bar_map()

        logger.debug(f"Built maps: {len(self._rhythms)} rhythms, {len(self._beats)} beats, "
                     f"{len(self._voices)} voices, {len(self._bars)} bars")

        # Find which bar index to use for this track
        track_bar_index = self._find_track_bar_index(track_id)

        # Parse MasterBars to build notation map
        notation_map = NotationMap(track_id=track_id)
        master_bars_section = self._root.find("MasterBars")

        if master_bars_section is None:
            logger.warning("No MasterBars section found")
            return notation_map

        current_time_sig = (4, 4)

        for bar_index, master_bar in enumerate(master_bars_section.findall("MasterBar")):
            # Check for time signature change
            time_sig = self._get_time_signature(master_bar)
            if time_sig != (0, 0):  # Valid time signature found
                current_time_sig = time_sig

            # Get bar IDs for this master bar position
            bars_elem = master_bar.find("Bars")
            if bars_elem is None or not bars_elem.text:
                # No bars, create empty bar notation
                bar_notation = BarNotation(
                    bar_index=bar_index,
                    time_signature=current_time_sig,
                )
                notation_map.bars.append(bar_notation)
                continue

            bar_ids = bars_elem.text.strip().split()

            # Get the bar ID for our track
            if track_bar_index < len(bar_ids):
                bar_id = bar_ids[track_bar_index]
            else:
                bar_id = bar_ids[0] if bar_ids else None

            # Get note onsets for this bar
            if bar_id:
                onsets = self._get_bar_onsets_for_track(bar_id, bar_ids)
            else:
                onsets = []

            bar_notation = BarNotation(
                bar_index=bar_index,
                time_signature=current_time_sig,
                note_onsets=onsets,
                first_onset=onsets[0] if onsets else None,
            )
            notation_map.bars.append(bar_notation)

        logger.info(f"Parsed {len(notation_map.bars)} bars for track {track_id}")
        bars_with_notes = sum(1 for b in notation_map.bars if b.has_notes)
        logger.debug(f"Bars with notes: {bars_with_notes}")

        return notation_map
