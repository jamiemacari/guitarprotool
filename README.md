# Guitar Pro 8 Audio Injection Tool

Automate the workflow of downloading YouTube audio, injecting it into Guitar Pro 8 (.gp) files, and creating sync points for playback alignment.

## Features

- Download audio from YouTube using yt-dlp
- Convert audio to MP3 192kbps for Guitar Pro compatibility
- Automatic BPM and beat detection using aubio
- Generate sync points for accurate playback alignment
- Interactive CLI interface with beautiful terminal UI
- Extract, modify, and repackage Guitar Pro 8 files safely

## Installation

### System Requirements

You need to install system dependencies first:

**Ubuntu/Debian:**
```bash
sudo apt-get install ffmpeg libaubio-dev aubio-tools
```

**macOS:**
```bash
brew install ffmpeg aubio
```

**Windows:**
- Download ffmpeg from [ffmpeg.org](https://ffmpeg.org/)
- For aubio: `pip install aubio` should work, or use conda

### Python Package

```bash
# Clone the repository
git clone <repository-url>
cd guitarprotool

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Or install in development mode
pip install -e .
```

## Usage

### Interactive CLI

Run the tool with:

```bash
python -m guitarprotool
```

Or if installed:

```bash
guitarprotool
```

Follow the interactive prompts to:
1. Select a Guitar Pro 8 (.gp) file
2. Provide a YouTube URL or local audio file
3. Review detected BPM (option to override)
4. Process and generate output file

### Output

The tool creates a new file: `[original]_with_audio.gp` containing:
- Your original tab
- Injected audio track
- Automatically calculated sync points

## How It Works

1. **Extract**: Treats .gp file as ZIP archive and extracts contents
2. **Download**: Downloads audio from YouTube and converts to MP3 192kbps
3. **Detect**: Analyzes audio to detect BPM and beat positions
4. **Sync**: Calculates sync points matching GP timeline with audio
5. **Inject**: Modifies score.gpif XML to add AudioTrack element
6. **Repackage**: Creates new .gp file with audio and sync points

## Tech Stack

- **yt-dlp**: YouTube audio download
- **pydub**: Audio processing and conversion
- **aubio**: BPM and beat detection (lightweight, fast)
- **lxml**: XML parsing and modification
- **rich**: Beautiful terminal UI
- **questionary**: Interactive prompts
- **loguru**: Logging

## Development

### Running Tests

```bash
pytest
```

### Code Formatting

```bash
black src/ tests/
ruff check src/ tests/
```

### Type Checking

```bash
mypy src/
```

## Project Status

Currently in active development (v0.1.0).

Tested with Guitar Pro 8 files. Compatibility with earlier GP versions not guaranteed.

## Contributing

Contributions welcome! Please feel free to submit issues or pull requests.

## License

MIT License

## Acknowledgments

- Built for automating bass tab practice with Guitar Pro 8
- Uses aubio for lightweight, accurate beat detection
- Inspired by the need to quickly add backing tracks to existing tabs
