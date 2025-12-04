"""Pytest configuration and fixtures for guitarprotool tests."""

import tempfile
import zipfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_gp_file(temp_dir):
    """Create a minimal valid .gp file for testing.

    Creates a ZIP file with the basic structure of a GP8 file:
    - score.gpif (minimal XML)
    - Content/ directory
    """
    gp_path = temp_dir / "test.gp"

    # Create minimal score.gpif content
    gpif_content = '''<?xml version="1.0" encoding="UTF-8"?>
<GPIF>
    <GPVersion>8.0</GPVersion>
    <Score>
        <Title>Test Song</Title>
        <Artist>Test Artist</Artist>
    </Score>
</GPIF>'''

    # Create the .gp file as a ZIP
    with zipfile.ZipFile(gp_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("score.gpif", gpif_content)
        # Add empty Content directory
        zf.writestr("Content/", "")

    return gp_path


@pytest.fixture
def sample_gp_with_audio(temp_dir):
    """Create a .gp file with existing audio directory structure."""
    gp_path = temp_dir / "test_with_audio.gp"

    gpif_content = '''<?xml version="1.0" encoding="UTF-8"?>
<GPIF>
    <GPVersion>8.0</GPVersion>
    <Score>
        <Title>Test Song with Audio</Title>
    </Score>
    <Tracks>
        <Track>
            <Name>Guitar</Name>
        </Track>
    </Tracks>
</GPIF>'''

    with zipfile.ZipFile(gp_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("score.gpif", gpif_content)
        zf.writestr("Content/Audio/", "")
        # Add a fake audio file
        zf.writestr("Content/Audio/track_001.mp3", b"fake audio data")

    return gp_path


@pytest.fixture
def invalid_zip_file(temp_dir):
    """Create a file that is not a valid ZIP archive."""
    file_path = temp_dir / "invalid.gp"
    file_path.write_text("This is not a ZIP file")
    return file_path


@pytest.fixture
def corrupted_gp_file(temp_dir):
    """Create a .gp file missing required score.gpif."""
    gp_path = temp_dir / "corrupted.gp"

    with zipfile.ZipFile(gp_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Content/", "")
        # Missing score.gpif!

    return gp_path


@pytest.fixture
def sample_gp_file_content_gpif(temp_dir):
    """Create a .gp file with score.gpif inside Content/ folder.

    This mirrors the structure found in some real GP8 files where
    score.gpif is located at Content/score.gpif instead of root.
    """
    gp_path = temp_dir / "test_content_gpif.gp"

    gpif_content = '''<?xml version="1.0" encoding="UTF-8"?>
<GPIF>
    <GPVersion>8.0</GPVersion>
    <Score>
        <Title>Test Song Content Path</Title>
        <Artist>Test Artist</Artist>
    </Score>
</GPIF>'''

    with zipfile.ZipFile(gp_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # score.gpif inside Content/ folder
        zf.writestr("Content/score.gpif", gpif_content)
        zf.writestr("Content/BinaryStylesheet", "")
        zf.writestr("VERSION", "8.0")

    return gp_path
