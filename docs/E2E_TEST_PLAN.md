# Guitar Pro Audio Injection Tool - E2E Test Plan

## Document Information

| Field | Value |
|-------|-------|
| Version | 1.0 |
| Created | 2025-12-06 |
| Author | QA Team |
| Status | Active |

---

## 1. Executive Summary

This document provides a comprehensive manual end-to-end test plan for the Guitar Pro Audio Injection Tool. The tool automates downloading YouTube audio, injecting it into Guitar Pro 8 (.gp) files, and creating sync points for playback alignment.

### Scope

- Full audio injection workflow testing
- Standalone BPM detection testing
- Error handling and edge cases
- Cross-platform validation
- Guitar Pro 8 integration verification

### Out of Scope

- Unit testing (covered in automated test suite)
- Performance benchmarking under heavy load
- Security/penetration testing

---

## 2. Test Environment Prerequisites

### 2.1 Software Requirements

| Software | Required Version | Notes |
|----------|------------------|-------|
| Python | 3.11 or 3.12 | 3.13+ has pydub/audioop issues |
| Guitar Pro 8 | Latest | For final validation |
| ffmpeg | Latest stable | Must be in PATH |
| pip | Latest | For package management |

### 2.2 System Configuration Checklist

- [ ] Python 3.11/3.12 installed and in PATH
- [ ] ffmpeg installed and in PATH (`ffmpeg -version` works)
- [ ] Guitar Pro 8 installed
- [ ] Internet connection available (for YouTube tests)
- [ ] At least 1GB free disk space
- [ ] Read/write access to test directories

### 2.3 Tool Installation

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements-dev.txt
pip install -e .

