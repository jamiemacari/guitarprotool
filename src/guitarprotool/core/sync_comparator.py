"""Sync point comparison utility for Guitar Pro files.

This module provides functionality to extract and compare sync points between
GP files, useful for validating pipeline output against manually-synced reference files.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from lxml import etree
from loguru import logger

from guitarprotool.core.gp_file import GPFile
from guitarprotool.core.xml_modifier import SyncPoint
from guitarprotool.utils.exceptions import (
    GPFileError,
    XMLParseError,
)


@dataclass
class BackingTrackInfo:
    """Extracted backing track metadata from a GP file.

    Attributes:
        frame_padding: Audio offset in frames (negative = shift earlier)
        frames_per_pixel: Zoom level for audio display
        name: Track name
        asset_id: Reference to asset
    """

    frame_padding: int = 0
    frames_per_pixel: int = 1274
    name: str = ""
    asset_id: int = 0


@dataclass
class SyncPointDiff:
    """Difference between two sync points at the same bar.

    Attributes:
        bar: Bar number where both files have a sync point
        generated: Sync point from generated file
        reference: Sync point from reference file
        frame_offset_diff: Difference in frame offset (generated - reference)
        tempo_diff: Difference in modified tempo (generated - reference)
    """

    bar: int
    generated: SyncPoint
    reference: SyncPoint
    frame_offset_diff: int
    tempo_diff: float


@dataclass
class ComparisonResult:
    """Result of comparing sync points between two GP files.

    Attributes:
        matched_bars: List of bar numbers present in both files
        diffs: List of differences for matched bars
        extra_bars: Sync points in generated but not in reference
        missing_bars: Sync points in reference but not in generated
        frame_tolerance: Tolerance used for frame offset comparison
        tempo_tolerance: Tolerance used for tempo comparison
    """

    matched_bars: List[int] = field(default_factory=list)
    diffs: List[SyncPointDiff] = field(default_factory=list)
    extra_bars: List[SyncPoint] = field(default_factory=list)
    missing_bars: List[SyncPoint] = field(default_factory=list)
    frame_tolerance: int = 4410
    tempo_tolerance: float = 1.0

    # File paths for report
    generated_path: str = ""
    reference_path: str = ""

    @property
    def avg_frame_diff(self) -> float:
        """Average absolute frame offset difference across matched bars."""
        if not self.diffs:
            return 0.0
        return sum(abs(d.frame_offset_diff) for d in self.diffs) / len(self.diffs)

    @property
    def max_frame_diff(self) -> int:
        """Maximum absolute frame offset difference across matched bars."""
        if not self.diffs:
            return 0
        return max(abs(d.frame_offset_diff) for d in self.diffs)

    @property
    def avg_tempo_diff(self) -> float:
        """Average absolute tempo difference across matched bars."""
        if not self.diffs:
            return 0.0
        return sum(abs(d.tempo_diff) for d in self.diffs) / len(self.diffs)

    @property
    def max_tempo_diff(self) -> float:
        """Maximum absolute tempo difference across matched bars."""
        if not self.diffs:
            return 0.0
        return max(abs(d.tempo_diff) for d in self.diffs)

    def is_within_tolerance(self) -> bool:
        """Check if all matched bars are within tolerance.

        Returns:
            True if all differences are within tolerance, False otherwise
        """
        for diff in self.diffs:
            if abs(diff.frame_offset_diff) > self.frame_tolerance:
                return False
            if abs(diff.tempo_diff) > self.tempo_tolerance:
                return False
        return True

    def get_bars_outside_tolerance(self) -> List[SyncPointDiff]:
        """Get list of diffs that exceed tolerance thresholds.

        Returns:
            List of SyncPointDiff where frame or tempo diff exceeds tolerance
        """
        return [
            d
            for d in self.diffs
            if abs(d.frame_offset_diff) > self.frame_tolerance
            or abs(d.tempo_diff) > self.tempo_tolerance
        ]

    def generate_report(self) -> str:
        """Generate human-readable comparison report.

        Returns:
            Formatted string report
        """
        lines = [
            "=" * 60,
            "SYNC POINT COMPARISON REPORT",
            "=" * 60,
            "",
            f"Generated: {self.generated_path}",
            f"Reference: {self.reference_path}",
            "",
            "SUMMARY:",
            f"  Matched bars:                 {len(self.matched_bars)}",
            f"  Extra bars (generated only):  {len(self.extra_bars)}",
            f"  Missing bars (reference only): {len(self.missing_bars)}",
            f"  Within tolerance:             {'YES' if self.is_within_tolerance() else 'NO'}",
            "",
        ]

        # Statistics
        if self.diffs:
            lines.extend(
                [
                    "STATISTICS:",
                    f"  Avg frame diff: {self.avg_frame_diff:.1f} samples "
                    f"({self.avg_frame_diff / 44.1:.1f} ms)",
                    f"  Max frame diff: {self.max_frame_diff} samples "
                    f"({self.max_frame_diff / 44.1:.1f} ms)",
                    f"  Avg tempo diff: {self.avg_tempo_diff:.3f} BPM",
                    f"  Max tempo diff: {self.max_tempo_diff:.3f} BPM",
                    "",
                ]
            )

        # Matched bars with differences
        if self.diffs:
            lines.extend(
                [
                    "MATCHED BARS:",
                    f"  {'Bar':>4}  {'FrameDiff':>12}  {'TempoDiff':>10}  {'Status':>8}",
                    f"  {'-'*4}  {'-'*12}  {'-'*10}  {'-'*8}",
                ]
            )
            for diff in self.diffs:
                frame_status = (
                    "OK"
                    if abs(diff.frame_offset_diff) <= self.frame_tolerance
                    else "OVER"
                )
                tempo_status = (
                    "OK" if abs(diff.tempo_diff) <= self.tempo_tolerance else "OVER"
                )
                status = "OK" if frame_status == "OK" and tempo_status == "OK" else "FAIL"
                lines.append(
                    f"  {diff.bar:>4}  {diff.frame_offset_diff:>+12}  "
                    f"{diff.tempo_diff:>+10.3f}  {status:>8}"
                )
            lines.append("")

        # Extra bars
        if self.extra_bars:
            lines.extend(
                [
                    "EXTRA BARS (in generated, not in reference):",
                    f"  {'Bar':>4}  {'FrameOffset':>12}  {'Tempo':>10}",
                    f"  {'-'*4}  {'-'*12}  {'-'*10}",
                ]
            )
            for sp in sorted(self.extra_bars, key=lambda x: x.bar):
                lines.append(
                    f"  {sp.bar:>4}  {sp.frame_offset:>12}  {sp.modified_tempo:>10.3f}"
                )
            lines.append("")

        # Missing bars
        if self.missing_bars:
            lines.extend(
                [
                    "MISSING BARS (in reference, not in generated):",
                    f"  {'Bar':>4}  {'FrameOffset':>12}  {'Tempo':>10}",
                    f"  {'-'*4}  {'-'*12}  {'-'*10}",
                ]
            )
            for sp in sorted(self.missing_bars, key=lambda x: x.bar):
                lines.append(
                    f"  {sp.bar:>4}  {sp.frame_offset:>12}  {sp.modified_tempo:>10.3f}"
                )
            lines.append("")

        # Tolerance info
        lines.extend(
            [
                "-" * 60,
                f"Tolerances: FrameOffset={self.frame_tolerance} samples "
                f"({self.frame_tolerance / 44.1:.1f}ms), "
                f"Tempo={self.tempo_tolerance} BPM",
            ]
        )

        return "\n".join(lines)


class SyncComparator:
    """Compare sync points between generated and reference GP files.

    Example:
        >>> comparator = SyncComparator(frame_tolerance=4410, tempo_tolerance=1.5)
        >>> sync_points = SyncComparator.extract_sync_points(Path("song.gp"))
        >>> result = comparator.compare(Path("generated.gp"), Path("reference.gp"))
        >>> print(result.generate_report())
    """

    DEFAULT_FRAME_TOLERANCE = 4410  # ~100ms at 44.1kHz
    DEFAULT_TEMPO_TOLERANCE = 1.5  # 1.5 BPM

    def __init__(
        self,
        frame_tolerance: int = DEFAULT_FRAME_TOLERANCE,
        tempo_tolerance: float = DEFAULT_TEMPO_TOLERANCE,
    ):
        """Initialize SyncComparator.

        Args:
            frame_tolerance: Maximum allowed frame offset difference (samples)
            tempo_tolerance: Maximum allowed tempo difference (BPM)
        """
        self.frame_tolerance = frame_tolerance
        self.tempo_tolerance = tempo_tolerance

    @staticmethod
    def extract_sync_points(gp_path: Path) -> List[SyncPoint]:
        """Extract all sync points from a GP file.

        Args:
            gp_path: Path to the GP file

        Returns:
            List of SyncPoint objects extracted from the file

        Raises:
            GPFileError: If file extraction fails
            XMLParseError: If XML parsing fails
        """
        gp_path = Path(gp_path)
        sync_points = []

        logger.info(f"Extracting sync points from: {gp_path}")

        try:
            with GPFile(gp_path) as gp:
                gpif_path = gp.get_gpif_path()

                # Parse XML
                parser = etree.XMLParser(remove_blank_text=False, strip_cdata=False)
                tree = etree.parse(str(gpif_path), parser)
                root = tree.getroot()

                # Find all SyncPoint automations in MasterTrack/Automations
                master_track = root.find("MasterTrack")
                if master_track is None:
                    logger.warning("MasterTrack not found in XML")
                    return sync_points

                automations = master_track.find("Automations")
                if automations is None:
                    logger.warning("Automations element not found")
                    return sync_points

                # Extract each SyncPoint
                for automation in automations.findall("Automation"):
                    type_elem = automation.find("Type")
                    if type_elem is None or type_elem.text != "SyncPoint":
                        continue

                    value_elem = automation.find("Value")
                    if value_elem is None:
                        continue

                    # Extract values
                    bar_index = SyncComparator._get_int(value_elem, "BarIndex", 0)
                    bar_occurrence = SyncComparator._get_int(value_elem, "BarOccurrence", 0)
                    modified_tempo = SyncComparator._get_float(
                        value_elem, "ModifiedTempo", 0.0
                    )
                    original_tempo = SyncComparator._get_float(
                        value_elem, "OriginalTempo", 0.0
                    )
                    frame_offset = SyncComparator._get_int(value_elem, "FrameOffset", 0)

                    # Get position from automation element (not Value)
                    position = SyncComparator._get_int(automation, "Position", 0)

                    sync_point = SyncPoint(
                        bar=bar_index,
                        frame_offset=frame_offset,
                        modified_tempo=modified_tempo,
                        original_tempo=original_tempo,
                        position=position,
                        bar_occurrence=bar_occurrence,
                    )
                    sync_points.append(sync_point)

                logger.info(f"Extracted {len(sync_points)} sync points")

        except GPFileError:
            raise
        except etree.XMLSyntaxError as e:
            raise XMLParseError(f"Failed to parse XML: {e}") from e
        except Exception as e:
            raise XMLParseError(f"Error extracting sync points: {e}") from e

        return sync_points

    @staticmethod
    def extract_backing_track_info(gp_path: Path) -> Optional[BackingTrackInfo]:
        """Extract backing track metadata from a GP file.

        Args:
            gp_path: Path to the GP file

        Returns:
            BackingTrackInfo if found, None otherwise

        Raises:
            GPFileError: If file extraction fails
            XMLParseError: If XML parsing fails
        """
        gp_path = Path(gp_path)

        try:
            with GPFile(gp_path) as gp:
                gpif_path = gp.get_gpif_path()

                parser = etree.XMLParser(remove_blank_text=False, strip_cdata=False)
                tree = etree.parse(str(gpif_path), parser)
                root = tree.getroot()

                backing_track = root.find("BackingTrack")
                if backing_track is None:
                    return None

                info = BackingTrackInfo(
                    frame_padding=SyncComparator._get_int(
                        backing_track, "FramePadding", 0
                    ),
                    frames_per_pixel=SyncComparator._get_int(
                        backing_track, "FramesPerPixel", 1274
                    ),
                    asset_id=SyncComparator._get_int(backing_track, "AssetId", 0),
                )

                # Get name (may be in CDATA)
                name_elem = backing_track.find("Name")
                if name_elem is not None and name_elem.text:
                    info.name = name_elem.text

                return info

        except GPFileError:
            raise
        except etree.XMLSyntaxError as e:
            raise XMLParseError(f"Failed to parse XML: {e}") from e
        except Exception as e:
            raise XMLParseError(f"Error extracting backing track info: {e}") from e

    def compare(self, generated_path: Path, reference_path: Path) -> ComparisonResult:
        """Compare sync points between generated and reference files.

        Args:
            generated_path: Path to the generated GP file
            reference_path: Path to the reference GP file

        Returns:
            ComparisonResult with matched, extra, and missing sync points
        """
        generated_path = Path(generated_path)
        reference_path = Path(reference_path)

        logger.info(f"Comparing sync points: {generated_path} vs {reference_path}")

        # Extract sync points from both files
        generated_points = self.extract_sync_points(generated_path)
        reference_points = self.extract_sync_points(reference_path)

        # Build lookup maps by bar number
        gen_map: Dict[int, SyncPoint] = {sp.bar: sp for sp in generated_points}
        ref_map: Dict[int, SyncPoint] = {sp.bar: sp for sp in reference_points}

        # Find all bars
        all_bars = set(gen_map.keys()) | set(ref_map.keys())

        result = ComparisonResult(
            frame_tolerance=self.frame_tolerance,
            tempo_tolerance=self.tempo_tolerance,
            generated_path=str(generated_path),
            reference_path=str(reference_path),
        )

        for bar in sorted(all_bars):
            gen_sp = gen_map.get(bar)
            ref_sp = ref_map.get(bar)

            if gen_sp and ref_sp:
                # Both have sync point at this bar
                result.matched_bars.append(bar)
                diff = SyncPointDiff(
                    bar=bar,
                    generated=gen_sp,
                    reference=ref_sp,
                    frame_offset_diff=gen_sp.frame_offset - ref_sp.frame_offset,
                    tempo_diff=gen_sp.modified_tempo - ref_sp.modified_tempo,
                )
                result.diffs.append(diff)

            elif gen_sp and not ref_sp:
                # Only in generated (extra)
                result.extra_bars.append(gen_sp)

            elif ref_sp and not gen_sp:
                # Only in reference (missing)
                result.missing_bars.append(ref_sp)

        logger.info(
            f"Comparison complete: {len(result.matched_bars)} matched, "
            f"{len(result.extra_bars)} extra, {len(result.missing_bars)} missing"
        )

        return result

    @staticmethod
    def _get_int(element: etree._Element, tag: str, default: int) -> int:
        """Get integer value from child element."""
        child = element.find(tag)
        if child is not None and child.text:
            try:
                return int(child.text.strip())
            except ValueError:
                pass
        return default

    @staticmethod
    def _get_float(element: etree._Element, tag: str, default: float) -> float:
        """Get float value from child element."""
        child = element.find(tag)
        if child is not None and child.text:
            try:
                return float(child.text.strip())
            except ValueError:
                pass
        return default
