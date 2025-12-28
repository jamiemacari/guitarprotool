# Manual Testing Guide

This guide explains how to test the Guitar Pro Audio Injection Tool.

## Quick Start - Test Mode

The simplest way to run all tests:

```bash
guitarprotool --test-mode
```

This automatically:
1. Finds all test cases in `tests/fixtures/`
2. Runs the pipeline on each one
3. Compares output to reference files (if available)
4. Shows a summary of results
5. Saves output files for manual verification in Guitar Pro

## Other Modes

### Interactive Mode (Default)

```bash
guitarprotool
```

Follow the on-screen prompts to select files and enter URLs.

### Single File Mode

```bash
# With YouTube URL
guitarprotool -i song.gp -y "https://youtube.com/watch?v=..." -o output.gp

# With comparison to reference
guitarprotool -i song.gp -y "URL" -o output.gp --compare reference.gp
```

## Setting Up Test Fixtures

### 1. Create the Fixture Structure

The test fixtures directory structure should already exist:

```
tests/fixtures/
├── simple_song/
│   ├── input.gp          # Your original GP file
│   ├── reference.gp      # Manually synced reference
│   ├── youtube_url.txt   # YouTube URL
│   └── notes.md          # Test case documentation
└── complex_intro/
    ├── input.gp (or .gpx)
    ├── reference.gp
    ├── youtube_url.txt
    └── notes.md
```

### 2. Copy Your Files

```bash
# Simple song (e.g., Nirvana - In Bloom)
cp /path/to/in_bloom.gp tests/fixtures/simple_song/input.gp

# Complex intro (e.g., Air - La Femme d'Argent)
cp /path/to/la_femme.gpx tests/fixtures/complex_intro/input.gpx
```

### 3. Add YouTube URLs

```bash
echo "https://www.youtube.com/watch?v=YOUR_VIDEO_ID" > tests/fixtures/simple_song/youtube_url.txt
echo "https://www.youtube.com/watch?v=YOUR_VIDEO_ID" > tests/fixtures/complex_intro/youtube_url.txt
```

### 4. Create Reference Files

1. Run the tool on your input file:
   ```bash
   guitarprotool -i tests/fixtures/simple_song/input.gp \
     -y "$(cat tests/fixtures/simple_song/youtube_url.txt)" \
     -o /tmp/initial.gp
   ```

2. Open `/tmp/initial.gp` in Guitar Pro 8

3. Play the audio along with the tab

4. Manually adjust sync points where audio drifts from tab

5. Save as `tests/fixtures/simple_song/reference.gp`

## Interpreting Comparison Results

### Sample Output

```
============================================================
SYNC POINT COMPARISON REPORT
============================================================

Generated: /tmp/simple_output.gp
Reference: tests/fixtures/simple_song/reference.gp

SUMMARY:
  Matched bars:                 12
  Extra bars (generated only):  3
  Missing bars (reference only): 0
  Within tolerance:             YES

STATISTICS:
  Avg frame diff: 234.5 samples (5.3 ms)
  Max frame diff: 512 samples (11.6 ms)
  Avg tempo diff: 0.156 BPM
  Max tempo diff: 0.456 BPM

MATCHED BARS:
   Bar    FrameDiff    TempoDiff    Status
  ----  ------------  ----------  --------
     0            +0      +0.000        OK
     4          +234      -0.123        OK
     8          -512      +0.456        OK
   ...

EXTRA BARS (in generated, not in reference):
   Bar   FrameOffset       Tempo
  ----   -----------   ---------
    12         45678       120.5
   ...

------------------------------------------------------------
Tolerances: FrameOffset=4410 samples (100.0ms), Tempo=1.0 BPM
```

### What's Acceptable?

| Status | Meaning |
|--------|---------|
| **Within tolerance = YES** | All matched sync points have acceptable differences |
| **Extra bars** | Tool generated more sync points than reference (acceptable) |
| **Missing bars** | Reference has sync points the tool missed (may need investigation) |
| **FAIL in status** | Individual bar exceeded tolerance threshold |

### Common Issues

#### Audio starts at wrong position
- Check the drift_report.txt in the run folder
- Verify first_beat_time detection
- May need bass isolation for songs with ambient intros

#### Tempo drifts during song
- Check sync point placement in drift_report.txt
- More sync points may be needed (reduce DRIFT_THRESHOLD_PERCENT in code)

#### Many missing bars
- Reference file may have been manually adjusted more aggressively
- Check if reference has sync points at non-standard intervals

## Running Automated Tests

### Unit Tests for Comparison Utility

```bash
pytest tests/test_sync_comparison.py -v
```

### Integration Tests (require fixture files)

```bash
pytest tests/test_sync_comparison.py -v -m integration
```

## Troubleshooting

### Bass Isolation Not Working

Install optional dependencies:
```bash
pip install guitarprotool[bass-isolation]
```

Check GPU availability:
```bash
python -c "import torch; print(torch.cuda.is_available())"
```

### Output Files for Debugging

Each run creates a timestamped folder with debugging artifacts:

```
files/run_YYYYMMDD_HHMMSS/
├── input_<filename>.gp     # Copy of original input
├── <output>.gp             # Modified output file
├── <uuid>.mp3              # Processed audio
├── drift_report.txt        # Tempo drift analysis
├── debug_beats.txt         # Beat detection data
├── session_log.txt         # Console output (text)
└── session_log.html        # Console output (formatted)
```

### Checking Help

```bash
guitarprotool --help
```

Output:
```
usage: guitarprotool [-h] [-i FILE] [-y URL] [--local-audio FILE] [-o FILE]
                     [-n TRACK_NAME] [--compare FILE] [--quiet]

Guitar Pro Audio Injection Tool

options:
  -h, --help            show this help message and exit
  -i FILE, --input FILE
                        Input GP file path
  -y URL, --youtube-url URL
                        YouTube URL for audio
  --local-audio FILE    Local audio file path
  -o FILE, --output FILE
                        Output GP file path
  -n TRACK_NAME, --track-name TRACK_NAME
                        Track name in Guitar Pro (default: Audio Track)
  --compare FILE        Compare output to reference file and print report
  --quiet               Suppress non-essential output
```

## Tolerance Tuning

Default tolerances in `sync_comparator.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `DEFAULT_FRAME_TOLERANCE` | 4410 samples (~100ms) | Maximum allowed frame offset difference |
| `DEFAULT_TEMPO_TOLERANCE` | 1.0 BPM | Maximum allowed tempo difference |

If defaults are too strict or loose, adjust these values when creating the comparator:

```python
from guitarprotool.core.sync_comparator import SyncComparator

# Stricter comparison (50ms, 0.5 BPM)
comparator = SyncComparator(frame_tolerance=2205, tempo_tolerance=0.5)

# More lenient comparison (200ms, 2 BPM)
comparator = SyncComparator(frame_tolerance=8820, tempo_tolerance=2.0)
```
