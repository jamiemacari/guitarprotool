"""Main CLI module for Guitar Pro Audio Injection Tool.

Provides an interactive command-line interface for:
- Selecting Guitar Pro files
- Downloading/converting audio from YouTube or local files
- Detecting BPM and beat positions
- Injecting audio with sync points into GP files
"""

import shutil
import sys
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
from guitarprotool.core.beat_detector import BeatDetector, BeatInfo
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

# Rich console for styled output
console = Console()

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
    banner = """
[bold cyan]Guitar Pro Audio Injection Tool[/bold cyan]
[dim]v{version}[/dim]

Inject YouTube audio into Guitar Pro 8 files with automatic sync points.
    """.format(
        version=__version__
    )
    console.print(Panel(banner.strip(), border_style="cyan"))


def get_gp_file_path() -> Optional[Path]:
    """Prompt user for Guitar Pro file path.

    Returns:
        Path to .gp file or None if cancelled
    """
    result = questionary.path(
        "Select Guitar Pro file (.gp):",
        only_directories=False,
        style=custom_style,
    ).ask()

    if not result:
        return None

    path = Path(result).expanduser().resolve()

    if not path.exists():
        console.print(f"[red]Error:[/red] File not found: {path}")
        return None

    if path.suffix.lower() != ".gp":
        console.print(f"[red]Error:[/red] Expected .gp file, got: {path.suffix}")
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


def get_manual_bpm() -> Optional[float]:
    """Prompt user for manual BPM input.

    Returns:
        BPM value or None to use detected
    """
    use_manual = questionary.confirm(
        "Would you like to enter BPM manually?",
        default=False,
        style=custom_style,
    ).ask()

    if not use_manual:
        return None

    bpm_str = questionary.text(
        "Enter BPM:",
        validate=lambda x: x.replace(".", "").isdigit(),
        style=custom_style,
    ).ask()

    return float(bpm_str) if bpm_str else None


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

    gp_file = None

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:

            # Extract GP file
            extract_task = progress.add_task("[cyan]Extracting GP file...", total=None)
            gp_file = GPFile(gp_path)
            temp_dir = gp_file.extract()
            progress.update(
                extract_task, completed=100, total=100, description="[green]GP file extracted"
            )

            # Process audio
            audio_dir = gp_file.get_audio_dir()
            audio_info = process_audio(source_type, source_value, audio_dir, progress)
            if not audio_info:
                raise AudioProcessingError("Failed to process audio")

            # Detect beats
            beat_info = detect_beats(audio_info.file_path, progress)
            if not beat_info:
                raise BeatDetectionError("Failed to detect beats")

            # Get original tempo from GP file
            gpif_path = gp_file.get_gpif_path()
            modifier = XMLModifier(gpif_path)
            modifier.load()
            original_tempo = modifier.get_original_tempo()

            # Fall back to detected BPM if original tempo not found in GP file
            if original_tempo is None:
                original_tempo = beat_info.bpm
                logger.info(
                    f"No tempo found in GP file, using detected BPM: {original_tempo:.1f}"
                )

            # Display beat info
            progress.stop()
            console.print()
            display_beat_info(beat_info)

            # Option to manually override BPM
            manual_bpm = get_manual_bpm()
            if manual_bpm:
                beat_info = BeatInfo(
                    bpm=manual_bpm,
                    beat_times=beat_info.beat_times,
                    confidence=1.0,
                )
                console.print(f"[cyan]Using manual BPM:[/cyan] {manual_bpm}")

            console.print()

            # Restart progress for remaining tasks
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console,
            ) as progress2:

                # Generate sync points
                sync_task = progress2.add_task("[cyan]Generating sync points...", total=None)
                detector = BeatDetector()
                bar_count = modifier.get_bar_count()
                sync_point_data = detector.generate_sync_points(
                    beat_info,
                    original_tempo=original_tempo,
                    sync_interval=16,
                    max_bars=bar_count if bar_count > 0 else None,
                )

                # Convert to XML modifier format
                sync_points = [
                    SyncPoint(
                        bar=sp.bar,
                        frame_offset=sp.frame_offset,
                        modified_tempo=sp.modified_tempo,
                        original_tempo=sp.original_tempo,
                    )
                    for sp in sync_point_data
                ]
                progress2.update(
                    sync_task,
                    completed=100,
                    total=100,
                    description=f"[green]Generated {len(sync_points)} sync points",
                )

                # Inject into XML
                xml_task = progress2.add_task("[cyan]Modifying GP file...", total=None)

                # Create asset info
                asset_info = AssetInfo(
                    asset_id=0,
                    uuid=audio_info.uuid,
                    original_file_path=str(audio_info.file_path),
                )

                # Create backing track config
                track_config = BackingTrackConfig(
                    name=track_name,
                    short_name=track_name[:8] if len(track_name) > 8 else track_name,
                    asset_id=0,
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

                progress2.update(
                    xml_task, completed=100, total=100, description="[green]GP file modified"
                )

                # Repackage
                repack_task = progress2.add_task("[cyan]Repackaging...", total=None)
                gp_file.repackage(output_path)
                progress2.update(
                    repack_task, completed=100, total=100, description="[green]File saved"
                )

        # Success!
        console.print()
        console.print(
            Panel(
                f"[bold green]Success![/bold green]\n\n"
                f"Modified file saved to:\n[cyan]{output_path}[/cyan]\n\n"
                f"[dim]Detected BPM: {beat_info.bpm:.1f}\n"
                f"Sync points: {len(sync_points)}\n"
                f"Original tempo: {original_tempo:.1f}[/dim]",
                title="Complete",
                border_style="green",
            )
        )

    except GuitarProToolError as e:
        console.print(f"\n[red]Error:[/red] {e}")
        logger.exception("Pipeline failed")

    except Exception as e:
        console.print(f"\n[red]Unexpected error:[/red] {e}")
        logger.exception("Unexpected error in pipeline")

    finally:
        if gp_file:
            gp_file.cleanup()


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
