# Test Fixtures for Manual Testing

This directory contains test fixtures for validating the audio injection pipeline.

## Quick Start

Run all tests with a single command:

```bash
guitarprotool --test-mode
```

The test fixtures are included in the repository, so tests run immediately after checkout.

## Structure

Each song has its own directory with:
- `input.gp` - Original Guitar Pro file without audio
- `reference.gp` - Manually synchronized reference file (created in GP8)
- `youtube_url.txt` - YouTube URL used for audio (one URL per line)
- `notes.md` - Description of test case and expected behavior

## Included Test Cases

### simple_song (Nirvana - In Bloom)
- Music starts on first beat (no intro)
- Expected: high accuracy out of the box

### complex_intro (Air - La Femme d'Argent)
- Ambient intro before bass enters
- Tests bass isolation and intro alignment
- Reference has manually adjusted sync points

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
6. Commit all files to git
