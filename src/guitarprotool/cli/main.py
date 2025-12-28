"""Main CLI module for Guitar Pro Audio Injection Tool.

Provides an interactive command-line interface for:
- Selecting Guitar Pro files
- Downloading/converting audio from YouTube or local files
- Detecting BPM and beat positions
- Injecting audio with sync points into GP files

Also supports non-interactive mode via command-line arguments.
"""

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import questionary
from questionary import Style
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from loguru import logger

from guitarprotool import __version__
from guitarprotool.core.gp_file import GPFile
from guitarprotool.core.format_handler import (
    GPFileHandler,
    GPFormat,
    get_supported_extensions,
    is_supported_format,
)
from guitarprotool.core.beat_detector import BeatDetector, BeatInfo, SyncResult
from guitarprotool.core.drift_analyzer import DriftAnalyzer, DriftReport, DriftSeverity
from guitarprotool.core.xml_modifier import (
    XMLModifier,
    SyncPoint,
    AssetInfo,
    BackingTrackConfig,
)
from guitarprotool.utils.exceptions import (
    GuitarProToolError,
    AudioProcessingError,
    BeatDetectionError,
    FormatConversionError,
)
from guitarprotool.core.sync_comparator import SyncComparator

# Try to import AudioProcessor - may fail on Python 3.14 due to pydub/audioop issue
try:
    from guitarprotool.core.audio_processor import AudioProcessor, AudioInfo

    AUDIO_PROCESSOR_AVAILABLE = True
except ImportError as e:
    AudioProcessor = None  # type: ignore
    AudioInfo = None  # type: ignore
    AUDIO_PROCESSOR_AVAILABLE = False
    logger.warning(f"AudioProcessor not available: {e}")

# Try to import BassIsolator - requires optional torch/demucs dependencies
try:
    from guitarprotool.core.bass_isolator import BassIsolator, IsolationResult

    BASS_ISOLATION_AVAILABLE = BassIsolator.is_available()
except ImportError:
    BassIsolator = None  # type: ignore
    IsolationResult = None  # type: ignore
    BASS_ISOLATION_AVAILABLE = False
    logger.debug("BassIsolator not available (optional dependency)")

# Rich console for styled output (record=True enables session capture)
console = Console(record=True)

# Custom questionary style
custom_style = Style(
    [
        ("qmark", "fg:cyan bold"),
        ("question", "bold"),
        ("answer", "fg:cyan"),
        ("pointer", "fg:cyan bold"),
        ("highlighted", "fg:cyan"),
        ("selected", "fg:green"),
    ]
)


def print_banner():
    """Display application banner."""
    supported = ", ".join(get_supported_extensions())
    banner = """
[bold cyan]Guitar Pro Audio Injection Tool[/bold cyan]
[dim]v{version}[/dim]

Inject YouTube audio into Guitar Pro files with automatic sync points.
[dim]Supports: {supported}[/dim]
    """.format(
        version=__version__,
        supported=supported,
    )
    console.print(Panel(banner.strip(), border_style="cyan"))


