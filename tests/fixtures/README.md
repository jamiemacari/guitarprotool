# Test Fixtures for Manual Testing

This directory contains test fixtures for validating the audio injection pipeline.

## Quick Start

Once you've added your test files, run all tests with a single command:

```bash
guitarprotool --test-mode
```

## Structure

Each song has its own directory with:
- `input.gp` - Original Guitar Pro file without audio
- `reference.gp` - Manually synchronized reference file (created in GP8)
- `youtube_url.txt` - YouTube URL used for audio (one URL per line)
- `notes.md` - Description of test case and expected behavior

## Setup Instructions

### 1. Copy Test Files

Copy your GP files into the appropriate directories:

```bash
# Simple song (Nirvana - In Bloom)
cp /path/to/in_bloom.gp tests/fixtures/simple_song/input.gp
cp /path/to/in_bloom_synced.gp tests/fixtures/simple_song/reference.gp

# Complex intro (Air - La Femme d'Argent)
cp /path/to/la_femme.gpx tests/fixtures/complex_intro/input.gp
cp /path/to/la_femme_synced.gp tests/fixtures/complex_intro/reference.gp
```

### 2. Add YouTube URLs

```bash
echo "https://youtube.com/watch?v=YOUR_URL_HERE" > tests/fixtures/simple_song/youtube_url.txt
echo "https://youtube.com/watch?v=YOUR_URL_HERE" > tests/fixtures/complex_intro/youtube_url.txt
```

### 3. Run Tests

```bash
guitarprotool --test-mode
```

Output files are saved to a temp directory (shown in the output).

## Test Case Categories

### Simple Songs (music starts on first beat)
- No intro bars before bass enters
- Expected: high accuracy out of the box
- Example: Nirvana - In Bloom

### Complex Intros (ambient/silent intro)
- Bars of silence or ambient audio before bass
- Tests bass isolation and intro alignment
- Reference may have fewer sync points (user only added where needed)
- Example: Air - La Femme d'Argent

## Adding New Test Cases

1. Create a new directory: `tests/fixtures/{song_name}/`
2. Add the original GP file as `input.gp`
3. Create reference manually:
   - Run the tool: `guitarprotool -i input.gp -y "URL" -o temp.gp`
   - Open `temp.gp` in Guitar Pro 8
   - Adjust sync points manually until audio is aligned
   - Save as `reference.gp`
4. Save YouTube URL in `youtube_url.txt`
5. Document test case in `notes.md`

## Git Ignored Files

The actual GP files (.gp, .gpx) and YouTube URLs are git-ignored to avoid:
- Copyright issues with copyrighted music files
- Repository bloat from binary files
- Sensitive URL exposure

Only the README.md and notes.md files are tracked in git.
