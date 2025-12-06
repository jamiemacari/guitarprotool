"""XML modification module for Guitar Pro 8 files.

This module handles:
- Parsing score.gpif XML files using lxml
- Injecting BackingTrack elements for audio playback
- Adding Asset elements to reference embedded audio files
- Creating SyncPoint automations for audio-tab synchronization
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from lxml import etree
from loguru import logger

from guitarprotool.utils.exceptions import (
    XMLParseError,
    XMLStructureError,
    XMLInjectionError,
)


@dataclass
class SyncPoint:
    """Represents a sync point for audio-tab synchronization.

    Attributes:
        bar: Bar/measure number (0-indexed)
        position: Position within bar (0 = start of bar)
        frame_offset: Audio frame position (sample number at 44.1kHz)
        modified_tempo: Detected tempo in audio at this point (BPM)
        original_tempo: Tempo specified in tab (BPM)
        bar_occurrence: For repeat sections (usually 0)
    """

    bar: int
    frame_offset: int
    modified_tempo: float
    original_tempo: float
    position: int = 0
    bar_occurrence: int = 0


@dataclass
class AssetInfo:
    """Information about an audio asset to embed.

    Attributes:
        asset_id: Unique identifier (referenced by BackingTrack)
        uuid: SHA1 hash used as filename
        original_file_path: Path where audio was imported from
        embedded_file_path: Path within .gp archive (Content/Assets/{uuid}.mp3)
    """

    asset_id: int
    uuid: str
    original_file_path: str
    embedded_file_path: str = field(init=False)

    def __post_init__(self):
        self.embedded_file_path = f"Content/Assets/{self.uuid}.mp3"


@dataclass
class BackingTrackConfig:
    """Configuration for the backing track element.

    Attributes:
        name: Display name shown in track list
        short_name: Abbreviated name
        asset_id: References Asset id
        playback_state: Solo, Default, or Mute
        enabled: Whether track is enabled
        frame_padding: Audio offset in frames (negative = shift earlier)
        semitones: Pitch shift in semitones
        cents: Fine pitch adjustment in cents
    """

    name: str = "Audio Track"
    short_name: str = "a.track"
    asset_id: int = 0
    playback_state: str = "Default"
    enabled: bool = True
    frame_padding: int = 0
    semitones: int = 0
    cents: int = 0


class XMLModifier:
    """Handles modification of Guitar Pro 8 score.gpif XML files.

    This class provides methods to inject audio track metadata into GP8 files,
    enabling audio playback synchronized with tab notation.

    Example:
        >>> modifier = XMLModifier(Path("extracted/score.gpif"))
        >>> modifier.load()
        >>> modifier.inject_asset(AssetInfo(0, "abc123-uuid", "/path/to/song.mp3"))
        >>> modifier.inject_backing_track(BackingTrackConfig(name="My Song"))
        >>> modifier.inject_sync_points([SyncPoint(bar=0, frame_offset=0, ...)])
        >>> modifier.save()
    """

    # Default ChannelStrip parameters (16 float values for audio processing)
    DEFAULT_CHANNEL_PARAMS = (
        "0.500000 0.500000 0.500000 0.500000 0.500000 0.500000 0.500000 0.500000 "
        "0.500000 0.000000 0.500000 0.500000 0.800000 0.500000 0.500000 0.500000"
    )

    def __init__(self, gpif_path: Path):
        """Initialize XMLModifier.

        Args:
            gpif_path: Path to the score.gpif XML file

        Raises:
            FileNotFoundError: If gpif_path doesn't exist
        """
        self.gpif_path = Path(gpif_path)

        if not self.gpif_path.exists():
            raise FileNotFoundError(f"score.gpif not found: {self.gpif_path}")

        self._tree: Optional[etree._ElementTree] = None
        self._root: Optional[etree._Element] = None
        self._is_loaded = False

        logger.debug(f"XMLModifier initialized for: {self.gpif_path}")

    def load(self) -> None:
        """Load and parse the score.gpif XML file.

        Raises:
            XMLParseError: If XML parsing fails
        """
        if self._is_loaded:
            logger.warning("XML already loaded, skipping")
            return

        try:
            logger.info(f"Loading XML from: {self.gpif_path}")

            # Parse with lxml, preserving CDATA sections
            parser = etree.XMLParser(
                remove_blank_text=False,
                strip_cdata=False,
            )
            self._tree = etree.parse(str(self.gpif_path), parser)
            self._root = self._tree.getroot()
            self._is_loaded = True

            logger.success("XML loaded successfully")

        except etree.XMLSyntaxError as e:
            raise XMLParseError(f"Failed to parse XML: {e}") from e
        except Exception as e:
            raise XMLParseError(f"Unexpected error loading XML: {e}") from e

    def save(self, output_path: Optional[Path] = None) -> Path:
        """Save the modified XML to file.

        Args:
            output_path: Optional output path. If None, overwrites original file.

        Returns:
            Path to the saved file

        Raises:
            XMLParseError: If XML is not loaded
        """
        self._ensure_loaded()

        save_path = output_path or self.gpif_path

        try:
            logger.info(f"Saving XML to: {save_path}")

            # Write with XML declaration and proper encoding
            self._tree.write(
                str(save_path),
                encoding="UTF-8",
                xml_declaration=True,
                pretty_print=True,
            )

            logger.success(f"XML saved to: {save_path}")
            return save_path

        except Exception as e:
            raise XMLParseError(f"Failed to save XML: {e}") from e

    def inject_backing_track(self, config: Optional[BackingTrackConfig] = None) -> None:
        """Inject BackingTrack element into the XML.

        The BackingTrack element is inserted after MasterTrack and before Tracks.

        Args:
            config: BackingTrack configuration. Uses defaults if None.

        Raises:
            XMLStructureError: If required elements are missing
            XMLInjectionError: If injection fails
        """
        self._ensure_loaded()
        config = config or BackingTrackConfig()

        logger.info(f"Injecting BackingTrack: {config.name}")

        try:
            # Check if BackingTrack already exists
            existing = self._root.find("BackingTrack")
            if existing is not None:
                logger.warning("BackingTrack already exists, replacing")
                self._root.remove(existing)

            # Find MasterTrack (required anchor point)
            master_track = self._root.find("MasterTrack")
            if master_track is None:
                raise XMLStructureError("MasterTrack element not found in XML")

            # Find Tracks element to insert before
            tracks = self._root.find("Tracks")
            if tracks is None:
                raise XMLStructureError("Tracks element not found in XML")

            # Create BackingTrack element
            backing_track = self._create_backing_track_element(config)

            # Insert after MasterTrack (before Tracks)
            master_track_index = list(self._root).index(master_track)
            self._root.insert(master_track_index + 1, backing_track)

            logger.success("BackingTrack injected successfully")

        except (XMLStructureError, XMLInjectionError):
            raise
        except Exception as e:
            raise XMLInjectionError(f"Failed to inject BackingTrack: {e}") from e

    def inject_asset(self, asset_info: AssetInfo) -> None:
        """Inject Asset element into the Assets section.

        Creates the Assets section if it doesn't exist.

        Args:
            asset_info: Asset information to inject

        Raises:
            XMLInjectionError: If injection fails
        """
        self._ensure_loaded()

        logger.info(f"Injecting Asset: {asset_info.uuid}")

        try:
            # Find or create Assets element
            assets = self._root.find("Assets")
            if assets is None:
                logger.debug("Assets element not found, creating")
                assets = self._create_assets_section()

            # Check if asset with this ID already exists
            existing = assets.find(f"Asset[@id='{asset_info.asset_id}']")
            if existing is not None:
                logger.warning(f"Asset with id={asset_info.asset_id} already exists, replacing")
                assets.remove(existing)

            # Create Asset element
            asset = etree.SubElement(assets, "Asset", id=str(asset_info.asset_id))

            # Add child elements with CDATA
            original_path = etree.SubElement(asset, "OriginalFilePath")
            original_path.text = etree.CDATA(asset_info.original_file_path)

            original_sha1 = etree.SubElement(asset, "OriginalFileSha1")
            original_sha1.text = etree.CDATA(asset_info.uuid)

            embedded_path = etree.SubElement(asset, "EmbeddedFilePath")
            embedded_path.text = etree.CDATA(asset_info.embedded_file_path)

            logger.success(f"Asset injected: {asset_info.embedded_file_path}")

        except Exception as e:
            raise XMLInjectionError(f"Failed to inject Asset: {e}") from e

    def inject_sync_points(self, sync_points: List[SyncPoint]) -> None:
        """Inject SyncPoint automations into MasterTrack/Automations.

        Args:
            sync_points: List of sync points to inject

        Raises:
            XMLStructureError: If MasterTrack is missing
            XMLInjectionError: If injection fails
        """
        self._ensure_loaded()

        if not sync_points:
            logger.warning("No sync points provided, skipping injection")
            return

        logger.info(f"Injecting {len(sync_points)} sync points")

        try:
            # Find MasterTrack
            master_track = self._root.find("MasterTrack")
            if master_track is None:
                raise XMLStructureError("MasterTrack element not found")

            # Find or create Automations element
            automations = master_track.find("Automations")
            if automations is None:
                logger.debug("Automations element not found, creating")
                automations = etree.SubElement(master_track, "Automations")

            # Remove existing SyncPoint automations
            for existing in automations.findall("Automation[Type='SyncPoint']"):
                automations.remove(existing)

            # Add new sync points
            for sync_point in sync_points:
                automation = self._create_sync_point_element(sync_point)
                automations.append(automation)

            logger.success(f"Injected {len(sync_points)} sync points")

        except XMLStructureError:
            raise
        except Exception as e:
            raise XMLInjectionError(f"Failed to inject sync points: {e}") from e

    def get_original_tempo(self) -> Optional[float]:
        """Extract the original tempo from the XML.

        Returns:
            Tempo in BPM, or None if not found
        """
        self._ensure_loaded()

        try:
            # Look for Tempo automation in MasterTrack/Automations
            tempo_automation = self._root.find("MasterTrack/Automations/Automation[Type='Tempo']")
            if tempo_automation is not None:
                value = tempo_automation.find("Value")
                if value is not None and value.text:
                    # Tempo value may be space-separated (e.g., "78 2" for BPM and beat type)
                    # Extract just the first value (BPM)
                    tempo_str = value.text.strip().split()[0]
                    return float(tempo_str)

            logger.debug("Tempo automation not found in XML")
            return None

        except Exception as e:
            logger.warning(f"Error extracting tempo: {e}")
            return None

    def get_bar_count(self) -> int:
        """Get the total number of bars/measures in the score.

        Returns:
            Number of bars, or 0 if cannot be determined
        """
        self._ensure_loaded()

        try:
            master_bars = self._root.find("MasterBars")
            if master_bars is not None:
                return len(master_bars.findall("MasterBar"))
            return 0
        except Exception as e:
            logger.warning(f"Error counting bars: {e}")
            return 0

    def _ensure_loaded(self) -> None:
        """Ensure XML is loaded before operations.

        Raises:
            XMLParseError: If XML is not loaded
        """
        if not self._is_loaded or self._root is None:
            raise XMLParseError("XML not loaded. Call load() first.")

    def _create_backing_track_element(self, config: BackingTrackConfig) -> etree._Element:
        """Create a BackingTrack XML element.

        Args:
            config: BackingTrack configuration

        Returns:
            BackingTrack element
        """
        backing_track = etree.Element("BackingTrack")

        # Add child elements in correct order
        self._add_element(backing_track, "IconId", "21")
        self._add_element(backing_track, "Color", "0 0 0")
        self._add_cdata_element(backing_track, "Name", config.name)
        self._add_cdata_element(backing_track, "ShortName", config.short_name)
        self._add_element(backing_track, "PlaybackState", config.playback_state)

        # ChannelStrip with Parameters
        channel_strip = etree.SubElement(backing_track, "ChannelStrip")
        self._add_element(channel_strip, "Parameters", self.DEFAULT_CHANNEL_PARAMS)

        self._add_element(backing_track, "Enabled", str(config.enabled).lower())
        self._add_element(backing_track, "Source", "Local")
        self._add_element(backing_track, "AssetId", str(config.asset_id))
        self._add_element(backing_track, "YouTubeVideoUrl", "")
        self._add_element(backing_track, "Filter", "6")
        self._add_element(backing_track, "FramesPerPixel", "100")
        self._add_element(backing_track, "FramePadding", str(config.frame_padding))
        self._add_element(backing_track, "Semitones", str(config.semitones))
        self._add_element(backing_track, "Cents", str(config.cents))

        return backing_track

    def _create_sync_point_element(self, sync_point: SyncPoint) -> etree._Element:
        """Create a SyncPoint Automation XML element.

        Args:
            sync_point: Sync point data

        Returns:
            Automation element for sync point
        """
        automation = etree.Element("Automation")

        self._add_element(automation, "Type", "SyncPoint")
        self._add_element(automation, "Linear", "false")
        self._add_element(automation, "Bar", str(sync_point.bar))
        self._add_element(automation, "Position", str(sync_point.position))
        self._add_element(automation, "Visible", "true")

        # Value sub-element
        value = etree.SubElement(automation, "Value")
        self._add_element(value, "BarIndex", str(sync_point.bar))
        self._add_element(value, "BarOccurrence", str(sync_point.bar_occurrence))
        self._add_element(value, "ModifiedTempo", f"{sync_point.modified_tempo:.3f}")
        self._add_element(value, "OriginalTempo", str(int(sync_point.original_tempo)))
        self._add_element(value, "FrameOffset", str(sync_point.frame_offset))

        return automation

    def _create_assets_section(self) -> etree._Element:
        """Create and insert Assets section in the correct location.

        Assets should be placed after Rhythms element.

        Returns:
            The created Assets element
        """
        assets = etree.Element("Assets")

        # Find Rhythms element (Assets goes after it)
        rhythms = self._root.find("Rhythms")
        if rhythms is not None:
            rhythms_index = list(self._root).index(rhythms)
            self._root.insert(rhythms_index + 1, assets)
        else:
            # Fallback: append to end
            self._root.append(assets)

        return assets

    @staticmethod
    def _add_element(parent: etree._Element, tag: str, text: str) -> etree._Element:
        """Add a simple text element to parent.

        Args:
            parent: Parent element
            tag: Element tag name
            text: Text content

        Returns:
            Created element
        """
        element = etree.SubElement(parent, tag)
        element.text = text
        return element

    @staticmethod
    def _add_cdata_element(parent: etree._Element, tag: str, text: str) -> etree._Element:
        """Add an element with CDATA content.

        Args:
            parent: Parent element
            tag: Element tag name
            text: Text content (will be wrapped in CDATA)

        Returns:
            Created element
        """
        element = etree.SubElement(parent, tag)
        element.text = etree.CDATA(text)
        return element

    def has_backing_track(self) -> bool:
        """Check if the XML already has a BackingTrack element.

        Returns:
            True if BackingTrack exists
        """
        self._ensure_loaded()
        return self._root.find("BackingTrack") is not None

    def has_assets(self) -> bool:
        """Check if the XML has an Assets section with content.

        Returns:
            True if Assets section exists and has content
        """
        self._ensure_loaded()
        assets = self._root.find("Assets")
        return assets is not None and len(assets) > 0