# Verify installation
guitarprotool --help  # or python -m guitarprotool
```

---

## 3. Test Data Requirements

### 3.1 Guitar Pro Files

| File | Description | Location |
|------|-------------|----------|
| `simple_song.gp` | Basic .gp file with 1 track, 4/4 time, 120 BPM | `tests/fixtures/` |
| `content_gpif.gp` | .gp file with score.gpif in Content/ folder | `tests/fixtures/` |
| `complex_song.gp` | Multi-track, tempo changes, 200+ bars | `tests/fixtures/` |
| `with_audio.gp` | .gp file already containing audio track | `tests/fixtures/` |
| `corrupted.gp` | Invalid/corrupted .gp file | `tests/fixtures/` |

### 3.2 Audio Files

| File | Description | Duration | Format |
|------|-------------|----------|--------|
| `short_audio.mp3` | Very short audio | 5 seconds | MP3 192kbps |
| `standard_audio.mp3` | Normal length audio | 3-5 minutes | MP3 192kbps |
| `long_audio.mp3` | Extended audio | 60+ minutes | MP3 192kbps |
| `variable_tempo.mp3` | Audio with tempo drift | 3 minutes | MP3 192kbps |
| `no_beat.mp3` | Ambient/beatless audio | 1 minute | MP3 192kbps |
| `test_audio.wav` | WAV format audio | 30 seconds | WAV 44.1kHz |
| `test_audio.flac` | FLAC format audio | 30 seconds | FLAC |

### 3.3 YouTube URLs (Stable)

| URL | Description | Duration |
|-----|-------------|----------|
| Use stable YouTube videos | Classic rock song | ~4 minutes |
| Creative Commons content | Avoid copyrighted content that may be removed | Variable |

**Note:** YouTube URLs may become unavailable. Use URLs from official channels or Creative Commons content that are unlikely to be removed.

---

## 4. Test Cases

### 4.1 Setup and Launch (TC-001 to TC-005)

#### TC-001: Application Launch

| Field | Value |
|-------|-------|
| **Category** | Setup |
| **Priority** | P0-Critical |
| **Preconditions** | Tool installed, terminal open |
| **Estimated Time** | 1 minute |

**Test Steps:**
1. Open terminal/command prompt
2. Navigate to project directory
3. Activate virtual environment: `source venv/bin/activate`
4. Run: `python -m guitarprotool`

**Expected Results:**
- Application banner displays with version number
- Main menu appears with three options:
  - "Inject audio into GP file"
  - "Detect BPM from audio file"
  - "Exit"
- No error messages displayed

**Verification:** Visual inspection of terminal output

---

#### TC-002: Application Launch via Entry Point

| Field | Value |
|-------|-------|
| **Category** | Setup |
| **Priority** | P1-High |
| **Preconditions** | Tool installed with `pip install -e .` |
| **Estimated Time** | 1 minute |

**Test Steps:**
1. Open terminal
2. Activate virtual environment
3. Run: `guitarprotool`

**Expected Results:**
- Same output as TC-001
- Entry point command works correctly

---

#### TC-003: Exit Application

| Field | Value |
|-------|-------|
| **Category** | Setup |
| **Priority** | P2-Medium |
| **Preconditions** | Application running |
| **Estimated Time** | 30 seconds |

**Test Steps:**
1. Launch application
2. Select "Exit" from main menu

**Expected Results:**
- "Goodbye!" message displayed
- Application exits cleanly
- Return to shell prompt

---

#### TC-004: Keyboard Interrupt (Ctrl+C)

| Field | Value |
|-------|-------|
| **Category** | Setup |
| **Priority** | P2-Medium |
| **Preconditions** | Application running |
| **Estimated Time** | 30 seconds |

**Test Steps:**
1. Launch application
2. At any prompt, press Ctrl+C

**Expected Results:**
- "Interrupted." message displayed
- Application exits with code 1
- No stack trace shown to user

---

#### TC-005: Missing Dependencies Warning

| Field | Value |
|-------|-------|
| **Category** | Setup |
| **Priority** | P1-High |
| **Preconditions** | Python 3.14+ environment (or audioop unavailable) |
| **Estimated Time** | 2 minutes |

**Test Steps:**
1. Create Python 3.14 environment
2. Install tool without audioop-lts
3. Launch application
4. Attempt "Inject audio into GP file"

**Expected Results:**
- Warning logged about AudioProcessor unavailability
- Clear error message when audio processing attempted
- Application continues running (doesn't crash)

---

### 4.2 Happy Path - Audio Injection (TC-010 to TC-019)

#### TC-010: Complete YouTube Audio Injection

| Field | Value |
|-------|-------|
| **Category** | Happy Path |
| **Priority** | P0-Critical |
| **Preconditions** | Valid .gp file, active internet, ffmpeg installed |
| **Estimated Time** | 5-10 minutes |

**Test Steps:**
1. Launch application
2. Select "Inject audio into GP file"
3. **Step 1:** Enter path to valid .gp file
4. **Step 2:** Select "YouTube URL"
5. Enter valid YouTube URL
6. **Step 3:** Enter track name (e.g., "My Audio Track")
7. **Step 4:** Accept default output path or specify custom
8. If output exists, confirm overwrite
9. **Step 5:** Wait for processing:
   - Extracting GP file
   - Processing audio (download + conversion)
   - Detecting beats
   - Generating sync points
   - Modifying GP file
   - Repackaging

**Expected Results:**
- Progress bars display for each step
- BPM detection results shown in table format
- Option to manually override BPM offered
- Success panel displays with:
  - Output file path
  - Detected BPM
  - Number of sync points
  - Original tempo
- Output file exists at specified location

**Verification:**
1. File size > original .gp file
2. Open in Guitar Pro 8 (TC-050)

**Cleanup:** None required

---

#### TC-011: Complete Local Audio Injection

| Field | Value |
|-------|-------|
| **Category** | Happy Path |
| **Priority** | P0-Critical |
| **Preconditions** | Valid .gp file, valid local audio file |
| **Estimated Time** | 3-5 minutes |

**Test Steps:**
1. Launch application
2. Select "Inject audio into GP file"
3. **Step 1:** Enter path to valid .gp file
4. **Step 2:** Select "Local audio file"
5. Enter path to local MP3 file
6. **Step 3:** Enter track name
7. **Step 4:** Accept default output path
8. **Step 5:** Wait for processing

**Expected Results:**
- Same as TC-010
- Processing should be faster (no download)

**Verification:** Open output in Guitar Pro 8

---

#### TC-012: Manual BPM Override

| Field | Value |
|-------|-------|
| **Category** | Happy Path |
| **Priority** | P1-High |
| **Preconditions** | Valid inputs, processing complete to BPM display |
| **Estimated Time** | 5 minutes |

**Test Steps:**
1. Follow TC-010 or TC-011 through Step 5 (processing)
2. When BPM results displayed, respond "yes" to manual BPM
3. Enter custom BPM value (e.g., "120")
4. Wait for remaining processing

**Expected Results:**
- "Using manual BPM: 120" displayed
- Processing continues with custom BPM
- Output file created successfully

---

#### TC-013: Custom Output Path

| Field | Value |
|-------|-------|
| **Category** | Happy Path |
| **Priority** | P2-Medium |
| **Preconditions** | Valid inputs |
| **Estimated Time** | 5 minutes |

**Test Steps:**
1. Follow injection flow to Step 4
2. Enter custom output path (e.g., `/tmp/my_custom_output.gp`)
3. Complete processing

**Expected Results:**
- File created at specified custom path
- Original file unchanged
- Success message shows custom path

---

#### TC-014: Overwrite Existing Output

| Field | Value |
|-------|-------|
| **Category** | Happy Path |
| **Priority** | P2-Medium |
| **Preconditions** | Output file already exists |
| **Estimated Time** | 5 minutes |

**Test Steps:**
1. Create an existing output file
2. Run injection workflow
3. Use same output path as existing file
4. When prompted "File exists. Overwrite?", select "Yes"
5. Complete processing

**Expected Results:**
- Original file overwritten
- New file contains injected audio
- No additional files created

---

#### TC-015: Decline Overwrite

| Field | Value |
|-------|-------|
| **Category** | Happy Path |
| **Priority** | P2-Medium |
| **Preconditions** | Output file already exists |
| **Estimated Time** | 2 minutes |

**Test Steps:**
1. Create an existing output file
2. Run injection workflow
3. Use same output path as existing file
4. When prompted "File exists. Overwrite?", select "No"

**Expected Results:**
- "Cancelled." message displayed
- Original file unchanged
- Returns to main menu

---

#### TC-016: GP File with Content/ Structure

| Field | Value |
|-------|-------|
| **Category** | Happy Path |
| **Priority** | P1-High |
| **Preconditions** | .gp file with score.gpif inside Content/ folder |
| **Estimated Time** | 5 minutes |

**Test Steps:**
1. Run injection workflow with .gp file that has Content/score.gpif structure
2. Complete all steps normally

**Expected Results:**
- Tool correctly locates score.gpif in Content/ folder
- Processing completes successfully
- Output file opens correctly in Guitar Pro 8

---

#### TC-017: Long Track Name

| Field | Value |
|-------|-------|
| **Category** | Happy Path |
| **Priority** | P3-Low |
| **Preconditions** | Valid inputs |
| **Estimated Time** | 5 minutes |

**Test Steps:**
1. Run injection workflow
2. At Step 3, enter long track name (50+ characters)
3. Complete processing

**Expected Results:**
- Track name accepted
- Short name truncated to 8 characters
- Output file valid

---

#### TC-018: WAV Audio Input

| Field | Value |
|-------|-------|
| **Category** | Happy Path |
| **Priority** | P1-High |
| **Preconditions** | Valid WAV audio file |
| **Estimated Time** | 5 minutes |

**Test Steps:**
1. Run injection workflow
2. Select "Local audio file"
3. Enter path to .wav file
4. Complete processing

**Expected Results:**
- WAV converted to MP3 successfully
- Audio embedded in output file
- Plays correctly in Guitar Pro 8

---

#### TC-019: FLAC Audio Input

| Field | Value |
|-------|-------|
| **Category** | Happy Path |
| **Priority** | P2-Medium |
| **Preconditions** | Valid FLAC audio file |
| **Estimated Time** | 5 minutes |

**Test Steps:**
1. Run injection workflow with FLAC file as input

**Expected Results:**
- FLAC converted to MP3 successfully
- Output file valid and playable

---

### 4.3 Happy Path - BPM Detection (TC-020 to TC-025)

#### TC-020: Standalone BPM Detection - MP3

| Field | Value |
|-------|-------|
| **Category** | Happy Path |
| **Priority** | P1-High |
| **Preconditions** | Valid MP3 audio file |
| **Estimated Time** | 2 minutes |

**Test Steps:**
1. Launch application
2. Select "Detect BPM from audio file"
3. Enter path to MP3 file
4. Wait for detection

**Expected Results:**
- Progress spinner shows during detection
- Table displayed with:
  - Detected BPM
  - Total Beats
  - Confidence
  - Duration
- Returns to main menu after display

---

#### TC-021: Standalone BPM Detection - WAV

| Field | Value |
|-------|-------|
| **Category** | Happy Path |
| **Priority** | P2-Medium |
| **Preconditions** | Valid WAV audio file |
| **Estimated Time** | 2 minutes |

**Test Steps:**
1. Select "Detect BPM from audio file"
2. Enter path to WAV file

**Expected Results:**
- BPM detection succeeds
- Results displayed correctly

---

#### TC-022: Cancel BPM Detection

| Field | Value |
|-------|-------|
| **Category** | Happy Path |
| **Priority** | P3-Low |
| **Preconditions** | None |
| **Estimated Time** | 1 minute |

**Test Steps:**
1. Select "Detect BPM from audio file"
2. Press Enter without entering path (or Ctrl+C)

**Expected Results:**
- Returns to main menu without error

---

---

### 4.4 Error Handling (TC-030 to TC-049)

#### TC-030: Non-Existent GP File

| Field | Value |
|-------|-------|
| **Category** | Error Handling |
| **Priority** | P0-Critical |
| **Preconditions** | None |
| **Estimated Time** | 1 minute |

**Test Steps:**
1. Start injection workflow
2. Enter path to non-existent file: `/path/to/nonexistent.gp`

**Expected Results:**
- Error message: "File not found: /path/to/nonexistent.gp"
- "Cancelled." displayed
- Returns to main menu
- No crash or stack trace

---

#### TC-031: Wrong File Extension

| Field | Value |
|-------|-------|
| **Category** | Error Handling |
| **Priority** | P1-High |
| **Preconditions** | Non-.gp file exists |
| **Estimated Time** | 1 minute |

**Test Steps:**
1. Start injection workflow
2. Enter path to .mp3 file or .txt file

**Expected Results:**
- Error message: "Expected .gp file, got: .mp3"
- Returns to main menu

---

#### TC-032: Corrupted GP File

| Field | Value |
|-------|-------|
| **Category** | Error Handling |
| **Priority** | P1-High |
| **Preconditions** | Corrupted .gp file (not valid ZIP) |
| **Estimated Time** | 2 minutes |

**Test Steps:**
1. Create a text file renamed to .gp
2. Start injection workflow with this file

**Expected Results:**
- Error during extraction step
- User-friendly error message (not raw exception)
- Cleanup of temp files

---

#### TC-033: Missing score.gpif

| Field | Value |
|-------|-------|
| **Category** | Error Handling |
| **Priority** | P1-High |
| **Preconditions** | .gp file (ZIP) without score.gpif |
| **Estimated Time** | 2 minutes |

**Test Steps:**
1. Create ZIP with random content, rename to .gp
2. Start injection workflow

**Expected Results:**
- Error about missing score.gpif
- Graceful error handling

---

#### TC-034: Invalid YouTube URL

| Field | Value |
|-------|-------|
| **Category** | Error Handling |
| **Priority** | P0-Critical |
| **Preconditions** | Valid GP file |
| **Estimated Time** | 2 minutes |

**Test Steps:**
1. Start injection workflow
2. Select YouTube URL
3. Enter invalid URL: "not-a-url"

**Expected Results:**
- Error during audio processing step
- Clear error message about invalid URL
- Temp files cleaned up

---

#### TC-035: Private/Unavailable YouTube Video

| Field | Value |
|-------|-------|
| **Category** | Error Handling |
| **Priority** | P1-High |
| **Preconditions** | URL of private/deleted video |
| **Estimated Time** | 2 minutes |

**Test Steps:**
1. Start injection workflow
2. Enter URL of private or deleted video

**Expected Results:**
- Error message indicating video unavailable
- Processing stops gracefully
- Returns to main menu

---

#### TC-036: Non-Existent Local Audio File

| Field | Value |
|-------|-------|
| **Category** | Error Handling |
| **Priority** | P1-High |
| **Preconditions** | None |
| **Estimated Time** | 1 minute |

**Test Steps:**
1. Start injection workflow
2. Select "Local audio file"
3. Enter path to non-existent file

**Expected Results:**
- Error message about file not found
- Graceful handling

---

#### TC-037: Corrupted Audio File

| Field | Value |
|-------|-------|
| **Category** | Error Handling |
| **Priority** | P2-Medium |
| **Preconditions** | File with .mp3 extension but invalid content |
| **Estimated Time** | 2 minutes |

**Test Steps:**
1. Create text file renamed to .mp3
2. Start injection workflow with this file

**Expected Results:**
- Error during audio processing or beat detection
- User-friendly error message

---

#### TC-038: Read-Only Output Directory

| Field | Value |
|-------|-------|
| **Category** | Error Handling |
| **Priority** | P2-Medium |
| **Preconditions** | Read-only directory |
| **Estimated Time** | 3 minutes |

**Test Steps:**
1. Create read-only directory: `mkdir /tmp/readonly && chmod 444 /tmp/readonly`
2. Start injection workflow
3. Set output path in read-only directory

**Expected Results:**
- Error when attempting to write output
- Clear permission error message

**Cleanup:** `rm -rf /tmp/readonly`

---

#### TC-039: Disk Full Simulation

| Field | Value |
|-------|-------|
| **Category** | Error Handling |
| **Priority** | P3-Low |
| **Preconditions** | Very limited disk space |
| **Estimated Time** | 5 minutes |

**Test Steps:**
1. Fill disk to nearly full
2. Attempt injection with large audio file

**Expected Results:**
- Error about insufficient disk space
- Partial files cleaned up

---

#### TC-040: Network Failure During YouTube Download

| Field | Value |
|-------|-------|
| **Category** | Error Handling |
| **Priority** | P2-Medium |
| **Preconditions** | Ability to disable network mid-download |
| **Estimated Time** | 5 minutes |

**Test Steps:**
1. Start injection with YouTube URL
2. During download progress, disable network
3. Wait for timeout/failure

**Expected Results:**
- Error about network/download failure
- Temp files cleaned up
- Returns to main menu

---

#### TC-041: Cancel During Processing

| Field | Value |
|-------|-------|
| **Category** | Error Handling |
| **Priority** | P2-Medium |
| **Preconditions** | Long audio file for extended processing |
| **Estimated Time** | 3 minutes |

**Test Steps:**
1. Start injection workflow
2. During any processing step, press Ctrl+C

**Expected Results:**
- "Interrupted." message
- Temp files cleaned up
- Clean exit

---

#### TC-042: Empty Audio Source Input

| Field | Value |
|-------|-------|
| **Category** | Error Handling |
| **Priority** | P2-Medium |
| **Preconditions** | None |
| **Estimated Time** | 1 minute |

**Test Steps:**
1. Start injection workflow
2. At YouTube URL prompt, press Enter with empty input

**Expected Results:**
- "Cancelled." displayed
- Returns to main menu

---

#### TC-043: GP File Open in Another Application

| Field | Value |
|-------|-------|
| **Category** | Error Handling |
| **Priority** | P2-Medium |
| **Preconditions** | .gp file open in Guitar Pro 8 |
| **Estimated Time** | 3 minutes |

**Test Steps:**
1. Open .gp file in Guitar Pro 8
2. Start injection workflow with same file

**Expected Results:**
- May succeed (reading) or show appropriate error
- No data corruption
- Original file intact

---

---

### 4.5 Edge Cases (TC-050 to TC-065)

#### TC-050: Very Short Audio (<10 seconds)

| Field | Value |
|-------|-------|
| **Category** | Edge Case |
| **Priority** | P2-Medium |
| **Preconditions** | Audio file <10 seconds |
| **Estimated Time** | 3 minutes |

**Test Steps:**
1. Run injection with very short audio file

**Expected Results:**
- Beat detection may have lower confidence
- Sync points generated (even if few)
- Output file valid

---

#### TC-051: Very Long Audio (>1 hour)

| Field | Value |
|-------|-------|
| **Category** | Edge Case |
| **Priority** | P2-Medium |
| **Preconditions** | Audio file >60 minutes |
| **Estimated Time** | 15-30 minutes |

**Test Steps:**
1. Run injection with hour-long audio file

**Expected Results:**
- Processing completes (may take time)
- Many sync points generated
- Output file opens in GP8

---

#### TC-052: Audio with No Discernible Beat

| Field | Value |
|-------|-------|
| **Category** | Edge Case |
| **Priority** | P2-Medium |
| **Preconditions** | Ambient/beatless audio file |
| **Estimated Time** | 3 minutes |

**Test Steps:**
1. Run injection with ambient music or white noise

**Expected Results:**
- Beat detection completes with low confidence
- Manual BPM option offered
- With manual BPM, output file valid

---

#### TC-053: Audio with Highly Variable Tempo

| Field | Value |
|-------|-------|
| **Category** | Edge Case |
| **Priority** | P2-Medium |
| **Preconditions** | Audio with tempo changes (e.g., classical music) |
| **Estimated Time** | 5 minutes |

**Test Steps:**
1. Run injection with variable-tempo audio

**Expected Results:**
- BPM detection uses average tempo
- Multiple sync points handle tempo variations
- Sync may not be perfect but file is valid

---

#### TC-054: GP File with Existing Audio Track

| Field | Value |
|-------|-------|
| **Category** | Edge Case |
| **Priority** | P1-High |
| **Preconditions** | .gp file already containing audio |
| **Estimated Time** | 5 minutes |

**Test Steps:**
1. Run injection on .gp file that already has audio track

**Expected Results:**
- Tool behavior documented (replace, add, or error)
- No file corruption
- Clear messaging to user

---

#### TC-055: Filenames with Spaces

| Field | Value |
|-------|-------|
| **Category** | Edge Case |
| **Priority** | P1-High |
| **Preconditions** | Files with spaces in names |
| **Estimated Time** | 5 minutes |

**Test Steps:**
1. Use .gp file: "My Song File.gp"
2. Use audio file: "My Audio Track.mp3"
3. Set output: "My Output File.gp"

**Expected Results:**
- All paths handled correctly
- Output file created successfully

---

#### TC-056: Filenames with Special Characters

| Field | Value |
|-------|-------|
| **Category** | Edge Case |
| **Priority** | P2-Medium |
| **Preconditions** | Files with special chars |
| **Estimated Time** | 5 minutes |

**Test Steps:**
1. Use files with names like: "Song (Live) - Band.gp"
2. Complete injection workflow

**Expected Results:**
- Special characters handled
- Output file created

---

#### TC-057: Unicode Characters in Paths

| Field | Value |
|-------|-------|
| **Category** | Edge Case |
| **Priority** | P2-Medium |
| **Preconditions** | Paths with non-ASCII characters |
| **Estimated Time** | 5 minutes |

**Test Steps:**
1. Use file: "Cancion.gp" or "Song_" (Japanese chars)
2. Complete injection

**Expected Results:**
- Unicode paths handled correctly
- No encoding errors

---

#### TC-058: Very Long File Path

| Field | Value |
|-------|-------|
| **Category** | Edge Case |
| **Priority** | P3-Low |
| **Preconditions** | Deeply nested directory structure |
| **Estimated Time** | 5 minutes |

**Test Steps:**
1. Create path >200 characters deep
2. Run injection with files in this path

**Expected Results:**
- Either succeeds or gives clear path-length error
- No cryptic failures

---

#### TC-059: Multiple Runs Same Input File

| Field | Value |
|-------|-------|
| **Category** | Edge Case |
| **Priority** | P2-Medium |
| **Preconditions** | None |
| **Estimated Time** | 10 minutes |

**Test Steps:**
1. Run injection on file.gp -> output1.gp
2. Run injection on file.gp -> output2.gp
3. Run injection on file.gp -> output3.gp

**Expected Results:**
- Each output file valid
- Original file unchanged
- No temp file conflicts

---

#### TC-060: Tilde Expansion in Paths

| Field | Value |
|-------|-------|
| **Category** | Edge Case |
| **Priority** | P2-Medium |
| **Preconditions** | Unix-like system |
| **Estimated Time** | 3 minutes |

**Test Steps:**
1. Enter path as: `~/Documents/song.gp`
2. Complete workflow

**Expected Results:**
- Tilde expanded correctly
- File found and processed

---

---

### 4.6 Guitar Pro 8 Validation (TC-070 to TC-080)

#### TC-070: Open Modified File in GP8

| Field | Value |
|-------|-------|
| **Category** | GP8 Validation |
| **Priority** | P0-Critical |
| **Preconditions** | Output file from successful injection |
| **Estimated Time** | 5 minutes |

**Test Steps:**
1. Complete successful injection (TC-010 or TC-011)
2. Open output file in Guitar Pro 8

**Expected Results:**
- File opens without error dialogs
- No "file is corrupted" warnings
- Tab content displays correctly

---

#### TC-071: Verify Audio Track Visible

| Field | Value |
|-------|-------|
| **Category** | GP8 Validation |
| **Priority** | P0-Critical |
| **Preconditions** | Modified file open in GP8 |
| **Estimated Time** | 2 minutes |

**Test Steps:**
1. Open modified file in GP8
2. Open mixer view (View > Mixer)

**Expected Results:**
- Audio track visible in mixer
- Track name matches input
- Waveform displayed

---

#### TC-072: Audio Playback

| Field | Value |
|-------|-------|
| **Category** | GP8 Validation |
| **Priority** | P0-Critical |
| **Preconditions** | Modified file open in GP8 |
| **Estimated Time** | 3 minutes |

**Test Steps:**
1. Open modified file in GP8
2. Press Play (or Space)
3. Listen to audio

**Expected Results:**
- Audio plays back
- Audio is synchronized with tab playback
- No audio glitches or dropouts

---

#### TC-073: Audio Sync Point Alignment

| Field | Value |
|-------|-------|
| **Category** | GP8 Validation |
| **Priority** | P1-High |
| **Preconditions** | Modified file with known tempo |
| **Estimated Time** | 5 minutes |

**Test Steps:**
1. Open modified file
2. Play from different positions in the song
3. Listen for audio/tab synchronization

**Expected Results:**
- Audio stays in sync with tab
- Sync is consistent throughout song
- Minor drift acceptable (within 100ms)

---

#### TC-074: Solo/Mute Audio Track

| Field | Value |
|-------|-------|
| **Category** | GP8 Validation |
| **Priority** | P2-Medium |
| **Preconditions** | Modified file open in GP8 |
| **Estimated Time** | 3 minutes |

**Test Steps:**
1. Open modified file
2. In mixer, click Solo on audio track
3. Play - verify only audio plays
4. Click Mute on audio track
5. Play - verify audio is silent

**Expected Results:**
- Solo/Mute controls work correctly
- Other tracks unaffected

---

#### TC-075: Save and Re-open

| Field | Value |
|-------|-------|
| **Category** | GP8 Validation |
| **Priority** | P1-High |
| **Preconditions** | Modified file open in GP8 |
| **Estimated Time** | 5 minutes |

**Test Steps:**
1. Open modified file in GP8
2. Make a small edit (add a note)
3. Save file (Ctrl+S)
4. Close file
5. Re-open file

**Expected Results:**
- Audio track preserved after save
- Playback still works
- Sync points intact

---

#### TC-076: Export to Different Format

| Field | Value |
|-------|-------|
| **Category** | GP8 Validation |
| **Priority** | P3-Low |
| **Preconditions** | Modified file with audio |
| **Estimated Time** | 5 minutes |

**Test Steps:**
1. Open modified file
2. File > Export > PDF or MIDI

**Expected Results:**
- Export completes
- Audio track handled appropriately (may be excluded)

---

---

### 4.7 Cross-Platform (TC-090 to TC-095)

#### TC-090: macOS Testing

| Field | Value |
|-------|-------|
| **Category** | Cross-Platform |
| **Priority** | P1-High |
| **Preconditions** | macOS system with all prerequisites |
| **Estimated Time** | 30 minutes |

**Test Steps:**
1. Install tool on macOS
2. Run TC-010 (YouTube injection)
3. Run TC-011 (Local injection)
4. Verify output in Guitar Pro 8

**Expected Results:**
- All functionality works on macOS
- Paths handled correctly (forward slashes)

---

#### TC-091: Windows Testing

| Field | Value |
|-------|-------|
| **Category** | Cross-Platform |
| **Priority** | P1-High |
| **Preconditions** | Windows system with all prerequisites |
| **Estimated Time** | 30 minutes |

**Test Steps:**
1. Install tool on Windows
2. Run TC-010 (YouTube injection)
3. Run TC-011 (Local injection)
4. Verify output in Guitar Pro 8

**Expected Results:**
- All functionality works on Windows
- Backslash paths handled correctly
- No encoding issues with Windows paths

---

#### TC-092: Linux Testing

| Field | Value |
|-------|-------|
| **Category** | Cross-Platform |
| **Priority** | P2-Medium |
| **Preconditions** | Linux system with all prerequisites (no GP8) |
| **Estimated Time** | 20 minutes |

**Test Steps:**
1. Install tool on Linux
2. Run TC-010 (YouTube injection)
3. Run TC-011 (Local injection)
4. Transfer output file to machine with GP8 for verification

**Expected Results:**
- Tool runs on Linux
- Output file valid when opened on Mac/Windows

---

---

## 5. Defect Reporting Template

When a test case fails, document the defect using this template:

```markdown
## Defect Report

