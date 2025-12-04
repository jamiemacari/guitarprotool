"""Audio processing module for downloading and converting audio files.

This module handles:
- Downloading audio from YouTube using yt-dlp
- Converting local audio files to MP3 format
- Normalizing audio to target specifications (192kbps, 44.1kHz)
- Generating UUID filenames for .gp archive embedding
"""

import hashlib
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass

import yt_dlp
from pydub import AudioSegment
from loguru import logger

from guitarprotool.utils.exceptions import (
    DownloadError,
    ConversionError,
    AudioValidationError,
)


@dataclass
class AudioInfo:
    """Information about processed audio file.

    Attributes:
        file_path: Path to the processed MP3 file
        uuid: Generated UUID for the audio file (SHA1 hash)
        duration_ms: Duration in milliseconds
        sample_rate: Sample rate in Hz
        channels: Number of audio channels (1=mono, 2=stereo)
        bitrate: Bitrate in kbps
        title: Original title (from YouTube or filename)
        original_url: Original YouTube URL (if downloaded from YouTube)
    """
    file_path: Path
    uuid: str
    duration_ms: int
    sample_rate: int
    channels: int
    bitrate: int
    title: str
    original_url: Optional[str] = None


class AudioProcessor:
    """Handles audio download, conversion, and normalization.

    Target audio specifications:
    - Format: MP3
    - Bitrate: 192 kbps
    - Sample rate: 44.1 kHz
    - Channels: Stereo (2)

    Example:
        >>> processor = AudioProcessor()
        >>> audio_info = processor.process_youtube("https://www.youtube.com/watch?v=...")
        >>> print(f"Audio UUID: {audio_info.uuid}")
        >>> print(f"Duration: {audio_info.duration_ms}ms")
    """

    # Target audio specifications
    TARGET_SAMPLE_RATE = 44100  # Hz
    TARGET_BITRATE = 192  # kbps
    TARGET_CHANNELS = 2  # Stereo
    TARGET_FORMAT = "mp3"

    def __init__(
        self,
        output_dir: Optional[Path] = None,
        progress_callback: Optional[callable] = None,
    ):
        """Initialize AudioProcessor.

        Args:
            output_dir: Directory to save processed audio files.
                       If None, uses system temp directory.
            progress_callback: Optional callback for progress updates.
                             Called with (percent: float, status: str)
        """
        self.output_dir = output_dir or Path(tempfile.gettempdir()) / "guitarprotool"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.progress_callback = progress_callback

        logger.debug(f"AudioProcessor initialized with output_dir: {self.output_dir}")

    def process_youtube(
        self,
        url: str,
        output_filename: Optional[str] = None,
    ) -> AudioInfo:
        """Download and process audio from YouTube URL.

        Args:
            url: YouTube video URL
            output_filename: Optional custom filename (without extension).
                           If None, uses video title.

        Returns:
            AudioInfo object with processed audio details

        Raises:
            DownloadError: If download fails
            ConversionError: If audio conversion fails
            AudioValidationError: If downloaded audio is invalid

        Example:
            >>> processor = AudioProcessor()
            >>> info = processor.process_youtube("https://youtube.com/watch?v=abc123")
            >>> print(f"Downloaded: {info.title}")
        """
        logger.info(f"Processing YouTube URL: {url}")

        try:
            # Configure yt-dlp options
            temp_output = self.output_dir / "temp_download.%(ext)s"

            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': str(temp_output),
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': self.TARGET_FORMAT,
                    'preferredquality': str(self.TARGET_BITRATE),
                }],
                'quiet': True,
                'no_warnings': True,
                'extract_audio': True,
                'progress_hooks': [self._yt_dlp_progress_hook],
            }

            # Download and extract info
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                logger.debug("Extracting video info...")
                info_dict = ydl.extract_info(url, download=True)

                if not info_dict:
                    raise DownloadError(f"Failed to extract info from URL: {url}")

                title = info_dict.get('title', 'Unknown')
                logger.info(f"Downloaded: {title}")

            # Find the downloaded file
            downloaded_file = self.output_dir / f"temp_download.{self.TARGET_FORMAT}"

            if not downloaded_file.exists():
                raise DownloadError(f"Downloaded file not found: {downloaded_file}")

            # Process the downloaded audio
            final_filename = output_filename or self._sanitize_filename(title)
            audio_info = self._process_audio_file(
                downloaded_file,
                final_filename,
                title=title,
                original_url=url,
            )

            # Clean up temp file
            if downloaded_file != audio_info.file_path:
                downloaded_file.unlink(missing_ok=True)

            logger.success(f"YouTube audio processed: {audio_info.uuid}")
            return audio_info

        except yt_dlp.utils.DownloadError as e:
            logger.error(f"yt-dlp download error: {e}")
            raise DownloadError(f"Failed to download from YouTube: {e}")
        except Exception as e:
            logger.error(f"Unexpected error processing YouTube URL: {e}")
            raise DownloadError(f"Failed to process YouTube URL: {e}")

    def process_local_file(
        self,
        file_path: Path,
        output_filename: Optional[str] = None,
    ) -> AudioInfo:
        """Process a local audio file and convert to target format.

        Args:
            file_path: Path to local audio file
            output_filename: Optional custom filename (without extension).
                           If None, uses original filename.

        Returns:
            AudioInfo object with processed audio details

        Raises:
            ConversionError: If audio conversion fails
            AudioValidationError: If audio file is invalid
            FileNotFoundError: If input file doesn't exist

        Example:
            >>> processor = AudioProcessor()
            >>> info = processor.process_local_file(Path("song.wav"))
            >>> print(f"Converted to: {info.file_path}")
        """
        logger.info(f"Processing local file: {file_path}")

        if not file_path.exists():
            raise FileNotFoundError(f"Audio file not found: {file_path}")

        if not file_path.is_file():
            raise AudioValidationError(f"Path is not a file: {file_path}")

        final_filename = output_filename or file_path.stem

        return self._process_audio_file(
            file_path,
            final_filename,
            title=file_path.stem,
        )

    def _process_audio_file(
        self,
        input_path: Path,
        output_filename: str,
        title: str,
        original_url: Optional[str] = None,
    ) -> AudioInfo:
        """Process audio file to target specifications.

        Args:
            input_path: Path to input audio file
            output_filename: Output filename (without extension)
            title: Audio title for metadata
            original_url: Optional original YouTube URL

        Returns:
            AudioInfo object

        Raises:
            ConversionError: If conversion fails
        """
        logger.debug(f"Processing audio file: {input_path}")

        try:
            # Load audio file
            if self.progress_callback:
                self.progress_callback(10, "Loading audio file...")

            audio = AudioSegment.from_file(str(input_path))
            logger.debug(f"Loaded audio: {len(audio)}ms, {audio.frame_rate}Hz, {audio.channels}ch")

            # Convert to target specifications
            if self.progress_callback:
                self.progress_callback(30, "Converting audio format...")

            # Resample to target sample rate
            if audio.frame_rate != self.TARGET_SAMPLE_RATE:
                logger.debug(f"Resampling from {audio.frame_rate}Hz to {self.TARGET_SAMPLE_RATE}Hz")
                audio = audio.set_frame_rate(self.TARGET_SAMPLE_RATE)

            # Convert to target channels
            if audio.channels != self.TARGET_CHANNELS:
                logger.debug(f"Converting from {audio.channels}ch to {self.TARGET_CHANNELS}ch")
                audio = audio.set_channels(self.TARGET_CHANNELS)

            # Generate UUID from file content
            if self.progress_callback:
                self.progress_callback(60, "Generating UUID...")

            uuid = self._generate_uuid(input_path)

            # Export to MP3 with target bitrate
            if self.progress_callback:
                self.progress_callback(70, "Exporting MP3...")

            output_path = self.output_dir / f"{uuid}.{self.TARGET_FORMAT}"

            audio.export(
                str(output_path),
                format=self.TARGET_FORMAT,
                bitrate=f"{self.TARGET_BITRATE}k",
                parameters=["-ar", str(self.TARGET_SAMPLE_RATE)],
            )

            logger.info(f"Audio exported to: {output_path}")

            if self.progress_callback:
                self.progress_callback(100, "Complete")

            # Create AudioInfo
            return AudioInfo(
                file_path=output_path,
                uuid=uuid,
                duration_ms=len(audio),
                sample_rate=self.TARGET_SAMPLE_RATE,
                channels=self.TARGET_CHANNELS,
                bitrate=self.TARGET_BITRATE,
                title=title,
                original_url=original_url,
            )

        except Exception as e:
            logger.error(f"Audio conversion error: {e}")
            raise ConversionError(f"Failed to convert audio: {e}")

    def _generate_uuid(self, file_path: Path) -> str:
        """Generate SHA1 UUID from file content.

        Args:
            file_path: Path to file

        Returns:
            SHA1 hash as UUID string (format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)
        """
        sha1 = hashlib.sha1()

        with open(file_path, 'rb') as f:
            while chunk := f.read(8192):
                sha1.update(chunk)

        # Format as UUID: 8-4-4-4-12 hex digits
        hash_hex = sha1.hexdigest()
        uuid = f"{hash_hex[0:8]}-{hash_hex[8:12]}-{hash_hex[12:16]}-{hash_hex[16:20]}-{hash_hex[20:32]}"

        logger.debug(f"Generated UUID: {uuid}")
        return uuid

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename by removing invalid characters.

        Args:
            filename: Original filename

        Returns:
            Sanitized filename safe for filesystem
        """
        # Remove invalid characters
        invalid_chars = '<>:"/\\|?*'
        sanitized = ''.join(c if c not in invalid_chars else '_' for c in filename)

        # Limit length
        max_length = 200
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length]

        return sanitized.strip()

    def _yt_dlp_progress_hook(self, d: Dict[str, Any]) -> None:
        """Progress hook for yt-dlp downloads.

        Args:
            d: Progress dictionary from yt-dlp
        """
        if not self.progress_callback:
            return

        status = d.get('status')

        if status == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            downloaded = d.get('downloaded_bytes', 0)

            if total > 0:
                percent = (downloaded / total) * 100
                self.progress_callback(percent, f"Downloading: {percent:.1f}%")

        elif status == 'finished':
            self.progress_callback(100, "Download complete, converting...")

    def cleanup(self) -> None:
        """Clean up temporary files in output directory.

        Removes all files in output_dir that don't match the UUID pattern.
        """
        logger.debug(f"Cleaning up temporary files in: {self.output_dir}")

        for file in self.output_dir.glob("*"):
            if file.is_file() and not self._is_uuid_filename(file.stem):
                logger.debug(f"Removing temp file: {file}")
                file.unlink()

    def _is_uuid_filename(self, filename: str) -> bool:
        """Check if filename matches UUID pattern.

        Args:
            filename: Filename to check (without extension)

        Returns:
            True if filename matches UUID pattern
        """
        # UUID pattern: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
        parts = filename.split('-')
        if len(parts) != 5:
            return False

        return (
            len(parts[0]) == 8 and
            len(parts[1]) == 4 and
            len(parts[2]) == 4 and
            len(parts[3]) == 4 and
            len(parts[4]) == 12
        )
