# Guitar Pro Audio Injection Tool

Automate the workflow of downloading YouTube audio, injecting it into Guitar Pro files, and creating sync points for playback alignment.

## Supported Formats

| Format | Extension | Support |
|--------|-----------|---------|
| Guitar Pro 8 | `.gp` | Full support (native) |
| Guitar Pro 6/7 | `.gpx` | Full support (converts to GP8) |
| Guitar Pro 5 | `.gp5` | Not yet supported* |
| Guitar Pro 4 | `.gp4` | Not yet supported* |
| Guitar Pro 3 | `.gp3` | Not yet supported* |

*GP3/GP4/GP5 files can be opened in Guitar Pro 8 and saved as `.gp` format for use with this tool.

## Features

- **Multi-format support**: Works with GP8 (.gp) and GPX (.gpx) files
- Download audio from YouTube using yt-dlp
- Convert audio to MP3 192kbps for Guitar Pro compatibility
- Automatic BPM and beat detection using librosa
- Adaptive tempo sync for accurate playback alignment
- **AI-powered bass isolation** (optional): Better sync for songs with ambient intros
- Interactive CLI interface with beautiful terminal UI
- Extract, modify, and repackage Guitar Pro files safely

## Installation

### System Requirements

You need to install ffmpeg first:

**Ubuntu/Debian:**
```bash
sudo apt-get install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

**Windows:**
- Download ffmpeg from [ffmpeg.org](https://ffmpeg.org/)

**Python Version:** Python 3.11 or 3.12 recommended. Python 3.13+ may have compatibility issues with some audio libraries.

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

### Optional: Bass Isolation

For songs with ambient intros or complex arrangements, bass isolation uses AI to detect where the bass actually starts, improving sync accuracy:

```bash
pip install "guitarprotool[bass-isolation]"

# Or for local development:
pip install -e ".[bass-isolation]"
```

This installs PyTorch and Demucs (~2GB). Requires:
- ~4GB disk space
- GPU recommended (CUDA) but works on CPU
- First run downloads the model (~1.5GB)

When installed, bass isolation runs automatically during audio processing.

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
1. Select a Guitar Pro file (.gp or .gpx)
2. Provide a YouTube URL or local audio file
3. Review detected BPM (option to override)
4. Process and generate output file (always saved as .gp)

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

### Capturing Full Output

To capture all terminal output (including progress bars) to a file:

```bash
guitarprotool --test-mode 2>&1 | tee full_output.txt
```

## Tech Stack

- **yt-dlp**: YouTube audio download
- **pydub**: Audio processing and conversion
- **librosa**: BPM and beat detection
- **lxml**: XML parsing and modification
- **rich**: Beautiful terminal UI
- **questionary**: Interactive prompts
- **loguru**: Logging
- **Demucs** (optional): AI-powered bass isolation for improved sync

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

- Full support for Guitar Pro 8 (.gp) files
- Full support for Guitar Pro 6/7 (.gpx) files (converted to GP8 on output)
- GP3/GP4/GP5 support planned for future release

## Contributing

Contributions welcome! Please feel free to submit issues or pull requests.

## License

MIT License

## Acknowledgments

- Built for automating bass tab practice with Guitar Pro
- Uses librosa for accurate beat detection with adaptive tempo sync
- Inspired by the need to quickly add backing tracks to existing tabs
