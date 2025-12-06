"""Tests for XMLModifier class."""

import tempfile
from pathlib import Path

import pytest
from lxml import etree

from guitarprotool.core.xml_modifier import (
    XMLModifier,
    SyncPoint,
    AssetInfo,
    BackingTrackConfig,
)
from guitarprotool.utils.exceptions import (
    XMLParseError,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def minimal_gpif(temp_dir):
    """Create a minimal valid score.gpif file."""
    gpif_path = temp_dir / "score.gpif"
    content = """<?xml version="1.0" encoding="UTF-8"?>
<GPIF>
    <GPRevision>8000</GPRevision>
    <Score>
        <Title>Test Song</Title>
        <Artist>Test Artist</Artist>
    </Score>
    <MasterTrack>
        <Tracks>0</Tracks>
        <Automations>
            <Automation>
                <Type>Tempo</Type>
                <Value>120</Value>
            </Automation>
        </Automations>
    </MasterTrack>
    <Tracks>
        <Track id="0">
            <Name>Guitar</Name>
        </Track>
    </Tracks>
    <MasterBars>
        <MasterBar>
            <Key><AccidentalCount>0</AccidentalCount></Key>
            <Time>4/4</Time>
        </MasterBar>
        <MasterBar>
            <Key><AccidentalCount>0</AccidentalCount></Key>
            <Time>4/4</Time>
        </MasterBar>
    </MasterBars>
    <Bars></Bars>
    <Voices></Voices>
    <Beats></Beats>
    <Notes></Notes>
    <Rhythms></Rhythms>
</GPIF>"""
    gpif_path.write_text(content)
    return gpif_path


@pytest.fixture
def gpif_with_backing_track(temp_dir):
    """Create a score.gpif file with existing BackingTrack."""
    gpif_path = temp_dir / "score.gpif"
    content = """<?xml version="1.0" encoding="UTF-8"?>
<GPIF>
    <GPRevision>8000</GPRevision>
    <Score>
        <Title>Test Song</Title>
    </Score>
    <MasterTrack>
        <Tracks>0</Tracks>
        <Automations></Automations>
    </MasterTrack>
    <BackingTrack>
        <IconId>21</IconId>
        <Name><![CDATA[Existing Track]]></Name>
        <AssetId>99</AssetId>
    </BackingTrack>
    <Tracks>
        <Track id="0">
            <Name>Guitar</Name>
        </Track>
    </Tracks>
    <Rhythms></Rhythms>
    <Assets>
        <Asset id="99">
            <OriginalFilePath><![CDATA[/old/path.mp3]]></OriginalFilePath>
            <OriginalFileSha1><![CDATA[old-uuid-here]]></OriginalFileSha1>
            <EmbeddedFilePath><![CDATA[Content/Assets/old-uuid-here.mp3]]></EmbeddedFilePath>
        </Asset>
    </Assets>
</GPIF>"""
    gpif_path.write_text(content)
    return gpif_path


@pytest.fixture
def gpif_without_automations(temp_dir):
    """Create a score.gpif file without Automations element."""
    gpif_path = temp_dir / "score.gpif"
    content = """<?xml version="1.0" encoding="UTF-8"?>
<GPIF>
    <Score><Title>Test</Title></Score>
    <MasterTrack>
        <Tracks>0</Tracks>
    </MasterTrack>
    <Tracks>
        <Track id="0"><Name>Guitar</Name></Track>
    </Tracks>
    <Rhythms></Rhythms>
</GPIF>"""
    gpif_path.write_text(content)
    return gpif_path


@pytest.fixture
def invalid_xml(temp_dir):
    """Create an invalid XML file."""
    gpif_path = temp_dir / "score.gpif"
    gpif_path.write_text("This is not valid XML <broken>")
    return gpif_path


@pytest.fixture
def sample_sync_points():
    """Create sample sync points for testing."""
    return [
        SyncPoint(bar=0, frame_offset=0, modified_tempo=120.0, original_tempo=120.0),
        SyncPoint(bar=4, frame_offset=88200, modified_tempo=119.5, original_tempo=120.0),
        SyncPoint(bar=8, frame_offset=176400, modified_tempo=120.2, original_tempo=120.0),
    ]


@pytest.fixture
def sample_asset_info():
    """Create sample asset info for testing."""
    return AssetInfo(
        asset_id=0,
        uuid="abc12345-6789-0def-ghij-klmnopqrstuv",
        original_file_path="/Users/test/Music/song.mp3",
    )


# =============================================================================
# XMLModifier Initialization Tests
# =============================================================================


class TestXMLModifierInit:
    """Tests for XMLModifier initialization."""

    def test_init_with_valid_path(self, minimal_gpif):
        """Test initialization with valid gpif path."""
        modifier = XMLModifier(minimal_gpif)
        assert modifier.gpif_path == minimal_gpif
        assert not modifier._is_loaded

    def test_init_with_nonexistent_path(self, temp_dir):
        """Test initialization with nonexistent file raises error."""
        with pytest.raises(FileNotFoundError, match="score.gpif not found"):
            XMLModifier(temp_dir / "nonexistent.gpif")

    def test_init_accepts_string_path(self, minimal_gpif):
        """Test initialization accepts string path."""
        modifier = XMLModifier(str(minimal_gpif))
        assert modifier.gpif_path == minimal_gpif


# =============================================================================
# XMLModifier Load Tests
# =============================================================================


class TestXMLModifierLoad:
    """Tests for XMLModifier.load()."""

    def test_load_valid_xml(self, minimal_gpif):
        """Test loading valid XML file."""
        modifier = XMLModifier(minimal_gpif)
        modifier.load()
        assert modifier._is_loaded
        assert modifier._root is not None
        assert modifier._root.tag == "GPIF"

    def test_load_idempotent(self, minimal_gpif):
        """Test that calling load() twice doesn't error."""
        modifier = XMLModifier(minimal_gpif)
        modifier.load()
        modifier.load()  # Should just warn and return
        assert modifier._is_loaded

    def test_load_invalid_xml(self, invalid_xml):
        """Test loading invalid XML raises XMLParseError."""
        modifier = XMLModifier(invalid_xml)
        with pytest.raises(XMLParseError, match="Failed to parse XML"):
            modifier.load()


# =============================================================================
# XMLModifier Save Tests
# =============================================================================


class TestXMLModifierSave:
    """Tests for XMLModifier.save()."""

    def test_save_overwrites_original(self, minimal_gpif):
        """Test save overwrites original file by default."""
        modifier = XMLModifier(minimal_gpif)
        modifier.load()

        result = modifier.save()
        assert result == minimal_gpif
        assert minimal_gpif.exists()

    def test_save_to_new_path(self, minimal_gpif, temp_dir):
        """Test save to new path."""
        modifier = XMLModifier(minimal_gpif)
        modifier.load()

        new_path = temp_dir / "new_score.gpif"
        result = modifier.save(new_path)
        assert result == new_path
        assert new_path.exists()

    def test_save_without_load_raises_error(self, minimal_gpif):
        """Test save without load raises error."""
        modifier = XMLModifier(minimal_gpif)
        with pytest.raises(XMLParseError, match="XML not loaded"):
            modifier.save()

    def test_save_preserves_content(self, minimal_gpif, temp_dir):
        """Test that save preserves XML content."""
        modifier = XMLModifier(minimal_gpif)
        modifier.load()

        new_path = temp_dir / "saved.gpif"
        modifier.save(new_path)

        # Reload and verify
        saved_tree = etree.parse(str(new_path))
        saved_root = saved_tree.getroot()
        assert saved_root.tag == "GPIF"
        assert saved_root.find("Score/Title").text == "Test Song"


# =============================================================================
# BackingTrack Injection Tests
# =============================================================================


class TestInjectBackingTrack:
    """Tests for XMLModifier.inject_backing_track()."""

    def test_inject_backing_track_default_config(self, minimal_gpif):
        """Test injecting BackingTrack with default configuration."""
        modifier = XMLModifier(minimal_gpif)
        modifier.load()
        modifier.inject_backing_track()

        backing_track = modifier._root.find("BackingTrack")
        assert backing_track is not None
        assert backing_track.find("IconId").text == "21"
        assert backing_track.find("Name").text == "Audio Track"
        assert backing_track.find("AssetId").text == "0"
        assert backing_track.find("Enabled").text == "true"

    def test_inject_backing_track_custom_config(self, minimal_gpif):
        """Test injecting BackingTrack with custom configuration."""
        modifier = XMLModifier(minimal_gpif)
        modifier.load()

        config = BackingTrackConfig(
            name="My Custom Track",
            short_name="custom",
            asset_id=5,
            playback_state="Solo",
            frame_padding=-1000,
            semitones=-2,
            cents=50,
        )
        modifier.inject_backing_track(config)

        backing_track = modifier._root.find("BackingTrack")
        assert backing_track.find("Name").text == "My Custom Track"
        assert backing_track.find("ShortName").text == "custom"
        assert backing_track.find("AssetId").text == "5"
        assert backing_track.find("PlaybackState").text == "Solo"
        assert backing_track.find("FramePadding").text == "-1000"
        assert backing_track.find("Semitones").text == "-2"
        assert backing_track.find("Cents").text == "50"

    def test_inject_backing_track_replaces_existing(self, gpif_with_backing_track):
        """Test that injecting replaces existing BackingTrack."""
        modifier = XMLModifier(gpif_with_backing_track)
        modifier.load()

        # Verify existing track
        assert modifier._root.find("BackingTrack/Name").text == "Existing Track"

        # Inject new track
        config = BackingTrackConfig(name="New Track", asset_id=0)
        modifier.inject_backing_track(config)

        # Verify replacement
        assert modifier._root.find("BackingTrack/Name").text == "New Track"
        assert len(modifier._root.findall("BackingTrack")) == 1

    def test_inject_backing_track_position(self, minimal_gpif):
        """Test BackingTrack is inserted after MasterTrack, before Tracks."""
        modifier = XMLModifier(minimal_gpif)
        modifier.load()
        modifier.inject_backing_track()

        children = list(modifier._root)
        tags = [child.tag for child in children]

        master_idx = tags.index("MasterTrack")
        backing_idx = tags.index("BackingTrack")
        tracks_idx = tags.index("Tracks")

        assert master_idx < backing_idx < tracks_idx

    def test_inject_backing_track_without_load_raises_error(self, minimal_gpif):
        """Test inject without load raises error."""
        modifier = XMLModifier(minimal_gpif)
        with pytest.raises(XMLParseError, match="XML not loaded"):
            modifier.inject_backing_track()

    def test_inject_backing_track_channel_strip(self, minimal_gpif):
        """Test BackingTrack includes ChannelStrip with Parameters."""
        modifier = XMLModifier(minimal_gpif)
        modifier.load()
        modifier.inject_backing_track()

        channel_strip = modifier._root.find("BackingTrack/ChannelStrip")
        assert channel_strip is not None
        params = channel_strip.find("Parameters")
        assert params is not None
        assert "0.500000" in params.text


# =============================================================================
# Asset Injection Tests
# =============================================================================


class TestInjectAsset:
    """Tests for XMLModifier.inject_asset()."""

    def test_inject_asset_creates_assets_section(self, minimal_gpif, sample_asset_info):
        """Test asset injection creates Assets section if missing."""
        modifier = XMLModifier(minimal_gpif)
        modifier.load()

        # Verify no Assets section
        assert modifier._root.find("Assets") is None

        modifier.inject_asset(sample_asset_info)

        # Verify Assets created
        assets = modifier._root.find("Assets")
        assert assets is not None
        assert len(assets) == 1

    def test_inject_asset_content(self, minimal_gpif, sample_asset_info):
        """Test asset injection creates correct content."""
        modifier = XMLModifier(minimal_gpif)
        modifier.load()
        modifier.inject_asset(sample_asset_info)

        asset = modifier._root.find("Assets/Asset[@id='0']")
        assert asset is not None
        assert asset.find("OriginalFilePath").text == sample_asset_info.original_file_path
        assert asset.find("OriginalFileSha1").text == sample_asset_info.uuid
        assert asset.find("EmbeddedFilePath").text == sample_asset_info.embedded_file_path

    def test_inject_asset_replaces_existing(self, gpif_with_backing_track):
        """Test asset injection replaces existing asset with same ID."""
        modifier = XMLModifier(gpif_with_backing_track)
        modifier.load()

        new_asset = AssetInfo(
            asset_id=99,  # Same ID as existing
            uuid="new-uuid-here",
            original_file_path="/new/path.mp3",
        )
        modifier.inject_asset(new_asset)

        # Should only have one asset with id=99
        assets = modifier._root.findall("Assets/Asset[@id='99']")
        assert len(assets) == 1
        assert assets[0].find("OriginalFileSha1").text == "new-uuid-here"

    def test_inject_multiple_assets(self, minimal_gpif):
        """Test injecting multiple assets."""
        modifier = XMLModifier(minimal_gpif)
        modifier.load()

        asset1 = AssetInfo(asset_id=0, uuid="uuid-1", original_file_path="/path1.mp3")
        asset2 = AssetInfo(asset_id=1, uuid="uuid-2", original_file_path="/path2.mp3")

        modifier.inject_asset(asset1)
        modifier.inject_asset(asset2)

        assets = modifier._root.find("Assets")
        assert len(assets) == 2

    def test_inject_asset_without_load_raises_error(self, minimal_gpif, sample_asset_info):
        """Test inject without load raises error."""
        modifier = XMLModifier(minimal_gpif)
        with pytest.raises(XMLParseError, match="XML not loaded"):
            modifier.inject_asset(sample_asset_info)

    def test_asset_info_embedded_path(self, sample_asset_info):
        """Test AssetInfo auto-generates embedded file path."""
        assert sample_asset_info.embedded_file_path == (
            f"Content/Assets/{sample_asset_info.uuid}.mp3"
        )


# =============================================================================
# SyncPoint Injection Tests
# =============================================================================


class TestInjectSyncPoints:
    """Tests for XMLModifier.inject_sync_points()."""

    def test_inject_sync_points(self, minimal_gpif, sample_sync_points):
        """Test injecting sync points."""
        modifier = XMLModifier(minimal_gpif)
        modifier.load()
        modifier.inject_sync_points(sample_sync_points)

        automations = modifier._root.find("MasterTrack/Automations")
        sync_automations = automations.findall("Automation[Type='SyncPoint']")
        assert len(sync_automations) == 3

    def test_inject_sync_points_content(self, minimal_gpif):
        """Test sync point content is correct."""
        modifier = XMLModifier(minimal_gpif)
        modifier.load()

        sync_point = SyncPoint(
            bar=5,
            position=2,
            frame_offset=123456,
            modified_tempo=119.5,
            original_tempo=120.0,
            bar_occurrence=1,
        )
        modifier.inject_sync_points([sync_point])

        automation = modifier._root.find("MasterTrack/Automations/Automation[Type='SyncPoint']")
        assert automation.find("Bar").text == "5"
        assert automation.find("Position").text == "2"
        assert automation.find("Value/BarIndex").text == "5"
        assert automation.find("Value/BarOccurrence").text == "1"
        assert automation.find("Value/FrameOffset").text == "123456"
        assert automation.find("Value/ModifiedTempo").text == "119.500"
        assert automation.find("Value/OriginalTempo").text == "120"

    def test_inject_sync_points_creates_automations(self, gpif_without_automations):
        """Test sync point injection creates Automations if missing."""
        modifier = XMLModifier(gpif_without_automations)
        modifier.load()

        sync_point = SyncPoint(bar=0, frame_offset=0, modified_tempo=120.0, original_tempo=120.0)
        modifier.inject_sync_points([sync_point])

        automations = modifier._root.find("MasterTrack/Automations")
        assert automations is not None

    def test_inject_sync_points_replaces_existing(self, minimal_gpif, sample_sync_points):
        """Test injecting sync points replaces existing ones."""
        modifier = XMLModifier(minimal_gpif)
        modifier.load()

        # Inject first batch
        modifier.inject_sync_points(sample_sync_points)

        # Inject second batch (should replace)
        new_points = [SyncPoint(bar=0, frame_offset=0, modified_tempo=100.0, original_tempo=100.0)]
        modifier.inject_sync_points(new_points)

        automations = modifier._root.find("MasterTrack/Automations")
        sync_automations = automations.findall("Automation[Type='SyncPoint']")
        assert len(sync_automations) == 1
        assert sync_automations[0].find("Value/ModifiedTempo").text == "100.000"

    def test_inject_empty_sync_points(self, minimal_gpif):
        """Test injecting empty list does nothing."""
        modifier = XMLModifier(minimal_gpif)
        modifier.load()
        modifier.inject_sync_points([])

        # Should not create any sync points
        automations = modifier._root.find("MasterTrack/Automations")
        sync_automations = automations.findall("Automation[Type='SyncPoint']")
        assert len(sync_automations) == 0

    def test_inject_sync_points_preserves_tempo_automation(self, minimal_gpif, sample_sync_points):
        """Test sync point injection preserves existing Tempo automation."""
        modifier = XMLModifier(minimal_gpif)
        modifier.load()
        modifier.inject_sync_points(sample_sync_points)

        # Tempo automation should still exist
        tempo = modifier._root.find("MasterTrack/Automations/Automation[Type='Tempo']")
        assert tempo is not None
        assert tempo.find("Value").text == "120"


# =============================================================================
# Helper Method Tests
# =============================================================================


class TestHelperMethods:
    """Tests for XMLModifier helper methods."""

    def test_get_original_tempo(self, minimal_gpif):
        """Test extracting original tempo."""
        modifier = XMLModifier(minimal_gpif)
        modifier.load()

        tempo = modifier.get_original_tempo()
        assert tempo == 120.0

    def test_get_original_tempo_not_found(self, gpif_without_automations):
        """Test get_original_tempo returns None when not found."""
        modifier = XMLModifier(gpif_without_automations)
        modifier.load()

        tempo = modifier.get_original_tempo()
        assert tempo is None

    def test_get_original_tempo_space_separated(self, temp_dir):
        """Test extracting tempo when value is space-separated (e.g., '78 2').

        Some GP8 files store tempo as 'BPM BEAT_TYPE' format.
        We should extract only the BPM (first value).
        """
        gpif_path = temp_dir / "score_space_tempo.gpif"
        content = """<?xml version="1.0" encoding="UTF-8"?>
<GPIF>
    <MasterTrack>
        <Tracks>0</Tracks>
        <Automations>
            <Automation>
                <Type>Tempo</Type>
                <Linear>false</Linear>
                <Bar>0</Bar>
                <Position>0</Position>
                <Visible>true</Visible>
                <Value>78 2</Value>
            </Automation>
        </Automations>
    </MasterTrack>
</GPIF>"""
        gpif_path.write_text(content)

        modifier = XMLModifier(gpif_path)
        modifier.load()

        tempo = modifier.get_original_tempo()
        assert tempo == 78.0

    def test_get_bar_count(self, minimal_gpif):
        """Test getting bar count."""
        modifier = XMLModifier(minimal_gpif)
        modifier.load()

        count = modifier.get_bar_count()
        assert count == 2

    def test_get_bar_count_no_bars(self, gpif_without_automations):
        """Test get_bar_count returns 0 when no MasterBars."""
        modifier = XMLModifier(gpif_without_automations)
        modifier.load()

        count = modifier.get_bar_count()
        assert count == 0

    def test_has_backing_track_false(self, minimal_gpif):
        """Test has_backing_track returns False when none exists."""
        modifier = XMLModifier(minimal_gpif)
        modifier.load()
        assert not modifier.has_backing_track()

    def test_has_backing_track_true(self, gpif_with_backing_track):
        """Test has_backing_track returns True when exists."""
        modifier = XMLModifier(gpif_with_backing_track)
        modifier.load()
        assert modifier.has_backing_track()

    def test_has_assets_false(self, minimal_gpif):
        """Test has_assets returns False when none exists."""
        modifier = XMLModifier(minimal_gpif)
        modifier.load()
        assert not modifier.has_assets()

    def test_has_assets_true(self, gpif_with_backing_track):
        """Test has_assets returns True when exists."""
        modifier = XMLModifier(gpif_with_backing_track)
        modifier.load()
        assert modifier.has_assets()


# =============================================================================
# Data Class Tests
# =============================================================================


class TestDataClasses:
    """Tests for data classes."""

    def test_sync_point_defaults(self):
        """Test SyncPoint default values."""
        sp = SyncPoint(bar=0, frame_offset=0, modified_tempo=120.0, original_tempo=120.0)
        assert sp.position == 0
        assert sp.bar_occurrence == 0

    def test_backing_track_config_defaults(self):
        """Test BackingTrackConfig default values."""
        config = BackingTrackConfig()
        assert config.name == "Audio Track"
        assert config.short_name == "a.track"
        assert config.asset_id == 0
        assert config.playback_state == "Default"
        assert config.enabled is True
        assert config.frame_padding == 0
        assert config.semitones == 0
        assert config.cents == 0

    def test_asset_info_embedded_path_generation(self):
        """Test AssetInfo generates embedded path correctly."""
        asset = AssetInfo(
            asset_id=0,
            uuid="test-uuid-1234",
            original_file_path="/path/to/file.mp3",
        )
        assert asset.embedded_file_path == "Content/Assets/test-uuid-1234.mp3"


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for full injection workflow."""

    def test_full_injection_workflow(self, minimal_gpif, temp_dir):
        """Test complete audio injection workflow."""
        modifier = XMLModifier(minimal_gpif)
        modifier.load()

        # Inject asset
        asset = AssetInfo(
            asset_id=0,
            uuid="d47e6e00-5294-5fba-a78d-aad81b5856ca",
            original_file_path="/Users/test/song.mp3",
        )
        modifier.inject_asset(asset)

        # Inject backing track
        config = BackingTrackConfig(
            name="Test Song Audio",
            asset_id=0,
            playback_state="Default",
        )
        modifier.inject_backing_track(config)

        # Inject sync points
        sync_points = [
            SyncPoint(bar=0, frame_offset=0, modified_tempo=120.0, original_tempo=120.0),
            SyncPoint(bar=4, frame_offset=88200, modified_tempo=120.0, original_tempo=120.0),
        ]
        modifier.inject_sync_points(sync_points)

        # Save to new file
        output_path = temp_dir / "modified.gpif"
        modifier.save(output_path)

        # Reload and verify
        new_modifier = XMLModifier(output_path)
        new_modifier.load()

        assert new_modifier.has_backing_track()
        assert new_modifier.has_assets()

        # Verify structure
        root = new_modifier._root
        assert root.find("BackingTrack/Name").text == "Test Song Audio"
        assert root.find("Assets/Asset[@id='0']/OriginalFileSha1").text == asset.uuid

        sync_automations = root.findall("MasterTrack/Automations/Automation[Type='SyncPoint']")
        assert len(sync_automations) == 2

    def test_roundtrip_preservation(self, minimal_gpif, temp_dir):
        """Test that loading and saving preserves essential content."""
        modifier = XMLModifier(minimal_gpif)
        modifier.load()

        output_path = temp_dir / "roundtrip.gpif"
        modifier.save(output_path)

        # Parse both and compare key elements
        original = etree.parse(str(minimal_gpif))
        saved = etree.parse(str(output_path))

        assert original.find(".//Title").text == saved.find(".//Title").text
        assert original.find(".//Artist").text == saved.find(".//Artist").text