**Test Case:** TC-XXX
**Date:** YYYY-MM-DD
**Tester:** Name
**Severity:** Critical/High/Medium/Low
**Environment:**
- OS: macOS 14.0 / Windows 11 / Ubuntu 22.04
- Python: 3.11.x
- Tool Version: x.x.x

### Description
Brief description of the failure

### Steps to Reproduce
1. Step one
2. Step two
3. ...

### Expected Result
What should have happened

### Actual Result
What actually happened

### Evidence
- Screenshots
- Log output
- Error messages

### Notes
Additional context
```

---

## 6. Test Execution Checklist

### Pre-Test Checklist

- [ ] Test environment set up per Section 2
- [ ] All test data prepared per Section 3
- [ ] Guitar Pro 8 installed and licensed
- [ ] Internet connection verified
- [ ] Disk space checked (>1GB free)

### Test Execution Sign-off

| Test Category | Pass | Fail | Blocked | Not Run | Sign-off |
|---------------|------|------|---------|---------|----------|
| Setup (TC-001-005) | | | | | |
| Happy Path - Injection (TC-010-019) | | | | | |
| Happy Path - BPM (TC-020-025) | | | | | |
| Error Handling (TC-030-049) | | | | | |
| Edge Cases (TC-050-065) | | | | | |
| GP8 Validation (TC-070-080) | | | | | |
| Cross-Platform (TC-090-095) | | | | | |

### Post-Test Checklist

- [ ] All defects documented
- [ ] Test environment cleaned up
- [ ] Temp files removed
- [ ] Test results archived
- [ ] Sign-off obtained

---

## 7. Appendix

### A. Quick Reference Commands

```bash
# Launch tool
python -m guitarprotool
guitarprotool

# Run automated tests
pytest
pytest --cov=guitarprotool

# Check code quality
black src/ tests/
ruff check src/ tests/
mypy src/
```

### B. Test File Locations

| Item | Path |
|------|------|
| Test fixtures | `tests/fixtures/` |
| Test scripts | `tests/` |
| Main CLI | `src/guitarprotool/cli/main.py` |
| GP8 format docs | `docs/GP8_FORMAT.md` |

### C. Contact Information

For questions about this test plan, contact the development team.

---

*End of Test Plan Document*
