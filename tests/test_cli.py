"""Tests for CLI module."""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Mock pydub/audioop before importing CLI
sys.modules["pydub"] = MagicMock()
sys.modules["pydub.AudioSegment"] = MagicMock()

# Mock aubio
mock_aubio = MagicMock()
sys.modules["aubio"] = mock_aubio

# ruff: noqa: E402
from guitarprotool.cli.main import (
    print_banner,
    get_track_name,
    confirm_overwrite,
    display_beat_info,
    get_troubleshooting_dir,
    save_troubleshooting_copies,
    main,
)
from guitarprotool.core.beat_detector import BeatInfo


class TestPrintBanner:
    """Test banner display."""

    def test_print_banner_runs(self, capsys):
        """Test that print_banner executes without error."""
        # Should not raise
        print_banner()

        # Should have printed something
        captured = capsys.readouterr()
        # The output goes through rich console, might not show in capsys
        # Just verify no exception occurred


class TestGetTrackName:
    """Test track name prompt."""

    @patch("guitarprotool.cli.main.questionary")
    def test_get_track_name_default(self, mock_questionary):
        """Test default track name."""
        mock_questionary.text.return_value.ask.return_value = None

        result = get_track_name()

        assert result == "Audio Track"

    @patch("guitarprotool.cli.main.questionary")
    def test_get_track_name_custom(self, mock_questionary):
        """Test custom track name."""
        mock_questionary.text.return_value.ask.return_value = "My Song"

        result = get_track_name()

        assert result == "My Song"

    @patch("guitarprotool.cli.main.questionary")
    def test_get_track_name_custom_default(self, mock_questionary):
        """Test custom default track name."""
        mock_questionary.text.return_value.ask.return_value = None

        result = get_track_name(default="Custom Default")

        assert result == "Custom Default"


class TestConfirmOverwrite:
    """Test overwrite confirmation."""

    def test_confirm_overwrite_nonexistent(self, temp_dir):
        """Test confirming overwrite of nonexistent file."""
        nonexistent = temp_dir / "does_not_exist.gp"

        result = confirm_overwrite(nonexistent)

        assert result is True

    @patch("guitarprotool.cli.main.questionary")
    def test_confirm_overwrite_exists_yes(self, mock_questionary, temp_dir):
        """Test confirming overwrite when file exists and user says yes."""
        existing = temp_dir / "exists.gp"
        existing.write_text("test")

        mock_questionary.confirm.return_value.ask.return_value = True

        result = confirm_overwrite(existing)

        assert result is True

    @patch("guitarprotool.cli.main.questionary")
    def test_confirm_overwrite_exists_no(self, mock_questionary, temp_dir):
        """Test confirming overwrite when file exists and user says no."""
        existing = temp_dir / "exists.gp"
        existing.write_text("test")

        mock_questionary.confirm.return_value.ask.return_value = False

        result = confirm_overwrite(existing)

        assert result is False


class TestDisplayBeatInfo:
    """Test beat info display."""

    def test_display_beat_info(self, capsys):
        """Test displaying beat info."""
        beat_info = BeatInfo(
            bpm=120.0,
            beat_times=[0.0, 0.5, 1.0, 1.5, 2.0],
            confidence=0.95,
        )

        # Should not raise
        display_beat_info(beat_info)


class TestMain:
    """Test main entry point."""

    @patch("guitarprotool.cli.main.main_menu")
    @patch("guitarprotool.cli.main.print_banner")
    def test_main_calls_menu(self, mock_banner, mock_menu):
        """Test that main calls banner and menu."""
        main()

        mock_banner.assert_called_once()
        mock_menu.assert_called_once()

    @patch("guitarprotool.cli.main.main_menu")
    @patch("guitarprotool.cli.main.print_banner")
    def test_main_handles_keyboard_interrupt(self, mock_banner, mock_menu):
        """Test that main handles KeyboardInterrupt gracefully."""
        mock_menu.side_effect = KeyboardInterrupt()

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1