def parse_args() -> Optional[argparse.Namespace]:
    """Parse command-line arguments for non-interactive mode.

    Returns:
        Namespace with arguments if any provided, None for interactive mode.
    """
    parser = argparse.ArgumentParser(
        description="Guitar Pro Audio Injection Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode (default)
  guitarprotool

  # Run all test cases automatically
  guitarprotool --test-mode

  # Non-interactive with YouTube URL
  guitarprotool -i song.gp -y "https://youtube.com/watch?v=..." -o output.gp

  # Compare output to reference file
  guitarprotool -i song.gp -y "URL" -o output.gp --compare reference.gp
        """,
    )
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="Run all configured test cases from tests/fixtures/",
    )
    parser.add_argument(
        "-i", "--input", type=Path, metavar="FILE", help="Input GP file path"
    )
    parser.add_argument(
        "-y", "--youtube-url", type=str, metavar="URL", help="YouTube URL for audio"
    )
    parser.add_argument(
        "--local-audio", type=Path, metavar="FILE", help="Local audio file path"
    )
    parser.add_argument(
        "-o", "--output", type=Path, metavar="FILE", help="Output GP file path"
    )
    parser.add_argument(
        "-n",
        "--track-name",
        type=str,
        default="Audio Track",
        help="Track name in Guitar Pro (default: Audio Track)",
    )
    parser.add_argument(
        "--compare",
        type=Path,
        metavar="FILE",
        help="Compare output to reference file and print report",
    )
    parser.add_argument(
        "--quiet", action="store_true", help="Suppress non-essential output"
    )

    args = parser.parse_args()

    # Test mode takes priority
    if args.test_mode:
        return args

    # If no input provided, return None for interactive mode
    if args.input is None:
        return None

    # Validate required arguments for non-interactive mode
    if not (args.youtube_url or args.local_audio):
        parser.error("Either --youtube-url or --local-audio is required with --input")

    if args.youtube_url and args.local_audio:
        parser.error("Cannot specify both --youtube-url and --local-audio")

    # Validate input file exists
    if not args.input.exists():
        parser.error(f"Input file not found: {args.input}")

    # Validate input format
    if not is_supported_format(args.input):
        parser.error(
            f"Unsupported file format: {args.input.suffix}. "
            f"Supported: {', '.join(get_supported_extensions())}"
        )

    # Validate local audio exists
    if args.local_audio and not args.local_audio.exists():
        parser.error(f"Audio file not found: {args.local_audio}")

    # Default output path if not specified
    if args.output is None:
        args.output = args.input.parent / f"{args.input.stem}_with_audio.gp"

    # Validate compare file exists
    if args.compare and not args.compare.exists():
        parser.error(f"Reference file not found: {args.compare}")

    return args


def get_test_fixtures_dir() -> Path:
    """Get the path to the test fixtures directory."""
    # Try relative to this file first (installed package)
    cli_dir = Path(__file__).parent
    project_root = cli_dir.parent.parent.parent
    fixtures_dir = project_root / "tests" / "fixtures"

    if fixtures_dir.exists():
        return fixtures_dir

    # Try current working directory
    cwd_fixtures = Path.cwd() / "tests" / "fixtures"
    if cwd_fixtures.exists():
        return cwd_fixtures

    raise FileNotFoundError(
        "Test fixtures directory not found. "
        "Run from project root or ensure tests/fixtures/ exists."
    )


def run_test_mode() -> int:
    """Run all configured test cases from tests/fixtures/.

    Returns:
        Exit code (0 = all passed, 1 = some failed)
    """
    console.print()
    console.print(Panel("[bold]Test Mode[/bold]\nRunning all configured test cases...", border_style="cyan"))
    console.print()

    try:
        fixtures_dir = get_test_fixtures_dir()
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        return 1

    # Find all test case directories
    test_cases = []
    for case_dir in sorted(fixtures_dir.iterdir()):
        if not case_dir.is_dir():
            continue
        if case_dir.name.startswith("."):
            continue

        # Look for input file
        input_file = case_dir / "input.gp"
        if not input_file.exists():
            input_file = case_dir / "input.gpx"
        if not input_file.exists():
            continue

        # Look for YouTube URL
        url_file = case_dir / "youtube_url.txt"
        if not url_file.exists():
            console.print(f"[yellow]Skipping {case_dir.name}:[/yellow] No youtube_url.txt")
            continue

        youtube_url = url_file.read_text().strip()
        if not youtube_url:
            console.print(f"[yellow]Skipping {case_dir.name}:[/yellow] Empty youtube_url.txt")
            continue

        # Reference file (optional)
        reference_file = case_dir / "reference.gp"
        if not reference_file.exists():
            reference_file = None

        test_cases.append({
            "name": case_dir.name,
            "input": input_file,
            "youtube_url": youtube_url,
            "reference": reference_file,
        })

    if not test_cases:
        console.print("[yellow]No test cases found.[/yellow]")
        console.print()
        console.print("To set up test cases, add files to tests/fixtures/:")
        console.print("  tests/fixtures/<song_name>/input.gp")
        console.print("  tests/fixtures/<song_name>/youtube_url.txt")
        console.print("  tests/fixtures/<song_name>/reference.gp (optional)")
        return 1

    console.print(f"Found [cyan]{len(test_cases)}[/cyan] test case(s):")
    for tc in test_cases:
        ref_status = "[green]+ reference[/green]" if tc["reference"] else "[dim]no reference[/dim]"
        console.print(f"  - {tc['name']} {ref_status}")
    console.print()

    # Run each test case
    results = []
    for tc in test_cases:
        console.print(f"[bold]{'='*60}[/bold]")
        console.print(f"[bold]Test: {tc['name']}[/bold]")
        console.print(f"[bold]{'='*60}[/bold]")
        console.print()

        # Create output path in temp directory
        import tempfile
        output_dir = Path(tempfile.gettempdir()) / "guitarprotool_tests"
        output_dir.mkdir(exist_ok=True)
        output_path = output_dir / f"{tc['name']}_output.gp"

        # Create args namespace
        args = argparse.Namespace(
            input=tc["input"],
            youtube_url=tc["youtube_url"],
            local_audio=None,
            output=output_path,
            track_name="Audio Track",
            compare=tc["reference"],
            quiet=False,
            test_mode=True,
        )

        # Run pipeline
        exit_code = run_pipeline_noninteractive(args)

        results.append({
            "name": tc["name"],
            "passed": exit_code == 0,
            "output": output_path,
        })

        console.print()

    # Summary
    console.print(f"[bold]{'='*60}[/bold]")
    console.print("[bold]TEST SUMMARY[/bold]")
    console.print(f"[bold]{'='*60}[/bold]")
    console.print()

    passed = sum(1 for r in results if r["passed"])
    failed = len(results) - passed

    for r in results:
        status = "[green]PASS[/green]" if r["passed"] else "[red]FAIL[/red]"
        console.print(f"  {status} {r['name']}")
        console.print(f"       Output: {r['output']}")

    console.print()
    if failed == 0:
        console.print(f"[bold green]All {passed} test(s) passed![/bold green]")
    else:
        console.print(f"[bold yellow]{passed} passed, {failed} failed[/bold yellow]")

    console.print()
    console.print("[dim]Open output files in Guitar Pro to verify audio sync.[/dim]")

    return 0 if failed == 0 else 1


def get_gp_file_path() -> Optional[Path]:
    """Prompt user for Guitar Pro file path.

    Returns:
        Path to Guitar Pro file or None if cancelled
    """
    supported = ", ".join(get_supported_extensions())
    result = questionary.path(
        f"Select Guitar Pro file ({supported}):",
        only_directories=False,
        style=custom_style,
    ).ask()

    if not result:
        return None

    path = Path(result).expanduser().resolve()

    if not path.exists():
        console.print(f"[red]Error:[/red] File not found: {path}")
        return None

    if not is_supported_format(path):
        console.print(
            f"[red]Error:[/red] Unsupported format: {path.suffix}\n"
            f"[dim]Supported formats: {supported}[/dim]"
        )
        return None

    return path


def get_audio_source() -> tuple[str, str]:
    """Prompt user for audio source.

    Returns:
        Tuple of (source_type, source_value) where source_type is 'youtube' or 'local'
    """
    source_type = questionary.select(
        "Select audio source:",
        choices=[
            questionary.Choice("YouTube URL", value="youtube"),
            questionary.Choice("Local audio file", value="local"),
        ],
        style=custom_style,
    ).ask()

    if source_type == "youtube":
        url = questionary.text(
            "Enter YouTube URL:",
            style=custom_style,
        ).ask()
        return ("youtube", url or "")
    else:
        path = questionary.path(
            "Select audio file:",
            only_directories=False,
            style=custom_style,
        ).ask()
        return ("local", path or "")


def get_track_name(default: str = "Audio Track") -> str:
    """Prompt user for track name.

    Args:
        default: Default track name

    Returns:
        Track name
    """
    return (
        questionary.text(
            "Track name (shown in Guitar Pro):",
            default=default,
            style=custom_style,
        ).ask()
        or default
    )


def get_output_path(input_path: Path) -> Path:
    """Prompt user for output file path.

    Args:
        input_path: Original .gp file path

    Returns:
        Output path for modified file
    """
    default_output = input_path.parent / f"{input_path.stem}_with_audio.gp"

    result = questionary.path(
        "Save modified file as:",
        default=str(default_output),
        style=custom_style,
    ).ask()

    if not result:
        return default_output

    output_path = Path(result).expanduser().resolve()

    # Ensure .gp extension
    if output_path.suffix.lower() != ".gp":
        output_path = output_path.with_suffix(".gp")

    return output_path


def confirm_overwrite(path: Path) -> bool:
    """Confirm overwriting existing file.

    Args:
        path: Path to potentially overwrite

    Returns:
        True if user confirms, False otherwise
    """
    if not path.exists():
        return True

    return (
        questionary.confirm(
            f"File {path.name} already exists. Overwrite?",
            default=False,
            style=custom_style,
        ).ask()
        or False
    )


def get_troubleshooting_dir() -> Path:
    """Get the directory for saving troubleshooting copies.

    Creates a timestamped subdirectory under 'files/' in the project root.

    Returns:
        Path to the troubleshooting directory
    """
    # Use current working directory's 'files' folder
    base_dir = Path.cwd() / "files"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    troubleshoot_dir = base_dir / f"run_{timestamp}"
    troubleshoot_dir.mkdir(parents=True, exist_ok=True)
    return troubleshoot_dir


def save_troubleshooting_copies(
    input_gp_path: Path,
    output_gp_path: Path,
    audio_path: Path,
    troubleshoot_dir: Path,
) -> tuple[Path, Path, Path]:
    """Save copies of the input GP, output GP, and MP3 for troubleshooting.

    Args:
        input_gp_path: Path to the original input GP file
        output_gp_path: Path to the final GP file
        audio_path: Path to the processed MP3 file
        troubleshoot_dir: Directory to save copies to

    Returns:
        Tuple of (input_copy_path, output_copy_path, mp3_copy_path)
    """
    # Use descriptive names for clarity in run folder
    input_copy_path = troubleshoot_dir / f"input_{input_gp_path.name}"
    output_copy_path = troubleshoot_dir / output_gp_path.name
    mp3_copy_path = troubleshoot_dir / audio_path.name

    shutil.copy2(input_gp_path, input_copy_path)
    shutil.copy2(output_gp_path, output_copy_path)
    shutil.copy2(audio_path, mp3_copy_path)

    return input_copy_path, output_copy_path, mp3_copy_path


def save_session_log(troubleshoot_dir: Path) -> tuple[Path, Path]:
    """Save TUI session output to text and HTML files.

    Args:
        troubleshoot_dir: Directory to save session logs to

    Returns:
        Tuple of (txt_path, html_path)
    """
    txt_path = troubleshoot_dir / "session_log.txt"
    html_path = troubleshoot_dir / "session_log.html"

    console.save_text(str(txt_path))
    console.save_html(str(html_path))

    return txt_path, html_path


def process_audio(
    source_type: str,
    source_value: str,
    output_dir: Path,
    progress: Progress,
):
    """Download/convert audio with progress display.

    Args:
        source_type: 'youtube' or 'local'
        source_value: URL or file path
        output_dir: Directory to save processed audio
        progress: Rich progress instance

    Returns:
        AudioInfo or None on failure
    """
    if not AUDIO_PROCESSOR_AVAILABLE:
        console.print(
            "[red]Error:[/red] Audio processing not available. "
            "This is likely due to Python 3.14 compatibility issues with pydub.\n"
            "Please use Python 3.10-3.13 for full functionality."
        )
        return None

    task_id = progress.add_task("[cyan]Processing audio...", total=100)

    def update_progress(percent: float, status: str):
        progress.update(task_id, completed=percent * 100, description=f"[cyan]{status}")

    try:
        processor = AudioProcessor(
            output_dir=output_dir,
            progress_callback=update_progress,
        )

        if source_type == "youtube":
            audio_info = processor.process_youtube(source_value)
        else:
            audio_info = processor.process_local(Path(source_value))

        progress.update(task_id, completed=100, description="[green]Audio processed")
        return audio_info

    except Exception as e:
        progress.update(task_id, description=f"[red]Failed: {e}")
        logger.error(f"Audio processing failed: {e}")
        return None


def isolate_bass(
    audio_path: Path,
    output_dir: Path,
    progress: Progress,
) -> Optional[Path]:
    """Isolate bass from audio for improved beat detection.

    Args:
        audio_path: Path to audio file
        output_dir: Directory to save isolated audio
        progress: Rich progress instance

    Returns:
        Path to isolated bass audio or None if isolation fails/unavailable
    """
    if not BASS_ISOLATION_AVAILABLE:
        return None

    task_id = progress.add_task("[cyan]Isolating bass (AI)...", total=100)

    def update_progress(percent: float, status: str):
        progress.update(task_id, completed=percent * 100, description=f"[cyan]{status}")

    try:
        isolator = BassIsolator(
            output_dir=output_dir,
            progress_callback=update_progress,
        )

        result = isolator.isolate(audio_path)

        if result.success:
            progress.update(
                task_id,
                completed=100,
                description=f"[green]Bass isolated ({result.processing_time:.1f}s)",
            )
            return result.bass_path
        else:
            progress.update(
                task_id,
                completed=100,
                description=f"[yellow]Isolation failed: {result.error_message}",
            )
            return None

    except Exception as e:
        progress.update(task_id, description=f"[yellow]Isolation failed: {e}")
        logger.warning(f"Bass isolation failed, using full mix: {e}")
        return None


def detect_beats(
    audio_path: Path,
    progress: Progress,
) -> Optional[BeatInfo]:
    """Detect BPM and beats with progress display.

    Args:
        audio_path: Path to audio file
        progress: Rich progress instance

    Returns:
        BeatInfo or None on failure
    """
    task_id = progress.add_task("[cyan]Detecting beats...", total=100)

    def update_progress(percent: float, status: str):
        progress.update(task_id, completed=percent * 100, description=f"[cyan]{status}")

    try:
        detector = BeatDetector()
        beat_info = detector.analyze(audio_path, progress_callback=update_progress)

        progress.update(task_id, completed=100, description="[green]Beat detection complete")
        return beat_info

    except BeatDetectionError as e:
        progress.update(task_id, description=f"[red]Failed: {e}")
        logger.error(f"Beat detection failed: {e}")
        return None


def display_beat_info(beat_info: BeatInfo):
    """Display detected beat information."""
    table = Table(title="Beat Detection Results", border_style="cyan")
    table.add_column("Property", style="dim")
    table.add_column("Value", style="cyan")

    table.add_row("Detected BPM", f"{beat_info.bpm:.1f}")
    table.add_row("Total Beats", str(len(beat_info.beat_times)))
    table.add_row("Confidence", f"{beat_info.confidence:.0%}")

    if beat_info.beat_times:
        duration = beat_info.beat_times[-1]
        table.add_row("Duration", f"{duration:.1f} seconds")

    console.print(table)


def display_drift_report(drift_report: DriftReport):
    """Display tempo drift analysis results."""
    # Summary panel
    summary_lines = drift_report.get_summary_lines()
    summary_text = "\n".join(summary_lines)
    console.print(Panel(summary_text, title="Tempo Drift Analysis", border_style="yellow"))

    # If significant drift found, show detail table
    if drift_report.bars_with_significant_drift:
        table = Table(title="Bars with Significant Drift", border_style="yellow")
        table.add_column("Bar", style="dim")
        table.add_column("Local Tempo", style="cyan")
        table.add_column("Tab Tempo", style="dim")
        table.add_column("Drift", style="yellow")
        table.add_column("Severity", style="red")

        # Show up to 10 bars with significant drift
        for bar_num in drift_report.bars_with_significant_drift[:10]:
            drift_info = next(
                (d for d in drift_report.bar_drifts if d.bar == bar_num),
                None,
            )
            if drift_info:
                severity_color = {
                    DriftSeverity.MODERATE: "yellow",
                    DriftSeverity.SIGNIFICANT: "orange1",
                    DriftSeverity.SEVERE: "red",
                }.get(drift_info.severity, "white")

                table.add_row(
                    str(bar_num),
                    f"{drift_info.local_tempo:.1f}",
                    f"{drift_info.original_tempo:.1f}",
                    f"{drift_info.drift_percent:+.2f}%",
                    f"[{severity_color}]{drift_info.severity.value}[/{severity_color}]",
                )

        console.print(table)

        if len(drift_report.bars_with_significant_drift) > 10:
            remaining = len(drift_report.bars_with_significant_drift) - 10
            console.print(f"[dim]... and {remaining} more bars with drift[/dim]")


def run_pipeline():
    """Execute the full audio injection pipeline."""
    console.print()

    # Step 1: Get GP file
    console.print("[bold]Step 1:[/bold] Select Guitar Pro file")
    gp_path = get_gp_file_path()
    if not gp_path:
        console.print("[yellow]Cancelled.[/yellow]")
        return

    console.print(f"  [dim]Selected:[/dim] {gp_path.name}")
    console.print()

    # Step 2: Get audio source
    console.print("[bold]Step 2:[/bold] Select audio source")
    source_type, source_value = get_audio_source()
    if not source_value:
        console.print("[yellow]Cancelled.[/yellow]")
        return

    console.print(
        f"  [dim]Source:[/dim] {source_value[:60]}{'...' if len(source_value) > 60 else ''}"
    )
    console.print()

    # Step 3: Get track name
    console.print("[bold]Step 3:[/bold] Configure audio track")
    track_name = get_track_name()
    console.print(f"  [dim]Track name:[/dim] {track_name}")
    console.print()

    # Step 4: Get output path
    console.print("[bold]Step 4:[/bold] Output file")
    output_path = get_output_path(gp_path)
    if not confirm_overwrite(output_path):
        console.print("[yellow]Cancelled.[/yellow]")
        return

    console.print(f"  [dim]Output:[/dim] {output_path.name}")
    console.print()

    # Step 5: Run pipeline with progress
    console.print("[bold]Step 5:[/bold] Processing...")
    console.print()

    handler = None

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:

            # Initialize file handler and prepare for audio injection
            handler = GPFileHandler(gp_path)
            original_format = handler.format

            if original_format != GPFormat.GP8:
                extract_task = progress.add_task(
                    f"[cyan]Converting {original_format.name} to GP8...", total=None
                )
            else:
                extract_task = progress.add_task("[cyan]Extracting GP file...", total=None)

            temp_dir = handler.prepare_for_audio_injection()

            if original_format != GPFormat.GP8:
                progress.update(
                    extract_task,
                    completed=100,
                    total=100,
                    description=f"[green]Converted from {original_format.name} to GP8",
                )
            else:
                progress.update(
                    extract_task, completed=100, total=100, description="[green]GP file extracted"
                )

            # Process audio
            audio_dir = handler.get_audio_dir()
            audio_info = process_audio(source_type, source_value, audio_dir, progress)
            if not audio_info:
                raise AudioProcessingError("Failed to process audio")

            # Bass isolation for finding bass start time (used for intro alignment)
            # Beat detection uses ORIGINAL audio for accurate sync point timing
            bass_isolated = False
            bass_first_beat_time = None

            if BASS_ISOLATION_AVAILABLE:
                isolated_bass_path = isolate_bass(
                    audio_info.file_path,
                    audio_dir,
                    progress,
                )
                if isolated_bass_path:
                    bass_isolated = True
                    # Detect beats on isolated bass to find where bass starts
                    bass_beat_info = detect_beats(isolated_bass_path, progress)
                    if bass_beat_info and bass_beat_info.beat_times:
                        bass_first_beat_time = bass_beat_info.beat_times[0]
                        logger.info(f"Bass start detected at: {bass_first_beat_time:.3f}s")
            else:
                # Show one-time info about bass isolation availability
                progress.console.print(
                    "[dim]Tip: Install bass isolation for better sync with ambient intros:[/dim]\n"
                    "[dim]    pip install guitarprotool[bass-isolation][/dim]"
                )

            # Detect beats on ORIGINAL audio for accurate sync point timing
            # (Bass isolation is only used to find where bass starts, not for sync)
            beat_info = detect_beats(audio_info.file_path, progress)
            if not beat_info:
                raise BeatDetectionError("Failed to detect beats")

            # Get original tempo from GP file
            gpif_path = handler.get_gpif_path()
            modifier = XMLModifier(gpif_path)
            modifier.load()
            original_tempo = modifier.get_original_tempo()

            # Fall back to detected BPM if original tempo not found in GP file
            if original_tempo is None:
                original_tempo = beat_info.bpm
                logger.info(
                    f"No tempo found in GP file, using detected BPM: {original_tempo:.1f}"
                )

            # Find where notes start in the tab (for bass isolation alignment)
            tab_start_bar = 0
            if bass_isolated and bass_first_beat_time is not None:
                tab_start_bar = modifier.get_first_note_bar()
                if tab_start_bar > 0:
                    # Find the beat in original audio closest to bass start time
                    # This aligns original audio beats with where bass actually starts
                    min_diff = float('inf')
                    bass_beat_index = 0
                    for i, bt in enumerate(beat_info.beat_times):
                        diff = abs(bt - bass_first_beat_time)
                        if diff < min_diff:
                            min_diff = diff
                            bass_beat_index = i

                    # Shift beat times so that bass_beat_index becomes beat 0
                    # This makes the first beat align with where bass starts
                    original_first_beat = beat_info.beat_times[0]
                    aligned_beat_times = [
                        bt - beat_info.beat_times[bass_beat_index] + bass_first_beat_time
                        for bt in beat_info.beat_times[bass_beat_index:]
                    ]
                    beat_info = BeatInfo(
                        bpm=beat_info.bpm,
                        beat_times=aligned_beat_times,
                        confidence=beat_info.confidence,
                    )

                    logger.info(
                        f"Tab has {tab_start_bar} intro bars before notes start "
                        f"(first note at bar {tab_start_bar + 1}). "
                        f"Aligned to bass start at {bass_first_beat_time:.3f}s "
                        f"(shifted from beat {bass_beat_index})"
                    )

            # Correct for double/half-time detection
            original_detected_bpm = beat_info.bpm
            beat_info = BeatDetector.correct_tempo_multiple(beat_info, original_tempo)
            tempo_corrected = beat_info.bpm != original_detected_bpm

            # Display beat info
            progress.stop()
            console.print()
            display_beat_info(beat_info)

            if tempo_corrected:
                console.print(
                    f"[yellow]Note:[/yellow] Tempo corrected from {original_detected_bpm:.1f} "
                    f"to {beat_info.bpm:.1f} BPM (reference tempo: {original_tempo:.1f})"
                )

            if tab_start_bar > 0:
                console.print(
                    f"[cyan]Tab alignment:[/cyan] First notes at bar {tab_start_bar + 1} "
                    f"(skipping {tab_start_bar} intro bar{'s' if tab_start_bar > 1 else ''})"
                )

            console.print()

            # Restart progress for remaining tasks
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console,
            ) as progress2:

                # Analyze tempo drift
                drift_task = progress2.add_task("[cyan]Analyzing tempo drift...", total=None)
                bar_count = modifier.get_bar_count()
                max_bars = bar_count if bar_count > 0 else None

                # Create drift analyzer and generate report
                try:
                    analyzer = DriftAnalyzer(
                        beat_times=beat_info.beat_times,
                        original_tempo=original_tempo,
                        beats_per_bar=4,
                        tab_start_bar=tab_start_bar,
                    )
                    drift_report = analyzer.analyze(max_bars=max_bars)
                    # Add tempo correction info to report
                    drift_report.tempo_corrected = tempo_corrected
                    drift_report.original_detected_bpm = original_detected_bpm
                    drift_report.corrected_bpm = beat_info.bpm
                    has_drift_report = True
                except Exception as e:
                    logger.warning(f"Drift analysis failed: {e}")
                    drift_report = None
                    has_drift_report = False

                progress2.update(
                    drift_task,
                    completed=100,
                    total=100,
                    description="[green]Drift analysis complete",
                )

                # Generate adaptive sync points
                sync_task = progress2.add_task("[cyan]Generating sync points...", total=None)
                detector = BeatDetector()
                sync_result = detector.generate_sync_points(
                    beat_info,
                    original_tempo=original_tempo,
                    sync_interval=16,
                    max_bars=max_bars,
                    adaptive=True,  # Use adaptive tempo sync
                    tab_start_bar=tab_start_bar,  # Align with first note bar
                )

                # Convert to XML modifier format
                sync_points = [
                    SyncPoint(
                        bar=sp.bar,
                        frame_offset=sp.frame_offset,
                        modified_tempo=sp.modified_tempo,
                        original_tempo=sp.original_tempo,
                    )
                    for sp in sync_result.sync_points
                ]
                progress2.update(
                    sync_task,
                    completed=100,
                    total=100,
                    description=f"[green]Generated {len(sync_points)} adaptive sync points",
                )

            # Create troubleshooting directory early so all artifacts go there
            troubleshoot_dir = get_troubleshooting_dir()

            # Display drift report outside progress context and write to file
            drift_report_path = None
            debug_beats_path = None
            if has_drift_report and drift_report:
                # Add sync point bar numbers to the report
                drift_report.bars_with_sync_points = [sp.bar for sp in sync_result.sync_points]

                console.print()
                display_drift_report(drift_report)

                # Write drift report to run folder
                drift_report_path = troubleshoot_dir / "drift_report.txt"
                drift_report.write_to_file(str(drift_report_path))
                console.print(f"[dim]Drift report saved to: {drift_report_path}[/dim]")

                # Write debug beat data to run folder
                debug_beats_path = troubleshoot_dir / "debug_beats.txt"
                analyzer.write_debug_beats(str(debug_beats_path))
                console.print(f"[dim]Debug beat data saved to: {debug_beats_path}[/dim]")
                console.print()

            # Continue with XML injection
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console,
            ) as progress3:

                # Inject into XML
                xml_task = progress3.add_task("[cyan]Modifying GP file...", total=None)

                # Create asset info
                asset_info = AssetInfo(
                    asset_id=0,
                    uuid=audio_info.uuid,
                    original_file_path=str(audio_info.file_path),
                )

                # Create backing track config with frame_padding for audio alignment
                # frame_padding is negative to skip intro/silence before the first beat
                track_config = BackingTrackConfig(
                    name=track_name,
                    short_name=track_name[:8] if len(track_name) > 8 else track_name,
                    asset_id=0,
                    frame_padding=sync_result.frame_padding,
                )

                # Inject elements
                modifier.inject_asset(asset_info)
                modifier.inject_backing_track(track_config)
                modifier.inject_sync_points(sync_points)
                modifier.save()

                # Copy audio file to proper location
                target_audio_path = temp_dir / asset_info.embedded_file_path
                target_audio_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(audio_info.file_path, target_audio_path)

                progress3.update(
                    xml_task, completed=100, total=100, description="[green]GP file modified"
                )

                # Repackage
                repack_task = progress3.add_task("[cyan]Repackaging...", total=None)
                handler.save(output_path)
                progress3.update(
                    repack_task, completed=100, total=100, description="[green]File saved"
                )

        # Save troubleshooting copies (input, output, and audio)
        input_copy, output_copy, mp3_copy = save_troubleshooting_copies(
            gp_path,
            output_path,
            audio_info.file_path,
            troubleshoot_dir,
        )

        # Save session log (both .txt and .html formats)
        txt_log, html_log = save_session_log(troubleshoot_dir)

        # Success!
        console.print()
        bass_info = "Bass isolation: Yes (AI-enhanced)" if bass_isolated else "Bass isolation: No"
        console.print(
            Panel(
                f"[bold green]Success![/bold green]\n\n"
                f"Modified file saved to:\n[cyan]{output_path}[/cyan]\n\n"
                f"[dim]Detected BPM: {beat_info.bpm:.1f}\n"
                f"Sync points: {len(sync_points)}\n"
                f"Original tempo: {original_tempo:.1f}\n"
                f"Audio offset: {sync_result.first_beat_time:.3f}s\n"
                f"{bass_info}[/dim]\n\n"
                f"[dim]All testing artifacts saved to:\n{troubleshoot_dir}[/dim]",
                title="Complete",
                border_style="green",
            )
        )

    except FormatConversionError as e:
        console.print(f"\n[red]Format conversion error:[/red] {e}")
        logger.exception("Format conversion failed")

    except GuitarProToolError as e:
        console.print(f"\n[red]Error:[/red] {e}")
        logger.exception("Pipeline failed")

    except Exception as e:
        console.print(f"\n[red]Unexpected error:[/red] {e}")
        logger.exception("Unexpected error in pipeline")

    finally:
        if handler:
            handler.cleanup()


def main_menu():
    """Display main menu and handle selection."""
    while True:
        console.print()
        choice = questionary.select(
            "What would you like to do?",
            choices=[
                questionary.Choice("Inject audio into GP file", value="inject"),
                questionary.Choice("Detect BPM from audio file", value="bpm"),
                questionary.Choice("Exit", value="exit"),
            ],
            style=custom_style,
        ).ask()

        if choice == "inject":
            run_pipeline()
        elif choice == "bpm":
            detect_bpm_only()
        elif choice == "exit" or choice is None:
            console.print("[dim]Goodbye![/dim]")
            break


def detect_bpm_only():
    """Standalone BPM detection mode."""
    console.print()
    console.print("[bold]BPM Detection[/bold]")

    path = questionary.path(
        "Select audio file:",
        only_directories=False,
        style=custom_style,
    ).ask()

    if not path:
        return

    audio_path = Path(path).expanduser().resolve()

    if not audio_path.exists():
        console.print(f"[red]File not found:[/red] {audio_path}")
        return

    console.print()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        beat_info = detect_beats(audio_path, progress)

    if beat_info:
        console.print()
        display_beat_info(beat_info)


def run_pipeline_noninteractive(args: argparse.Namespace) -> int:
    """Execute the audio injection pipeline with CLI arguments (non-interactive).

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 = success, 1 = error)
    """
    gp_path = args.input.expanduser().resolve()
    output_path = args.output.expanduser().resolve()
    track_name = args.track_name

    # Determine audio source
    if args.youtube_url:
        source_type = "youtube"
        source_value = args.youtube_url
    else:
        source_type = "local"
        source_value = str(args.local_audio.expanduser().resolve())

    if not args.quiet:
        console.print(f"[dim]Input:[/dim] {gp_path}")
        console.print(f"[dim]Audio:[/dim] {source_value[:80]}{'...' if len(source_value) > 80 else ''}")
        console.print(f"[dim]Output:[/dim] {output_path}")
        console.print()

    handler = None

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:

            # Initialize file handler and prepare for audio injection
            handler = GPFileHandler(gp_path)
            original_format = handler.format

            if original_format != GPFormat.GP8:
                extract_task = progress.add_task(
                    f"[cyan]Converting {original_format.name} to GP8...", total=None
                )
            else:
                extract_task = progress.add_task("[cyan]Extracting GP file...", total=None)

            temp_dir = handler.prepare_for_audio_injection()

            if original_format != GPFormat.GP8:
                progress.update(
                    extract_task,
                    completed=100,
                    total=100,
                    description=f"[green]Converted from {original_format.name} to GP8",
                )
            else:
                progress.update(
                    extract_task, completed=100, total=100, description="[green]GP file extracted"
                )

            # Process audio
            audio_dir = handler.get_audio_dir()
            audio_info = process_audio(source_type, source_value, audio_dir, progress)
            if not audio_info:
                raise AudioProcessingError("Failed to process audio")

            # Bass isolation for finding bass start time
            bass_isolated = False
            bass_first_beat_time = None

            if BASS_ISOLATION_AVAILABLE:
                isolated_bass_path = isolate_bass(
                    audio_info.file_path,
                    audio_dir,
                    progress,
                )
                if isolated_bass_path:
                    bass_isolated = True
                    bass_beat_info = detect_beats(isolated_bass_path, progress)
                    if bass_beat_info and bass_beat_info.beat_times:
                        bass_first_beat_time = bass_beat_info.beat_times[0]
                        logger.info(f"Bass start detected at: {bass_first_beat_time:.3f}s")

            # Detect beats on original audio
            beat_info = detect_beats(audio_info.file_path, progress)
            if not beat_info:
                raise BeatDetectionError("Failed to detect beats")

            # Get original tempo from GP file
            gpif_path = handler.get_gpif_path()
            modifier = XMLModifier(gpif_path)
            modifier.load()
            original_tempo = modifier.get_original_tempo()

            if original_tempo is None:
                original_tempo = beat_info.bpm
                logger.info(f"No tempo found in GP file, using detected BPM: {original_tempo:.1f}")

            # Find where notes start in the tab
            tab_start_bar = 0
            if bass_isolated and bass_first_beat_time is not None:
                tab_start_bar = modifier.get_first_note_bar()
                if tab_start_bar > 0:
                    min_diff = float('inf')
                    bass_beat_index = 0
                    for i, bt in enumerate(beat_info.beat_times):
                        diff = abs(bt - bass_first_beat_time)
                        if diff < min_diff:
                            min_diff = diff
                            bass_beat_index = i

                    aligned_beat_times = [
                        bt - beat_info.beat_times[bass_beat_index] + bass_first_beat_time
                        for bt in beat_info.beat_times[bass_beat_index:]
                    ]
                    beat_info = BeatInfo(
                        bpm=beat_info.bpm,
                        beat_times=aligned_beat_times,
                        confidence=beat_info.confidence,
                    )

            # Correct for double/half-time detection
            original_detected_bpm = beat_info.bpm
            beat_info = BeatDetector.correct_tempo_multiple(beat_info, original_tempo)
            tempo_corrected = beat_info.bpm != original_detected_bpm

            # Display beat info (unless quiet)
            progress.stop()
            if not args.quiet:
                console.print()
                display_beat_info(beat_info)
                if tempo_corrected:
                    console.print(
                        f"[yellow]Note:[/yellow] Tempo corrected from {original_detected_bpm:.1f} "
                        f"to {beat_info.bpm:.1f} BPM (reference tempo: {original_tempo:.1f})"
                    )
                console.print()

        # Continue with processing (new progress context)
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress2:

            # Analyze tempo drift
            drift_task = progress2.add_task("[cyan]Analyzing tempo drift...", total=None)
            bar_count = modifier.get_bar_count()
            max_bars = bar_count if bar_count > 0 else None

            try:
                analyzer = DriftAnalyzer(
                    beat_times=beat_info.beat_times,
                    original_tempo=original_tempo,
                    beats_per_bar=4,
                    tab_start_bar=tab_start_bar,
                )
                drift_report = analyzer.analyze(max_bars=max_bars)
                drift_report.tempo_corrected = tempo_corrected
                drift_report.original_detected_bpm = original_detected_bpm
                drift_report.corrected_bpm = beat_info.bpm
                has_drift_report = True
            except Exception as e:
                logger.warning(f"Drift analysis failed: {e}")
                drift_report = None
                has_drift_report = False

            progress2.update(
                drift_task,
                completed=100,
                total=100,
                description="[green]Drift analysis complete",
            )

            # Generate adaptive sync points
            sync_task = progress2.add_task("[cyan]Generating sync points...", total=None)
            detector = BeatDetector()
            sync_result = detector.generate_sync_points(
                beat_info,
                original_tempo=original_tempo,
                sync_interval=16,
                max_bars=max_bars,
                adaptive=True,
                tab_start_bar=tab_start_bar,
            )

            sync_points = [
                SyncPoint(
                    bar=sp.bar,
                    frame_offset=sp.frame_offset,
                    modified_tempo=sp.modified_tempo,
                    original_tempo=sp.original_tempo,
                )
                for sp in sync_result.sync_points
            ]
            progress2.update(
                sync_task,
                completed=100,
                total=100,
                description=f"[green]Generated {len(sync_points)} adaptive sync points",
            )

        # Create troubleshooting directory
        troubleshoot_dir = get_troubleshooting_dir()

        # Write drift report
        if has_drift_report and drift_report:
            drift_report.bars_with_sync_points = [sp.bar for sp in sync_result.sync_points]

            if not args.quiet:
                console.print()
                display_drift_report(drift_report)

            drift_report_path = troubleshoot_dir / "drift_report.txt"
            drift_report.write_to_file(str(drift_report_path))

            debug_beats_path = troubleshoot_dir / "debug_beats.txt"
            analyzer.write_debug_beats(str(debug_beats_path))

            if not args.quiet:
                console.print(f"[dim]Drift report saved to: {drift_report_path}[/dim]")
                console.print()

        # XML injection and repackaging
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress3:

            xml_task = progress3.add_task("[cyan]Modifying GP file...", total=None)

            asset_info = AssetInfo(
                asset_id=0,
                uuid=audio_info.uuid,
                original_file_path=str(audio_info.file_path),
            )

            track_config = BackingTrackConfig(
                name=track_name,
                short_name=track_name[:8] if len(track_name) > 8 else track_name,
                asset_id=0,
                frame_padding=sync_result.frame_padding,
            )

            modifier.inject_asset(asset_info)
            modifier.inject_backing_track(track_config)
            modifier.inject_sync_points(sync_points)
            modifier.save()

            target_audio_path = temp_dir / asset_info.embedded_file_path
            target_audio_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(audio_info.file_path, target_audio_path)

            progress3.update(
                xml_task, completed=100, total=100, description="[green]GP file modified"
            )

            repack_task = progress3.add_task("[cyan]Repackaging...", total=None)
            handler.save(output_path)
            progress3.update(
                repack_task, completed=100, total=100, description="[green]File saved"
            )

        # Save troubleshooting copies
        save_troubleshooting_copies(
            gp_path,
            output_path,
            audio_info.file_path,
            troubleshoot_dir,
        )
        save_session_log(troubleshoot_dir)

        # Success message
        if not args.quiet:
            console.print()
            console.print(
                Panel(
                    f"[bold green]Success![/bold green]\n\n"
                    f"Output: [cyan]{output_path}[/cyan]\n"
                    f"BPM: {beat_info.bpm:.1f} | Sync points: {len(sync_points)}",
                    title="Complete",
                    border_style="green",
                )
            )

        # Optional comparison
        if args.compare:
            console.print()
            console.print("[bold]Comparing to reference file...[/bold]")
            comparator = SyncComparator()
            result = comparator.compare(output_path, args.compare)
            console.print()
            console.print(result.generate_report())

            if not result.is_within_tolerance():
                console.print()
                console.print("[yellow]Warning:[/yellow] Some sync points outside tolerance")
                return 1

        return 0

    except FormatConversionError as e:
        console.print(f"\n[red]Format conversion error:[/red] {e}")
        logger.exception("Format conversion failed")
        return 1

    except GuitarProToolError as e:
        console.print(f"\n[red]Error:[/red] {e}")
        logger.exception("Pipeline failed")
        return 1

    except Exception as e:
        console.print(f"\n[red]Unexpected error:[/red] {e}")
        logger.exception("Unexpected error in pipeline")
        return 1

    finally:
        if handler:
            handler.cleanup()


def main():
    """Main entry point for CLI."""
    # Configure logging
    logger.remove()  # Remove default handler
    logger.add(
        sys.stderr,
        format="<dim>{time:HH:mm:ss}</dim> | <level>{level: <8}</level> | {message}",
        level="WARNING",  # Only show warnings and errors in CLI
    )

    try:
        # Check for CLI arguments
        args = parse_args()

        if args is not None:
            print_banner()

            if args.test_mode:
                # Test mode - run all configured test cases
                sys.exit(run_test_mode())
            else:
                # Non-interactive mode with specific arguments
                sys.exit(run_pipeline_noninteractive(args))
        else:
            # Interactive mode
            print_banner()
            main_menu()

    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted.[/dim]")
        sys.exit(1)


if __name__ == "__main__":
    main()
