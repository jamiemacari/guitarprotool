# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Guitar Pro 8 Audio Injection Tool - Automates downloading YouTube audio, injecting it into Guitar Pro 8 (.gp) files, and creating sync points for playback alignment. Built for automating bass tab practice workflows.

## System Dependencies Required

Before working with this codebase, ensure these system dependencies are installed:

**Ubuntu/Debian:**
```bash
sudo apt-get install ffmpeg libaubio-dev aubio-tools
```

**macOS:**
```bash
brew install ffmpeg aubio
```

## Development Commands

### Setup
```bash
# Create virtual environment and install dependencies
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt

# Install in editable mode
pip install -e .
```

### Testing
```bash
# Run all tests with coverage
pytest

# Run specific test file
pytest tests/test_gp_file.py

# Run specific test class or function
pytest tests/test_gp_file.py::TestGPFileExtract
pytest tests/test_gp_file.py::TestGPFileExtract::test_extract_valid_file

# Run with verbose output
pytest -v

# Run with coverage report
pytest --cov=guitarprotool --cov-report=html
```

### Code Quality
```bash
# Format code (line length: 100)
black src/ tests/

# Lint code
ruff check src/ tests/

# Type checking
mypy src/
```

### Running the Tool
```bash
# Interactive CLI (when implemented)
python -m guitarprotool

# Or if installed
guitarprotool
```

## Architecture Overview

### Core Workflow Pipeline

The tool operates as a linear pipeline with 5 distinct phases:

1. **Extract** (`GPFile.extract()`) - Treats .gp file as ZIP archive, extracts to temp directory
2. **Download/Convert** (`AudioProcessor`) - Downloads YouTube audio, converts to MP3 192kbps
3. **Detect** (`BeatDetector`) - Analyzes audio for BPM and beat positions using aubio
4. **Inject** (`XMLModifier`) - Modifies score.gpif XML to add AudioTrack element with sync points
5. **Repackage** (`GPFile.repackage()`) - Creates new .gp file with audio and metadata

### Guitar Pro File Format

**Critical**: Guitar Pro 8 .gp files are ZIP archives with this structure:
```
mysong.gp (ZIP file)
├── score.gpif          # Main XML file with tab data, tempo, measures
├── Content/
│   └── Audio/          # Audio tracks (created if missing)
│       └── *.mp3       # Audio files referenced in XML
└── [other metadata]
```

The `score.gpif` XML file contains all tab data. To add audio:
- Copy MP3 to `Content/Audio/`
- Inject `<AudioTrack>` element into score.gpif XML
- AudioTrack must reference the audio file path and contain sync points

**IMPORTANT**: The GP8 XML schema is proprietary and undocumented. The exact structure of `<AudioTrack>` elements must be reverse-engineered from sample .gp files that already have audio. See `docs/GP8_FORMAT.md` for discoveries.

### Module Responsibilities

**`core/gp_file.py`** - GPFile class
- Handles all .gp file I/O operations
- Preserves ZIP compression settings exactly (stores metadata during extraction)
- Context manager support for automatic cleanup
- **Key methods**: `extract()`, `get_gpif_path()`, `get_audio_dir()`, `repackage()`

**`core/audio_processor.py`** ✅ IMPLEMENTED
- Downloads audio via yt-dlp with automatic MP3 conversion
- Uses pydub for metadata extraction and optional normalization
- **Target format**: MP3, 192kbps, 44.1kHz sample rate

**`core/beat_detector.py`** ✅ IMPLEMENTED
- Uses aubio for beat detection (optional dependency)
- Returns median BPM for robustness against tempo variations
- Creates sync points every 16 beats to handle BPM drift
- Graceful fallback when aubio not available (raises clear error)

**`core/xml_modifier.py`** ✅ IMPLEMENTED
- Uses lxml for faster parsing and better XPath support
- Preserves original XML formatting (indentation, spacing)
- Complete documentation in `docs/GP8_FORMAT.md`

