"""Tests for the NotationParser class."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from lxml import etree

from guitarprotool.core.notation_parser import (
    NotationParser,
    NotationMap,
    BarNotation,
    RHYTHM_DURATIONS,
)


class TestRhythmDurations:
    """Test rhythm duration constants."""

    def test_standard_durations(self):
        """Test that standard rhythm values have correct durations."""
        assert RHYTHM_DURATIONS["Whole"] == 4.0
        assert RHYTHM_DURATIONS["Half"] == 2.0
        assert RHYTHM_DURATIONS["Quarter"] == 1.0
        assert RHYTHM_DURATIONS["Eighth"] == 0.5
        assert RHYTHM_DURATIONS["16th"] == 0.25
        assert RHYTHM_DURATIONS["32nd"] == 0.125


class TestBarNotation:
    """Test BarNotation dataclass."""

    def test_has_notes_with_notes(self):
        """Test has_notes is True when notes are present."""
        bar = BarNotation(
            bar_index=0,
            time_signature=(4, 4),
            note_onsets=[0.0, 1.0, 2.0, 3.0],
            first_onset=0.0,
        )
        assert bar.has_notes is True

    def test_has_notes_empty(self):
        """Test has_notes is False when no notes (rest bar)."""
        bar = BarNotation(
            bar_index=0,
            time_signature=(4, 4),
            note_onsets=[],
            first_onset=None,
        )
        assert bar.has_notes is False

    def test_beats_per_bar_4_4(self):
        """Test beats_per_bar calculation for 4/4 time."""
        bar = BarNotation(bar_index=0, time_signature=(4, 4))
        assert bar.beats_per_bar == 4.0

    def test_beats_per_bar_3_4(self):
        """Test beats_per_bar calculation for 3/4 time."""
        bar = BarNotation(bar_index=0, time_signature=(3, 4))
        assert bar.beats_per_bar == 3.0

    def test_beats_per_bar_6_8(self):
        """Test beats_per_bar calculation for 6/8 time."""
        bar = BarNotation(bar_index=0, time_signature=(6, 8))
        assert bar.beats_per_bar == 3.0  # 6 eighth notes = 3 quarter note beats


class TestNotationMap:
    """Test NotationMap dataclass."""

    def test_total_bars(self):
        """Test total_bars property."""
        bars = [
            BarNotation(bar_index=0, time_signature=(4, 4)),
            BarNotation(bar_index=1, time_signature=(4, 4)),
        ]
        notation_map = NotationMap(bars=bars)
        assert notation_map.total_bars == 2

    def test_get_bar_valid(self):
        """Test get_bar returns correct bar."""
        bar0 = BarNotation(bar_index=0, time_signature=(4, 4), note_onsets=[0.0])
        bar1 = BarNotation(bar_index=1, time_signature=(4, 4), note_onsets=[0.0, 2.0])
        notation_map = NotationMap(bars=[bar0, bar1])

        result = notation_map.get_bar(1)
        assert result == bar1
        assert result.note_onsets == [0.0, 2.0]

    def test_get_bar_invalid(self):
        """Test get_bar returns None for invalid index."""
        bar0 = BarNotation(bar_index=0, time_signature=(4, 4))
        notation_map = NotationMap(bars=[bar0])

        assert notation_map.get_bar(-1) is None
        assert notation_map.get_bar(5) is None

    def test_get_expected_onsets(self):
        """Test get_expected_onsets returns correct values."""
        bar = BarNotation(bar_index=0, time_signature=(4, 4), note_onsets=[0.0, 2.5, 3.0])
        notation_map = NotationMap(bars=[bar])

        onsets = notation_map.get_expected_onsets(0)
        assert onsets == [0.0, 2.5, 3.0]

    def test_get_expected_onsets_invalid_bar(self):
        """Test get_expected_onsets returns empty list for invalid bar."""
        notation_map = NotationMap(bars=[])
        assert notation_map.get_expected_onsets(0) == []


class TestNotationParser:
    """Test NotationParser class."""

    def test_init(self, tmp_path):
        """Test NotationParser initialization."""
        gpif_path = tmp_path / "score.gpif"
        gpif_path.write_text("<GPIF></GPIF>")

        parser = NotationParser(gpif_path)
        assert parser.gpif_path == gpif_path

    def test_get_rhythm_duration_quarter(self):
        """Test rhythm duration calculation for quarter note."""
        parser = NotationParser(Path("/fake/path"))
        parser._rhythms = {"0": ("Quarter", 0)}

        duration = parser._get_rhythm_duration("0")
        assert duration == 1.0

    def test_get_rhythm_duration_dotted_quarter(self):
        """Test rhythm duration calculation for dotted quarter note."""
        parser = NotationParser(Path("/fake/path"))
        parser._rhythms = {"0": ("Quarter", 1)}

        duration = parser._get_rhythm_duration("0")
        assert duration == 1.5  # 1.0 * 1.5

    def test_get_rhythm_duration_double_dotted(self):
        """Test rhythm duration calculation for double-dotted note."""
        parser = NotationParser(Path("/fake/path"))
        parser._rhythms = {"0": ("Quarter", 2)}

        duration = parser._get_rhythm_duration("0")
        assert duration == 1.75  # 1.0 * 1.75

    def test_get_rhythm_duration_unknown(self):
        """Test rhythm duration returns 1.0 for unknown rhythm."""
        parser = NotationParser(Path("/fake/path"))
        parser._rhythms = {}

        duration = parser._get_rhythm_duration("unknown")
        assert duration == 1.0

    def test_get_time_signature(self):
        """Test time signature extraction from MasterBar."""
        parser = NotationParser(Path("/fake/path"))
        xml = "<MasterBar><Time>3/4</Time></MasterBar>"
        master_bar = etree.fromstring(xml)

        time_sig = parser._get_time_signature(master_bar)
        assert time_sig == (3, 4)

    def test_get_time_signature_default(self):
        """Test time signature defaults to 4/4."""
        parser = NotationParser(Path("/fake/path"))
        xml = "<MasterBar></MasterBar>"
        master_bar = etree.fromstring(xml)

        time_sig = parser._get_time_signature(master_bar)
        assert time_sig == (4, 4)


class TestNotationParserIntegration:
    """Integration tests using fixture files."""

    def test_parse_simple_song(self, simple_gp_file):
        """Test parsing notation from simple_song fixture."""
        # Extract the GP file to get gpif path
        import zipfile
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            with zipfile.ZipFile(simple_gp_file, 'r') as zf:
                zf.extractall(temp_path)

            # Find gpif file
            gpif_path = temp_path / "score.gpif"
            if not gpif_path.exists():
                gpif_path = temp_path / "Content" / "score.gpif"

            if gpif_path.exists():
                parser = NotationParser(gpif_path)
                notation_map = parser.parse(track_id=0)

                # Should have parsed some bars
                assert notation_map.total_bars > 0

                # Check that some bars have notes
                bars_with_notes = sum(1 for b in notation_map.bars if b.has_notes)
                assert bars_with_notes > 0


@pytest.fixture
def simple_gp_file():
    """Return path to simple_song fixture if it exists."""
    fixture_path = Path(__file__).parent / "fixtures" / "simple_song" / "input.gp"
    if fixture_path.exists():
        return fixture_path
    pytest.skip("simple_song fixture not available")
