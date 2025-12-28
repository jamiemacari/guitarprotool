"""Tests for sync point comparison utility."""

import zipfile
from pathlib import Path

import pytest

from guitarprotool.core.sync_comparator import (
    SyncComparator,
    ComparisonResult,
    SyncPointDiff,
    BackingTrackInfo,
)
from guitarprotool.core.xml_modifier import SyncPoint


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def sample_gp_with_syncpoints(temp_dir):
    """Create a GP file with sync points for testing extraction."""
    gp_path = temp_dir / "with_syncpoints.gp"

    gpif_content = '''<?xml version="1.0" encoding="UTF-8"?>
<GPIF>
    <GPVersion>8.0</GPVersion>
    <Score>
        <Title>Test Song</Title>
    </Score>
    <MasterTrack>
        <Automations>
            <Automation>
                <Type>Tempo</Type>
                <Value>120 2</Value>
            </Automation>
            <Automation>
                <Type>SyncPoint</Type>
                <Linear>false</Linear>
                <Bar>0</Bar>
                <Position>0</Position>
                <Visible>true</Visible>
                <Value>
                    <BarIndex>0</BarIndex>
                    <BarOccurrence>0</BarOccurrence>
                    <ModifiedTempo>120.000</ModifiedTempo>
                    <OriginalTempo>120</OriginalTempo>
                    <FrameOffset>0</FrameOffset>
                </Value>
            </Automation>
            <Automation>
                <Type>SyncPoint</Type>
                <Linear>false</Linear>
                <Bar>4</Bar>
                <Position>0</Position>
                <Visible>true</Visible>
                <Value>
                    <BarIndex>4</BarIndex>
                    <BarOccurrence>0</BarOccurrence>
                    <ModifiedTempo>119.500</ModifiedTempo>
                    <OriginalTempo>120</OriginalTempo>
                    <FrameOffset>88200</FrameOffset>
                </Value>
            </Automation>
            <Automation>
                <Type>SyncPoint</Type>
                <Linear>false</Linear>
                <Bar>8</Bar>
                <Position>0</Position>
                <Visible>true</Visible>
                <Value>
                    <BarIndex>8</BarIndex>
                    <BarOccurrence>0</BarOccurrence>
                    <ModifiedTempo>120.500</ModifiedTempo>
                    <OriginalTempo>120</OriginalTempo>
                    <FrameOffset>176400</FrameOffset>
                </Value>
            </Automation>
        </Automations>
    </MasterTrack>
    <BackingTrack>
        <Name><![CDATA[Test Track]]></Name>
        <FramePadding>-22050</FramePadding>
        <FramesPerPixel>1274</FramesPerPixel>
        <AssetId>0</AssetId>
    </BackingTrack>
</GPIF>'''

    with zipfile.ZipFile(gp_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("score.gpif", gpif_content)
        zf.writestr("Content/", "")

    return gp_path


@pytest.fixture
def sample_gp_with_different_syncpoints(temp_dir):
    """Create a GP file with slightly different sync points for comparison."""
    gp_path = temp_dir / "different_syncpoints.gp"

    gpif_content = '''<?xml version="1.0" encoding="UTF-8"?>
<GPIF>
    <GPVersion>8.0</GPVersion>
    <Score>
        <Title>Test Song Reference</Title>
    </Score>
    <MasterTrack>
        <Automations>
            <Automation>
                <Type>SyncPoint</Type>
                <Linear>false</Linear>
                <Bar>0</Bar>
                <Position>0</Position>
                <Visible>true</Visible>
                <Value>
                    <BarIndex>0</BarIndex>
                    <BarOccurrence>0</BarOccurrence>
                    <ModifiedTempo>120.100</ModifiedTempo>
                    <OriginalTempo>120</OriginalTempo>
                    <FrameOffset>100</FrameOffset>
                </Value>
            </Automation>
            <Automation>
                <Type>SyncPoint</Type>
                <Linear>false</Linear>
                <Bar>4</Bar>
                <Position>0</Position>
                <Visible>true</Visible>
                <Value>
                    <BarIndex>4</BarIndex>
                    <BarOccurrence>0</BarOccurrence>
                    <ModifiedTempo>119.600</ModifiedTempo>
                    <OriginalTempo>120</OriginalTempo>
                    <FrameOffset>88300</FrameOffset>
                </Value>
            </Automation>
        </Automations>
    </MasterTrack>
</GPIF>'''

    with zipfile.ZipFile(gp_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("score.gpif", gpif_content)
        zf.writestr("Content/", "")

    return gp_path


@pytest.fixture
def sample_gp_no_syncpoints(temp_dir):
    """Create a GP file without any sync points."""
    gp_path = temp_dir / "no_syncpoints.gp"

    gpif_content = '''<?xml version="1.0" encoding="UTF-8"?>
<GPIF>
    <GPVersion>8.0</GPVersion>
    <Score>
        <Title>No Sync Points</Title>
    </Score>
    <MasterTrack>
        <Automations>
            <Automation>
                <Type>Tempo</Type>
                <Value>120 2</Value>
            </Automation>
        </Automations>
    </MasterTrack>
</GPIF>'''

    with zipfile.ZipFile(gp_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("score.gpif", gpif_content)
        zf.writestr("Content/", "")

    return gp_path


# =============================================================================
# Unit Tests: SyncComparator.extract_sync_points
# =============================================================================


class TestExtractSyncPoints:
    """Tests for sync point extraction from GP files."""

    def test_extract_sync_points_basic(self, sample_gp_with_syncpoints):
        """Test extracting sync points from a GP file."""
        sync_points = SyncComparator.extract_sync_points(sample_gp_with_syncpoints)

        assert len(sync_points) == 3
        assert sync_points[0].bar == 0
        assert sync_points[0].frame_offset == 0
        assert sync_points[0].modified_tempo == 120.0
        assert sync_points[1].bar == 4
        assert sync_points[1].frame_offset == 88200
        assert sync_points[2].bar == 8

    def test_extract_sync_points_empty(self, sample_gp_no_syncpoints):
        """Test extracting from file with no sync points returns empty list."""
        sync_points = SyncComparator.extract_sync_points(sample_gp_no_syncpoints)
        assert sync_points == []

    def test_extract_sync_points_file_not_found(self, temp_dir):
        """Test extracting from non-existent file raises error."""
        from guitarprotool.utils.exceptions import InvalidGPFileError

        fake_path = temp_dir / "nonexistent.gp"
        with pytest.raises(InvalidGPFileError):
            SyncComparator.extract_sync_points(fake_path)


# =============================================================================
# Unit Tests: SyncComparator.extract_backing_track_info
# =============================================================================


class TestExtractBackingTrackInfo:
    """Tests for backing track info extraction."""

    def test_extract_backing_track_info(self, sample_gp_with_syncpoints):
        """Test extracting backing track metadata."""
        info = SyncComparator.extract_backing_track_info(sample_gp_with_syncpoints)

        assert info is not None
        assert info.frame_padding == -22050
        assert info.frames_per_pixel == 1274
        assert info.asset_id == 0
        assert "Test Track" in info.name

    def test_extract_backing_track_info_not_found(self, sample_gp_no_syncpoints):
        """Test extracting from file without backing track returns None."""
        info = SyncComparator.extract_backing_track_info(sample_gp_no_syncpoints)
        assert info is None


# =============================================================================
# Unit Tests: SyncComparator.compare
# =============================================================================


class TestCompare:
    """Tests for sync point comparison."""

    def test_compare_identical_files(self, sample_gp_with_syncpoints):
        """Test comparing a file to itself yields perfect match."""
        comparator = SyncComparator()
        result = comparator.compare(
            sample_gp_with_syncpoints, sample_gp_with_syncpoints
        )

        assert result.is_within_tolerance()
        assert len(result.matched_bars) == 3
        assert len(result.extra_bars) == 0
        assert len(result.missing_bars) == 0
        assert result.avg_frame_diff == 0.0
        assert result.avg_tempo_diff == 0.0

    def test_compare_different_files(
        self, sample_gp_with_syncpoints, sample_gp_with_different_syncpoints
    ):
        """Test comparing files with different sync points."""
        comparator = SyncComparator(frame_tolerance=500, tempo_tolerance=0.5)
        result = comparator.compare(
            sample_gp_with_syncpoints, sample_gp_with_different_syncpoints
        )

        # Should match on bars 0 and 4 (present in both)
        assert len(result.matched_bars) == 2
        assert 0 in result.matched_bars
        assert 4 in result.matched_bars

        # Bar 8 is only in generated
        assert len(result.extra_bars) == 1
        assert result.extra_bars[0].bar == 8

        # No missing bars
        assert len(result.missing_bars) == 0

    def test_compare_within_tolerance(
        self, sample_gp_with_syncpoints, sample_gp_with_different_syncpoints
    ):
        """Test that small differences pass tolerance check."""
        # Use generous tolerance
        comparator = SyncComparator(frame_tolerance=1000, tempo_tolerance=1.0)
        result = comparator.compare(
            sample_gp_with_syncpoints, sample_gp_with_different_syncpoints
        )

        # Differences are small, should be within tolerance
        assert result.is_within_tolerance()

    def test_compare_outside_tolerance(
        self, sample_gp_with_syncpoints, sample_gp_with_different_syncpoints
    ):
        """Test that differences can exceed tolerance."""
        # Use very strict tolerance
        comparator = SyncComparator(frame_tolerance=50, tempo_tolerance=0.05)
        result = comparator.compare(
            sample_gp_with_syncpoints, sample_gp_with_different_syncpoints
        )

        # Differences should exceed strict tolerance
        assert not result.is_within_tolerance()

    def test_compare_empty_files(self, sample_gp_no_syncpoints):
        """Test comparing files with no sync points."""
        comparator = SyncComparator()
        result = comparator.compare(
            sample_gp_no_syncpoints, sample_gp_no_syncpoints
        )

        assert result.is_within_tolerance()
        assert len(result.matched_bars) == 0
        assert len(result.extra_bars) == 0
        assert len(result.missing_bars) == 0


# =============================================================================
# Unit Tests: ComparisonResult
# =============================================================================


class TestComparisonResult:
    """Tests for ComparisonResult dataclass."""

    def test_generate_report_basic(self):
        """Test generating a comparison report."""
        sp1 = SyncPoint(bar=0, frame_offset=0, modified_tempo=120.0, original_tempo=120.0)
        sp2 = SyncPoint(bar=0, frame_offset=100, modified_tempo=120.1, original_tempo=120.0)

        result = ComparisonResult(
            matched_bars=[0],
            diffs=[SyncPointDiff(bar=0, generated=sp1, reference=sp2, frame_offset_diff=-100, tempo_diff=-0.1)],
            extra_bars=[],
            missing_bars=[],
            frame_tolerance=4410,
            tempo_tolerance=1.0,
            generated_path="/path/to/generated.gp",
            reference_path="/path/to/reference.gp",
        )

        report = result.generate_report()

        assert "SYNC POINT COMPARISON REPORT" in report
        assert "generated.gp" in report
        assert "reference.gp" in report
        assert "Matched bars:" in report
        assert "Within tolerance:" in report

    def test_is_within_tolerance_empty(self):
        """Test tolerance check with no diffs."""
        result = ComparisonResult()
        assert result.is_within_tolerance()

    def test_get_bars_outside_tolerance(self):
        """Test getting bars that exceed tolerance."""
        sp1 = SyncPoint(bar=0, frame_offset=0, modified_tempo=120.0, original_tempo=120.0)
        sp2 = SyncPoint(bar=0, frame_offset=10000, modified_tempo=125.0, original_tempo=120.0)

        result = ComparisonResult(
            matched_bars=[0],
            diffs=[SyncPointDiff(bar=0, generated=sp1, reference=sp2, frame_offset_diff=-10000, tempo_diff=-5.0)],
            frame_tolerance=1000,
            tempo_tolerance=1.0,
        )

        outside = result.get_bars_outside_tolerance()
        assert len(outside) == 1
        assert outside[0].bar == 0

    def test_statistics_properties(self):
        """Test avg/max statistics calculations."""
        sp = SyncPoint(bar=0, frame_offset=0, modified_tempo=120.0, original_tempo=120.0)

        result = ComparisonResult(
            matched_bars=[0, 4, 8],
            diffs=[
                SyncPointDiff(bar=0, generated=sp, reference=sp, frame_offset_diff=100, tempo_diff=0.1),
                SyncPointDiff(bar=4, generated=sp, reference=sp, frame_offset_diff=-200, tempo_diff=-0.2),
                SyncPointDiff(bar=8, generated=sp, reference=sp, frame_offset_diff=300, tempo_diff=0.3),
            ],
        )

        # avg_frame_diff = (100 + 200 + 300) / 3 = 200
        assert result.avg_frame_diff == 200.0
        assert result.max_frame_diff == 300
        # avg_tempo_diff = (0.1 + 0.2 + 0.3) / 3 = 0.2
        assert result.avg_tempo_diff == 0.2
        assert result.max_tempo_diff == 0.3


# =============================================================================
# Integration Tests (require fixture files)
# =============================================================================


@pytest.mark.integration
class TestPipelineAccuracy:
    """Integration tests comparing pipeline output to reference files.

    These tests are marked as integration tests and will be skipped
    if the fixture files are not available.
    """

    def test_simple_song_sync_extraction(self, simple_song_fixture):
        """Test that we can extract sync points from the reference file."""
        if simple_song_fixture["reference"] is None:
            pytest.skip("Reference file not available")

        sync_points = SyncComparator.extract_sync_points(
            simple_song_fixture["reference"]
        )

        # Should have at least some sync points
        assert len(sync_points) > 0, "Reference file should have sync points"
        # First sync point should be at bar 0
        assert sync_points[0].bar == 0, "First sync point should be at bar 0"

    def test_complex_intro_sync_extraction(self, complex_intro_fixture):
        """Test that we can extract sync points from the complex intro reference."""
        if complex_intro_fixture["reference"] is None:
            pytest.skip("Reference file not available")

        sync_points = SyncComparator.extract_sync_points(
            complex_intro_fixture["reference"]
        )

        assert len(sync_points) > 0, "Reference file should have sync points"