**`cli/main.py`** *(to be implemented)*
- Interactive menu using questionary for prompts
- Progress feedback using rich library (progress bars, panels, spinners)
- Orchestrates the 5-phase pipeline

**`utils/exceptions.py`**
- Exception hierarchy rooted at `GuitarProToolError`
- Specific exceptions: `GPFileError`, `AudioProcessingError`, `BeatDetectionError`, `XMLModificationError`

**`utils/logger.py`**
- Configured loguru logger (NOT stdlib logging)
- Console output: INFO+ with colors
- File output: DEBUG+ with rotation (if log file specified)

## Critical Technical Constraints

### ZIP Compression Preservation
When repackaging .gp files, you MUST match the original ZIP compression settings exactly. The `GPFile` class stores compression metadata during extraction in `_compression_info` dict and reapplies it during repackaging. Don't modify this logic without testing that repackaged files open in GP8.

### Sync Point Format (Unknown)
The format of sync points in the `<AudioTrack>` XML is **undocumented**. Likely options:
- Beat positions (e.g., 0, 16, 32 for measures in 4/4) - most probable
- MIDI ticks
- Milliseconds

This must be determined empirically by comparing GP8 files with/without audio tracks. Test incrementally - try minimal sync point values, verify GP8 accepts the file, observe playback behavior.

### Beat Detection Strategy
Create sync points at:
1. Start of song (first beat)
2. Every 16 beats thereafter

This handles BPM drift in recordings. More frequent sync points = more accurate alignment but larger XML.

## Testing Philosophy

**Unit tests**: Each core module in isolation, mock external dependencies (yt-dlp, ffmpeg, aubio)

**Integration tests**: End-to-end workflow with sample .gp files
- Extract → Modify → Repackage → Verify file still opens in GP8
- Full pipeline: Download audio → Detect BPM → Inject → Verify audio plays in GP8

**Test fixtures** (`tests/conftest.py`):
- `sample_gp_file`: Minimal valid .gp with basic score.gpif
- `sample_gp_with_audio`: .gp file with existing Audio directory
- `invalid_zip_file`: Not a ZIP archive (tests error handling)
- `corrupted_gp_file`: Missing score.gpif (tests validation)

**Manual validation required**: After implementing XML injection, you MUST test that modified .gp files open in Guitar Pro 8 application. Automated tests cannot verify this.

## Development Roadmap (Current Status)

**Phase 1: Foundation** ✅ COMPLETE
- GPFile class implemented with full test coverage
- Exception hierarchy defined
- Logger configured

**Phase 2: Audio Processing** ✅ COMPLETE
- AudioProcessor class implemented with yt-dlp and pydub
- YouTube download with automatic MP3 conversion
- Local file conversion to target specs (MP3, 192kbps, 44.1kHz)
- UUID generation for GP8 compatibility
- Comprehensive test suite (83 test cases)
- Progress callback support for UI integration

**Phase 3: XML Modification** ✅ COMPLETE
- ✅ GP8 format reverse-engineered from sample files
- ✅ Complete documentation in `docs/GP8_FORMAT.md`
- ✅ XMLModifier class implemented with lxml parsing
- ✅ BackingTrack, Asset, and SyncPoint injection methods
- ✅ Comprehensive test suite (41 test cases)
- Location: `src/guitarprotool/core/xml_modifier.py`
- Tests: `tests/test_xml_modifier.py`

**Phase 4: Beat Detection** ✅ COMPLETE
- ✅ BeatDetector class implemented with aubio
- ✅ BPM detection using median for robustness against tempo drift
- ✅ Beat position detection with progress callback support
- ✅ Sync point generation (bar, frame_offset, modified_tempo, original_tempo)
- ✅ Comprehensive test suite (40 test cases)
- Location: `src/guitarprotool/core/beat_detector.py`
- Tests: `tests/test_beat_detector.py`

