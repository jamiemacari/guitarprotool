# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Important Workflow Rules

**NEVER merge PRs to main without explicit user confirmation.** Even if the user's prompt says to "complete the PR" or "merge it", always ask for confirmation before merging. Create the PR, then wait for the user to confirm it should be merged.

**ALWAYS use feature branches.** Never commit changes directly to main without explicit double-confirmation from the user. Standard workflow:
1. Create a feature/bugfix branch before making changes
2. Make changes and commit to the feature branch
3. Push and create a PR for review
4. Only merge after user confirms

## Project Overview

Guitar Pro Audio Injection Tool - Automates downloading YouTube audio, injecting it into Guitar Pro files (.gp and .gpx), and creating sync points for playback alignment. Built for automating bass tab practice workflows.

**Supported Formats:**
- `.gp` (Guitar Pro 8) - Native support
- `.gpx` (Guitar Pro 6/7) - Converted to GP8 internally
- `.gp5/.gp4/.gp3` - Not yet supported (shows helpful error with workaround)

## System Dependencies Required

Before working with this codebase, ensure these system dependencies are installed:

**Ubuntu/Debian:**
```bash
sudo apt-get install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

**Python Version**: Use Python 3.11 or 3.12 for best compatibility. Python 3.13+ has issues with pydub's audioop dependency.

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
3. **Detect** (`BeatDetector`) - Analyzes audio for BPM and beat positions using librosa
4. **Inject** (`XMLModifier`) - Modifies score.gpif XML to add AudioTrack element with sync points
5. **Repackage** (`GPFile.repackage()`) - Creates new .gp file with audio and metadata

### Guitar Pro File Format

**Critical**: Guitar Pro 8 .gp files are ZIP archives with this structure:
```
mysong.gp (ZIP file)
├── score.gpif          # Main XML file (may also be at Content/score.gpif)
├── Content/
│   ├── score.gpif      # Alternate location for main XML (some GP8 exports)
│   └── Audio/          # Audio tracks (created if missing)
│       └── *.mp3       # Audio files referenced in XML
└── [other metadata]
```

**Note**: Some GP8 files have `score.gpif` at the root level, others have it inside `Content/`. The `GPFile` class handles both locations automatically.

The `score.gpif` XML file contains all tab data. To add audio:
- Copy MP3 to `Content/Audio/`
- Inject `<AudioTrack>` element into score.gpif XML
- AudioTrack must reference the audio file path and contain sync points

**IMPORTANT**: The GP8 XML schema is proprietary and undocumented. The exact structure of `<AudioTrack>` elements must be reverse-engineered from sample .gp files that already have audio. See `docs/GP8_FORMAT.md` for discoveries.

### Module Responsibilities

**`core/format_handler.py`** - GPFileHandler class (NEW)
- Unified handler for all Guitar Pro file formats (.gp, .gpx, .gp5, .gp4, .gp3)
- Detects format from file extension and routes to appropriate handler
- For GPX files: decompresses BCFZ, fixes XML corruption, creates GP8 structure
- **Key methods**: `prepare_for_audio_injection()`, `get_gpif_path()`, `get_audio_dir()`, `save()`
- Uses context manager pattern for automatic cleanup
- Location: `src/guitarprotool/core/format_handler.py`

**`core/bcfz.py`** - BCFZ Decompression (NEW)
- Handles BCFZ compression used by GPX files (Guitar Pro 6/7)
- Implements LZ77-style decompression with bit streams
- Extracts files from BCFS container format
- **Key functions**: `decompress_bcfz()`, `extract_gpx_files()`
- Location: `src/guitarprotool/core/bcfz.py`

**`core/gp_file.py`** - GPFile class
- Handles .gp file I/O operations (used internally by GPFileHandler)
- Preserves ZIP compression settings exactly (stores metadata during extraction)
- Context manager support for automatic cleanup
- **Key methods**: `extract()`, `get_gpif_path()`, `get_audio_dir()`, `repackage()`

**`core/audio_processor.py`** ✅ IMPLEMENTED
- Downloads audio via yt-dlp with automatic MP3 conversion
- Uses pydub for metadata extraction and optional normalization
- **Target format**: MP3, 192kbps, 44.1kHz sample rate

**`core/beat_detector.py`** ✅ IMPLEMENTED
- Uses librosa for beat detection (replaced aubio due to Python 3.12+ compatibility issues)
- Returns BPM using librosa.beat.beat_track()
- Creates sync points every 16 beats to handle BPM drift
- Graceful fallback when librosa not available (raises clear error)

**`core/xml_modifier.py`** ✅ IMPLEMENTED
- Uses lxml for faster parsing and better XPath support
- Preserves original XML formatting (indentation, spacing)
- Complete documentation in `docs/GP8_FORMAT.md`

**`cli/main.py`** ✅ IMPLEMENTED
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

**Unit tests**: Each core module in isolation, mock external dependencies (yt-dlp, ffmpeg, librosa)

**Integration tests**: End-to-end workflow with sample .gp files
- Extract → Modify → Repackage → Verify file still opens in GP8
- Full pipeline: Download audio → Detect BPM → Inject → Verify audio plays in GP8

**Test fixtures** (`tests/conftest.py`):
- `sample_gp_file`: Minimal valid .gp with basic score.gpif at root
- `sample_gp_file_content_gpif`: .gp with score.gpif inside Content/ folder
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
- ✅ BeatDetector class implemented with librosa (replaced aubio for Python 3.12+ compatibility)
- ✅ BPM detection using librosa.beat.beat_track()
- ✅ Beat position detection with progress callback support
- ✅ Sync point generation (bar, frame_offset, modified_tempo, original_tempo)
- ✅ Test suite (tests need updating for librosa mocks)
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

**Phase 7: Bass Isolation** ✅ COMPLETE
- ✅ BassIsolator class with Demucs v4 (Hybrid Transformer) integration
- ✅ Optional dependency management (torch, torchaudio, demucs)
- ✅ CLI integration with automatic fallback to full-mix beat detection
- ✅ Progress feedback for long-running isolation (~1.5x audio duration)
- ✅ GPU (CUDA) auto-detection with CPU fallback
- ✅ Test suite with mocked dependencies
- Location: `src/guitarprotool/core/bass_isolator.py`
- Tests: `tests/test_bass_isolator.py`
- Install: `pip install guitarprotool[bass-isolation]`

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
- ✅ Uses `librosa.beat.beat_track(y, sr, hop_length)` for beat detection
- ✅ Returns BPM and beat frame positions
- ✅ `BeatDetector.analyze()` - Full analysis returning BeatInfo (bpm, beat_times, confidence)
- ✅ `BeatDetector.detect_bpm()` - BPM-only detection
- ✅ `BeatDetector.generate_sync_points()` - Creates SyncPointData list for XML injection
- ✅ Configurable sync interval (default 16 beats), beats per bar, and start offset
- ✅ Local tempo calculation for each sync point (handles tempo drift)
- Data classes: `BeatInfo`, `SyncPointData`
- Location: `src/guitarprotool/core/beat_detector.py`
- Tests: `tests/test_beat_detector.py` (tests need updating for librosa)

### BassIsolator (Implemented):
- ✅ Uses Demucs v4 Hybrid Transformer for state-of-the-art source separation
- ✅ Isolates bass track for improved beat detection (especially for ambient intros)
- ✅ `BassIsolator.isolate(audio_path)` - Returns IsolationResult with path to isolated bass
- ✅ `BassIsolator.is_available()` - Check if dependencies are installed
- ✅ `BassIsolator.get_device_info()` - Get CUDA/CPU device information
- ✅ Lazy model loading (loads on first isolation call)
- ✅ Progress callback support for UI integration
- ✅ Graceful fallback: if isolation fails, beat detection uses original audio
- Data classes: `IsolationResult`
- Models supported: `htdemucs` (default), `htdemucs_ft`, `hdemucs_mmi`, `htdemucs_6s`
- Location: `src/guitarprotool/core/bass_isolator.py`
- Tests: `tests/test_bass_isolator.py`
- **Optional dependency**: Install with `pip install guitarprotool[bass-isolation]`

### CLI (Implemented):
- ✅ Uses `questionary.path()` for file selection with validation
- ✅ Uses `rich.progress.Progress()` with SpinnerColumn, BarColumn, TaskProgressColumn
- ✅ Pipeline phases wrapped in try/except with user-friendly errors via rich.console
- ✅ Main menu: "Inject audio into GP file", "Detect BPM from audio file", "Exit"
- ✅ Step-by-step workflow with progress feedback
- ✅ Fully automated (no manual BPM prompts)
- ✅ TUI session capture with `Console(record=True)`
- ✅ Handles Python 3.14 pydub/audioop compatibility gracefully
- Location: `src/guitarprotool/cli/main.py`
- Tests: `tests/test_cli.py`

## Entry Point
The `__main__.py` calls `cli.main.main()` which displays the interactive menu. Entry point registered in `pyproject.toml` as `guitarprotool = "guitarprotool.__main__:main"`.

Run with: `python -m guitarprotool` or `guitarprotool` (if installed)

## Known Issues & Next Steps

### Test Suite
- ✅ `tests/test_beat_detector.py` updated to mock librosa (was aubio)
- `tests/test_audio_processor.py` may have pydub/audioop issues on Python 3.13+

### Python Compatibility
- **Recommended**: Python 3.11 or 3.12
- Python 3.13+: pydub has issues with removed `audioop` module (can use `audioop-lts` package as workaround)
- Python 3.14: Not yet supported

### Dependencies Changed
- Replaced `aubio` with `librosa` for beat detection (better Python/NumPy compatibility)
- `librosa` is larger but more actively maintained

## Adaptive Tempo Sync - IMPLEMENTED

**Status:** ✅ Implemented with frame offset fix
**Branch:** `feature/adaptive-tempo-sync`

### What's Implemented
- ✅ `DriftAnalyzer` class in `src/guitarprotool/core/drift_analyzer.py`
- ✅ `adaptive` parameter in `BeatDetector.generate_sync_points()` (default True)
- ✅ Tempo correction for double/half-time detection (`BeatDetector.correct_tempo_multiple()`)
- ✅ Drift report file output (saved to run folder as `drift_report.txt`)
- ✅ Debug beat data output (saved to run folder as `debug_beats.txt`) for diagnosing beat detection issues
- ✅ Drift report shows which bars have sync points (`<<SYNC` marker)
- ✅ CLI displays tempo correction when applied
- ✅ **Frame offsets now use actual detected beat times** (fixed drift issue)

### Current Thresholds (in `drift_analyzer.py`)
```python
DRIFT_THRESHOLD_PERCENT = 0.5  # Place sync point if drift exceeds this
MIN_SYNC_INTERVAL = 1          # Minimum bars between sync points
MAX_SYNC_INTERVAL = 8          # Maximum bars between sync points
```

### Recent Fixes (Dec 2024)
1. ✅ **Frame offset calculation fixed** - Now uses actual detected beat times instead of expected times based on tab tempo. This ensures sync points align with where beats actually occur in the audio, not where they "should" be according to the tab.

2. ✅ **Debug beat data output** - New `DriftAnalyzer.write_debug_beats()` method outputs detailed beat-by-beat timing data including:
   - Beat times (absolute and relative to first beat)
   - Instantaneous BPM between each beat
   - Bar and beat-in-bar positions
   - Interval statistics (avg, std dev, min, max)

3. ✅ **Test coverage expanded** - Added tests for:
   - Frame offset using actual beat times with drifting tempo
   - Frame offset extrapolation beyond detected beats
   - Debug beat data output

### How Frame Offset Calculation Works Now
Frame offsets and FramePadding work together to align audio with the tab:

1. **FramePadding** (in `beat_detector.py`): Negative offset that shifts audio left
   ```python
   frame_padding = -int(first_beat_time * sample_rate)
   ```

2. **FrameOffset** (in `drift_analyzer.py`): Relative position from first beat
   ```python
   relative_time = beat_times[beat_index] - first_beat_time
   return int(relative_time * sample_rate)  # Bar 0 = 0
   ```

**Result:** Bar 0 starts at FrameOffset=0, FramePadding shifts audio so the first detected beat aligns with bar 0.

### Audio Sync Fixes (Dec 2024)

**Investigation #1 - False first onset detection:**
- Fix: Added first beat validation in `BeatDetector.analyze()` to skip false onsets

**Investigation #2 - Audio starting at wrong position (Dec 12-13):**
- Problem: audio50.gp had good sync but wrong start; audio70.gp had good start but broke sync
- Root cause: FramePadding and FrameOffset must BOTH change together
- Comparison with user-corrected file revealed the pattern:
  ```
  audio50:     FramePadding=0,      Bar0=21504, Bar1=162304 (absolute)
  audio70:     FramePadding=-21504, Bar0=21504, Bar1=162304 (mixed = broken!)
  corrected:   FramePadding=-22200, Bar0=0,     Bar1=140104 (both relative)
  ```
- Fix: FramePadding = negative first beat time, FrameOffset = relative to first beat

**Current settings:**
- ✅ **FramePadding = -first_beat_time** - Shifts audio left to align with bar 0
- ✅ **Relative frame offsets** - Bar 0 = 0, subsequent bars relative to first beat
- ✅ **FramesPerPixel = 1274** - Matches typical GP8 files

### Remaining TODO (if sync issues persist)
1. **Add manual first beat offset** - Let user specify exact first beat time via CLI `--first-beat-offset` option
2. **Investigate edge cases** - Some audio may need additional validation logic for first beat detection
3. **Consider percussive separation** - For complex audio, separating drums might improve beat detection

See `docs/ADAPTIVE_TEMPO_SYNC_PLAN.md` for original implementation plan.

## Music Theory Review (Dec 2024)

A comprehensive music theory review was conducted on the beat detection, sync point generation, and drift analysis code. The implementation is **generally sound** but identified several issues affecting sync accuracy.

### HIGH PRIORITY - Main Causes of Sync Issues

**1. Sync Points Only at Bar Starts**
- Current: All sync points have `position=0` (bar start only)
- Problem: GP8's XML schema supports mid-bar sync points, but we don't use them
- Impact: Syncopated music, off-beat accents, and songs with strong backbeat emphasis may not align well
- Location: `xml_modifier.py` line 42 hardcodes `position: int = 0`
- Fix needed: Calculate sub-bar position based on where beats actually fall relative to bar boundaries

**2. Bass = First Beat Assumption**
- Current: Bass isolation finds where bass enters, assumes that's beat 1
- Problem: Not all music has bass on beat 1:
  - **Reggae/dub**: Bass often enters on beat 3 or "and" of beat 2
  - **Jazz**: Walking bass may start mid-phrase
  - **Electronic**: Bass drops are often delayed for effect
- Impact: If bass starts later than the actual musical downbeat, alignment is shifted incorrectly
- Location: `main.py` lines 579-655 (hybrid bass isolation approach)
- Fix needed: Consider using drums/percussion onset detection as alternative, or allow manual override

### MEDIUM PRIORITY

**3. Half-Time Detection Asymmetry**
- Double-time tolerance: ±30% (ratio ~2.0)
- Half-time tolerance: ±7.5% (ratio ~0.5)
- Impact: Half-time feels may not be detected correctly, especially for songs explicitly in half-time
- Location: `beat_detector.py` lines 595-610
- Note: Impact unclear - may not be causing real-world issues

### DEFERRED - Not Currently Needed

**4. Time Signature Support** (deferred)
- Current: Hardcoded `beats_per_bar=4` throughout
- Would break for 3/4, 6/8, 5/4, 7/8 time signatures
- No user reports of issues with odd time signatures yet
- Can read time signature from `score.gpif` when needed

**5. Tempo Change Handling** (deferred)
- Current: Multiple tempo sections treated as "drift"
- Would need to read tempo automations from GP file
- No user reports of songs with actual tempo changes yet

### Review Details

| Area | Assessment |
|------|------------|
| BPM calculation (`60/median_interval`) | Correct |
| 16-beat sync interval (4 bars in 4/4) | Musically sensible |
| Drift thresholds (0.5% tight) | Match perceptual research |
| First beat false onset detection (60% threshold) | Clever and correct |
| Frame offset calculation | Mathematically correct |
| Bass isolation hybrid approach | Generally intelligent |

## Testing Artifacts - Run Folder

**Status:** ✅ Implemented (PR #11)

Each pipeline run saves all artifacts to a timestamped directory for manual testing and debugging:

```
files/run_YYYYMMDD_HHMMSS/
├── input_<filename>.gp    # Copy of original input file
├── <output>.gp            # Modified output file with audio
├── <uuid>.mp3             # Processed audio file
├── drift_report.txt       # Tempo drift analysis
├── debug_beats.txt        # Beat detection debug data
├── session_log.txt        # TUI output (plain text)
└── session_log.html       # TUI output (formatted HTML)
```

### Key Functions
- `get_troubleshooting_dir()` - Creates timestamped run folder
- `save_troubleshooting_copies()` - Copies input, output, and audio files
- `save_session_log()` - Exports TUI session as .txt and .html

### TUI Session Capture
The Rich console is initialized with `record=True` to capture all terminal output:
```python
console = Console(record=True)
```

At the end of the pipeline, session logs are saved via:
```python
console.save_text(str(txt_path))
console.save_html(str(html_path))
```

## GPX Format Support - IMPLEMENTED

**Status:** ✅ Implemented
**Branch:** `support-other-formats`

### GPX File Structure
GPX files (Guitar Pro 6/7) use BCFZ compression containing a BCFS file system:
- `score.gpif` - Main XML file (same schema as GP8)
- `BinaryStylesheet` - Visual styling data
- `LayoutConfiguration` - Page layout settings
- `PartConfiguration` - Part/track configuration
- `misc.xml` - Optional metadata

### GPX to GP8 Conversion Process
1. Read GPX file and decompress BCFZ data (`bcfz.py`)
2. Extract files from BCFS container
3. Fix XML corruption artifacts (`format_handler._fix_gpx_xml()`)
4. Create GP8-compatible directory structure
5. Copy metadata files (BinaryStylesheet, etc.)
6. Create VERSION file

### XML Corruption Fixes
GPX files often have corrupted XML due to compression artifacts. The `_fix_gpx_xml()` method in `format_handler.py` fixes these issues:

**Tag truncation/corruption:**
- `</Params>` → `</Parameters>`
- `<Finge>` → `<Fingering>`
- `<Poon ` → `<Position `
- `<Rhyref=` → `<Rhythm ref=`
- `<Propename=` → `<Property name=`
- `</AccialCount>` → `</AccidentalCount>`
- `</Prty>` → `</Property>`
- `</CleVoices>` → `</Clef><Voices>`
- `</Keyime>` → `</Key><Time>`
- `</IteItem` → `</Item><Item`

**CDATA corruption:**
- `<![A[7]]>` → `<![CDATA[A[7]]]>` (CDATA[ part truncated)

**Tag name doubling:**
- `<StringString>` → `<String></String>` (content merged into tag)
- `<Dynamic>Dynamic>` → `<Dynamic></Dynamic>`

**Attribute corruption:**
- `<Property naWhammyBar...">` → `<Property name="WhammyBar...">`
- Boolean attributes without values: `attr"/>` → `attr="true"/>`

**Container padding:**
- Trailing null bytes stripped from BCFS container

### Adding New XML Fixes
When encountering new XML parse errors from GPX files:
1. Check the error message for line number and column
2. Inspect the raw decompressed XML at that location
3. Identify the corruption pattern
4. Add a fix to `_fix_gpx_xml()` in `format_handler.py`
5. Test with the problematic GPX file

### Test Files
- `tests/test_bcfz.py` - 20 tests for BCFZ decompression
- `tests/test_format_handler.py` - 27 tests for format handling