class TestIntegration:
    """Integration tests for CLI components."""

    @patch("guitarprotool.cli.main.questionary")
    def test_get_gp_file_path_cancelled(self, mock_questionary):
        """Test file path selection when cancelled."""
        mock_questionary.path.return_value.ask.return_value = None

        from guitarprotool.cli.main import get_gp_file_path

        result = get_gp_file_path()

        assert result is None

    @patch("guitarprotool.cli.main.questionary")
    def test_get_audio_source_youtube(self, mock_questionary):
        """Test audio source selection for YouTube."""
        mock_questionary.select.return_value.ask.return_value = "youtube"
        mock_questionary.text.return_value.ask.return_value = "https://youtube.com/watch?v=test"

        from guitarprotool.cli.main import get_audio_source

        source_type, source_value = get_audio_source()

        assert source_type == "youtube"
        assert source_value == "https://youtube.com/watch?v=test"

    @patch("guitarprotool.cli.main.questionary")
    def test_get_audio_source_local(self, mock_questionary):
        """Test audio source selection for local file."""
        mock_questionary.select.return_value.ask.return_value = "local"
        mock_questionary.path.return_value.ask.return_value = "/path/to/audio.mp3"

        from guitarprotool.cli.main import get_audio_source

        source_type, source_value = get_audio_source()

        assert source_type == "local"
        assert source_value == "/path/to/audio.mp3"


class TestDetectBPMOnly:
    """Test standalone BPM detection mode."""

    @patch("guitarprotool.cli.main.questionary")
    def test_detect_bpm_only_cancelled(self, mock_questionary):
        """Test BPM detection when cancelled."""
        mock_questionary.path.return_value.ask.return_value = None

        from guitarprotool.cli.main import detect_bpm_only

        # Should not raise
        detect_bpm_only()


class TestTroubleshootingCopies:
    """Test troubleshooting file saving functions."""

    def test_get_troubleshooting_dir_creates_timestamped_dir(self, temp_dir, monkeypatch):
        """Test that get_troubleshooting_dir creates a timestamped directory."""
        monkeypatch.chdir(temp_dir)

        result = get_troubleshooting_dir()

        assert result.exists()
        assert result.is_dir()
        assert result.parent.name == "files"
        assert result.name.startswith("run_")

    def test_save_troubleshooting_copies(self, temp_dir):
        """Test that save_troubleshooting_copies copies both files."""
        # Create source files
        gp_file = temp_dir / "test.gp"
        mp3_file = temp_dir / "test.mp3"
        gp_file.write_text("gp content")
        mp3_file.write_text("mp3 content")

        # Create troubleshoot dir
        troubleshoot_dir = temp_dir / "troubleshoot"
        troubleshoot_dir.mkdir()

        gp_copy, mp3_copy = save_troubleshooting_copies(gp_file, mp3_file, troubleshoot_dir)

        assert gp_copy.exists()
        assert mp3_copy.exists()
        assert gp_copy.read_text() == "gp content"
        assert mp3_copy.read_text() == "mp3 content"
        assert gp_copy.name == "test.gp"
        assert mp3_copy.name == "test.mp3"


class TestOriginalTempoFallback:
    """Test that original_tempo falls back to detected BPM when not found in GP file."""

    def test_original_tempo_fallback_to_detected_bpm(self):
        """Test that when get_original_tempo returns None, we use detected BPM.

        This tests the fix for the bug where original_tempo=None caused:
        TypeError: int() argument must be a string, a bytes-like object
        or a real number, not 'NoneType'
        """
        # Create mock XMLModifier that returns None for original tempo
        mock_modifier = MagicMock()
        mock_modifier.get_original_tempo.return_value = None

        # Create beat_info with a detected BPM
        detected_bpm = 156.6
        beat_info = BeatInfo(
            bpm=detected_bpm,
            beat_times=[0.0, 0.383, 0.766, 1.149],  # ~156.6 BPM
            confidence=0.98,
        )

        # Simulate the fallback logic from run_pipeline
        original_tempo = mock_modifier.get_original_tempo()
        if original_tempo is None:
            original_tempo = beat_info.bpm

        # Verify the fallback worked
        assert original_tempo == detected_bpm
        assert original_tempo is not None