**Phase 5: CLI Interface** ✅ COMPLETE
- ✅ Interactive menu with questionary (main menu, file selection, audio source)
- ✅ Rich progress bars and formatting (spinners, progress bars, panels, tables)
- ✅ Full pipeline wired: Extract → Audio Processing → Beat Detection → XML Injection → Repackage
- ✅ Standalone BPM detection mode
- ✅ User-friendly error handling and progress feedback
- ✅ Test suite (14 test cases)
- Location: `src/guitarprotool/cli/main.py`
- Entry point: `src/guitarprotool/__main__.py`
- Tests: `tests/test_cli.py`

**Phase 6: Integration Testing**
- End-to-end tests with real .gp files
- Manual validation in Guitar Pro 8
- Performance testing with long audio files

## Important Implementation Notes

### AudioProcessor (Implemented):
- ✅ Uses yt-dlp's `postprocessors` for automatic MP3 conversion
- ✅ Configured with `preferredcodec: 'mp3'` and `preferredquality: '192'`
- ✅ Progress callback support (ready for rich.progress integration)
- ✅ Handles both YouTube URLs and local audio files
- ✅ UUID generation using SHA1 hash (matches GP8 format exactly)
- ✅ Target specs: MP3, 192kbps, 44.1kHz, stereo
- Location: `src/guitarprotool/core/audio_processor.py`
- Tests: `tests/test_audio_processor.py` (83 test cases)

### XMLModifier (Implemented):
- ✅ Uses lxml for XML parsing with CDATA preservation
- ✅ `XMLModifier.load()` - Parse score.gpif
- ✅ `XMLModifier.inject_backing_track(config)` - Add BackingTrack element
- ✅ `XMLModifier.inject_asset(asset_info)` - Add Asset element
- ✅ `XMLModifier.inject_sync_points(sync_points)` - Add SyncPoint automations
- ✅ `XMLModifier.save()` - Save with XML declaration and pretty printing
- ✅ Helper methods: `get_original_tempo()`, `get_bar_count()`, `has_backing_track()`, `has_assets()`
- Data classes: `SyncPoint`, `AssetInfo`, `BackingTrackConfig`
- Location: `src/guitarprotool/core/xml_modifier.py`

### BeatDetector (Implemented):
- ✅ Uses `aubio.tempo("default", win_s=1024, hop_s=512, sample_rate)`
- ✅ Returns **median** BPM from all detected values (more robust than mean)
- ✅ `BeatDetector.analyze()` - Full analysis returning BeatInfo (bpm, beat_times, confidence)
- ✅ `BeatDetector.detect_bpm()` - BPM-only detection
- ✅ `BeatDetector.generate_sync_points()` - Creates SyncPointData list for XML injection
- ✅ Configurable sync interval (default 16 beats), beats per bar, and start offset
- ✅ Local tempo calculation for each sync point (handles tempo drift)
- Data classes: `BeatInfo`, `SyncPointData`
- Location: `src/guitarprotool/core/beat_detector.py`
- Tests: `tests/test_beat_detector.py` (40 test cases)

### CLI (Implemented):
- ✅ Uses `questionary.path()` for file selection with validation
- ✅ Uses `rich.progress.Progress()` with SpinnerColumn, BarColumn, TaskProgressColumn
- ✅ Pipeline phases wrapped in try/except with user-friendly errors via rich.console
- ✅ Main menu: "Inject audio into GP file", "Detect BPM from audio file", "Exit"
- ✅ Step-by-step workflow with progress feedback
- ✅ Manual BPM override option after detection
- ✅ Handles Python 3.14 pydub/audioop compatibility gracefully
- Location: `src/guitarprotool/cli/main.py`
- Tests: `tests/test_cli.py` (14 test cases)

## Entry Point
The `__main__.py` calls `cli.main.main()` which displays the interactive menu. Entry point registered in `pyproject.toml` as `guitarprotool = "guitarprotool.__main__:main"`.

Run with: `python -m guitarprotool` or `guitarprotool` (if installed)
