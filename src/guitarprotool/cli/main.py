"""Main CLI module for Guitar Pro Audio Injection Tool.

Provides an interactive command-line interface for:
- Selecting Guitar Pro files
- Downloading/converting audio from YouTube or local files
- Detecting BPM and beat positions
- Injecting audio with sync points into GP files
"""

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

# Try to import AudioProcessor - may fail on Python 3.14 due to pydub/audioop issue
try:
    from guitarprotool.core.audio_processor import AudioProcessor, AudioInfo

    AUDIO_PROCESSOR_AVAILABLE = True
except ImportError as e:
    AudioProcessor = None  # type: ignore
    AudioInfo = None  # type: ignore
    AUDIO_PROCESSOR_AVAILABLE = False
    logger.warning(f"AudioProcessor not available: {e}")

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

            # Detect beats
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

            # Find first bar with actual notes (for tabs with intro rests)
            first_bar_with_notes = modifier.get_first_bar_with_notes()
            if first_bar_with_notes > 0:
                console.print(
                    f"[cyan]Note:[/cyan] Tab has {first_bar_with_notes} intro bar(s) "
                    f"before notes start. Audio will align with bar {first_bar_with_notes}."
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
                )

                # Adjust frame_padding to account for intro bars
                # The first detected beat should align with first_bar_with_notes, not bar 0
                # frame_padding already shifts audio left by first_beat_time
                # We need to shift it right by the duration of intro bars
                if first_bar_with_notes > 0:
                    beats_per_bar = 4
                    seconds_per_bar = 60.0 / original_tempo * beats_per_bar
                    intro_duration = first_bar_with_notes * seconds_per_bar
                    intro_frames = int(intro_duration * 44100)  # sample rate
                    adjusted_frame_padding = sync_result.frame_padding + intro_frames
                else:
                    adjusted_frame_padding = sync_result.frame_padding

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
                # frame_padding is adjusted to align first beat with first_bar_with_notes
                track_config = BackingTrackConfig(
                    name=track_name,
                    short_name=track_name[:8] if len(track_name) > 8 else track_name,
                    asset_id=0,
                    frame_padding=adjusted_frame_padding,
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
        console.print(
            Panel(
                f"[bold green]Success![/bold green]\n\n"
                f"Modified file saved to:\n[cyan]{output_path}[/cyan]\n\n"
                f"[dim]Detected BPM: {beat_info.bpm:.1f}\n"
                f"Sync points: {len(sync_points)}\n"
                f"Original tempo: {original_tempo:.1f}\n"
                f"Audio offset: {sync_result.first_beat_time:.3f}s[/dim]\n\n"
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
        print_banner()
        main_menu()
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted.[/dim]")
        sys.exit(1)


if __name__ == "__main__":
    main()
