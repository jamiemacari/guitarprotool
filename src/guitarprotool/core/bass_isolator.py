"""Bass isolation module for improved beat detection.

This module uses Demucs v4 (Hybrid Transformer model) to separate bass from
the audio mix. The isolated bass is used for more accurate beat detection,
especially for songs with ambient intros or complex mixes.

The isolated bass is only used for beat detection - the original full-mix
audio is still embedded in the GP file.

Dependencies:
    - torch>=2.0.0
    - torchaudio>=2.0.0
    - demucs>=4.0.0

Install with: pip install guitarprotool[bass-isolation]
"""

import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional

from loguru import logger

from guitarprotool.utils.exceptions import (
    IsolationError,
    IsolationDependencyError,
    ModelNotAvailableError,
)


# Lazy import flags - set when dependencies are actually imported
_DEMUCS_AVAILABLE: Optional[bool] = None
_TORCH_AVAILABLE: Optional[bool] = None


def _check_dependencies() -> bool:
    """Check if bass isolation dependencies are available.

    Returns:
        True if all dependencies are available
    """
    global _DEMUCS_AVAILABLE, _TORCH_AVAILABLE

    if _DEMUCS_AVAILABLE is not None:
        return _DEMUCS_AVAILABLE and _TORCH_AVAILABLE

    try:
        import torch
        _TORCH_AVAILABLE = True
        logger.debug(f"PyTorch available: {torch.__version__}")
    except ImportError:
        _TORCH_AVAILABLE = False
        logger.debug("PyTorch not available")

    try:
        import demucs  # noqa: F401
        _DEMUCS_AVAILABLE = True
        logger.debug("Demucs available")
    except ImportError:
        _DEMUCS_AVAILABLE = False
        logger.debug("Demucs not available")

    return _DEMUCS_AVAILABLE and _TORCH_AVAILABLE


@dataclass
class IsolationResult:
    """Result of bass isolation.

    Attributes:
        bass_path: Path to isolated bass audio file (WAV format)
        original_path: Path to original audio file
        model_used: Name of the separation model used
        processing_time: Time taken in seconds
        success: Whether isolation completed successfully
        error_message: Error message if isolation failed
    """

    bass_path: Optional[Path]
    original_path: Path
    model_used: str
    processing_time: float
    success: bool
    error_message: Optional[str] = None


# Type alias for progress callback
ProgressCallback = Callable[[float, str], None]


class BassIsolator:
    """Isolates bass from audio using Demucs neural network model.

    Uses Demucs v4 Hybrid Transformer model for state-of-the-art source
    separation. Falls back to CPU processing if CUDA is not available.

    Example:
        >>> if BassIsolator.is_available():
        ...     isolator = BassIsolator()
        ...     result = isolator.isolate("/path/to/audio.mp3")
        ...     if result.success:
        ...         beat_detector.analyze(result.bass_path)
    """

    DEFAULT_MODEL = "htdemucs"  # Best balance of quality and speed
    SUPPORTED_MODELS = ["htdemucs", "htdemucs_ft", "hdemucs_mmi", "htdemucs_6s"]

    def __init__(
        self,
        output_dir: Optional[Path] = None,
        model: str = DEFAULT_MODEL,
        device: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ):
        """Initialize BassIsolator.

        Args:
            output_dir: Directory to save isolated audio files.
                       If None, uses system temp directory.
            model: Demucs model name to use. Options:
                   - "htdemucs": Default, good balance (bass SDR 11.4)
                   - "htdemucs_ft": Fine-tuned, slightly better (bass SDR 11.9)
                   - "hdemucs_mmi": Best quality, more memory (bass SDR 12.0)
                   - "htdemucs_6s": 6 stems including guitar, piano
            device: Processing device ("cuda", "cpu", or None for auto-detect)
            progress_callback: Optional callback for progress updates.
                             Called with (percent: float, message: str)

        Raises:
            IsolationDependencyError: If torch/demucs not installed
            ModelNotAvailableError: If specified model is not available
        """
        if not self.is_available():
            raise IsolationDependencyError(
                "Bass isolation requires torch, torchaudio, and demucs. "
                "Install with: pip install guitarprotool[bass-isolation]"
            )

        if model not in self.SUPPORTED_MODELS:
            raise ModelNotAvailableError(
                f"Model '{model}' not supported. Available: {self.SUPPORTED_MODELS}"
            )

        self.output_dir = output_dir or Path(tempfile.gettempdir()) / "guitarprotool_isolation"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.model_name = model
        self.progress_callback = progress_callback

        # Auto-detect device if not specified
        if device is None:
            import torch

            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.debug(f"Auto-detected device: {self.device}")
        else:
            self.device = device

        logger.debug(
            f"BassIsolator initialized: model={model}, device={self.device}, "
            f"output_dir={self.output_dir}"
        )

        # Model is loaded lazily on first isolation
        self._model = None
        self._model_loaded = False

    def _load_model(self) -> None:
        """Load the Demucs model (lazy loading).

        Raises:
            IsolationError: If model loading fails
        """
        if self._model_loaded:
            return

        try:
            import torch
            from demucs.pretrained import get_model

            if self.progress_callback:
                self.progress_callback(0.05, "Loading Demucs model...")

            logger.info(f"Loading Demucs model: {self.model_name}")
            self._model = get_model(self.model_name)
            self._model.to(self.device)
            self._model.eval()
            self._model_loaded = True

            logger.debug(f"Model loaded on device: {self.device}")
            logger.debug(f"Model sources: {self._model.sources}")

        except Exception as e:
            logger.error(f"Failed to load Demucs model: {e}")
            raise IsolationError(f"Failed to load model '{self.model_name}': {e}")

    def isolate(
        self,
        audio_path: Path | str,
        output_filename: Optional[str] = None,
    ) -> IsolationResult:
        """Isolate bass from audio file.

        Args:
            audio_path: Path to input audio file (MP3, WAV, etc.)
            output_filename: Optional output filename (without extension).
                           If None, uses "{input_stem}_bass".

        Returns:
            IsolationResult with path to isolated bass audio

        Note:
            The isolated bass is saved as WAV format at the model's
            native sample rate (44.1 kHz for htdemucs models).
        """
        start_time = time.time()
        audio_path = Path(audio_path)

        logger.info(f"Isolating bass from: {audio_path}")

        if not audio_path.exists():
            return IsolationResult(
                bass_path=None,
                original_path=audio_path,
                model_used=self.model_name,
                processing_time=time.time() - start_time,
                success=False,
                error_message=f"Audio file not found: {audio_path}",
            )

        try:
            # Load model (lazy)
            self._load_model()

            # Import required modules
            import torch
            import torchaudio
            from demucs.audio import AudioFile
            from demucs.apply import apply_model

            # Load audio
            if self.progress_callback:
                self.progress_callback(0.15, "Loading audio file...")

            logger.debug("Loading audio with Demucs AudioFile...")
            wav = AudioFile(audio_path).read(
                streams=0,
                samplerate=self._model.samplerate,
                channels=self._model.audio_channels,
            )
            wav = wav.to(self.device)

            logger.debug(
                f"Audio loaded: shape={wav.shape}, samplerate={self._model.samplerate}"
            )

            # Apply separation model
            if self.progress_callback:
                self.progress_callback(0.25, "Separating sources (this may take a while)...")

            logger.info("Running source separation...")
            with torch.no_grad():
                sources = apply_model(
                    self._model,
                    wav[None],  # Add batch dimension
                    device=self.device,
                    progress=True,
                    num_workers=0,  # Avoid multiprocessing issues
                )

            # Extract bass stem
            sources = sources[0]  # Remove batch dimension
            bass_idx = self._model.sources.index("bass")
            bass = sources[bass_idx]

            logger.debug(f"Bass extracted: shape={bass.shape}")

            # Save isolated bass
            if self.progress_callback:
                self.progress_callback(0.9, "Saving isolated bass...")

            output_name = output_filename or f"{audio_path.stem}_bass"
            output_path = self.output_dir / f"{output_name}.wav"

            # Ensure bass is on CPU and has correct shape for torchaudio
            bass_cpu = bass.cpu()

            torchaudio.save(
                str(output_path),
                bass_cpu,
                self._model.samplerate,
            )

            processing_time = time.time() - start_time
            logger.success(
                f"Bass isolated in {processing_time:.1f}s: {output_path}"
            )

            if self.progress_callback:
                self.progress_callback(1.0, "Bass isolation complete")

            return IsolationResult(
                bass_path=output_path,
                original_path=audio_path,
                model_used=self.model_name,
                processing_time=processing_time,
                success=True,
            )

        except Exception as e:
            processing_time = time.time() - start_time
            error_msg = str(e)
            logger.error(f"Bass isolation failed after {processing_time:.1f}s: {error_msg}")

            # Check for common errors and provide helpful messages
            if "CUDA out of memory" in error_msg:
                error_msg = (
                    "GPU out of memory. Try with device='cpu' or a shorter audio file. "
                    f"Original error: {error_msg}"
                )
            elif "No such file or directory" in error_msg:
                error_msg = f"Audio file not found or ffmpeg not available: {error_msg}"

            return IsolationResult(
                bass_path=None,
                original_path=audio_path,
                model_used=self.model_name,
                processing_time=processing_time,
                success=False,
                error_message=error_msg,
            )

    @staticmethod
    def is_available() -> bool:
        """Check if bass isolation is available (dependencies installed).

        Returns:
            True if torch, torchaudio, and demucs are installed
        """
        return _check_dependencies()

    @staticmethod
    def get_device_info() -> Dict[str, any]:
        """Get information about available processing devices.

        Returns:
            Dictionary with device availability info:
            - cuda_available: bool
            - cuda_device_count: int
            - cuda_device_name: str (if CUDA available)
            - recommended_device: str ("cuda" or "cpu")
        """
        if not _check_dependencies():
            return {
                "cuda_available": False,
                "cuda_device_count": 0,
                "recommended_device": "cpu",
                "error": "Dependencies not installed",
            }

        import torch

        info = {
            "cuda_available": torch.cuda.is_available(),
            "cuda_device_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
        }

        if info["cuda_available"]:
            info["cuda_device_name"] = torch.cuda.get_device_name(0)
            info["recommended_device"] = "cuda"
        else:
            info["recommended_device"] = "cpu"

        return info

    def cleanup(self) -> None:
        """Remove temporary isolated audio files.

        Removes all files in output_dir that match the isolation pattern
        (files ending with _bass.wav).
        """
        logger.debug(f"Cleaning up isolation files in: {self.output_dir}")

        for file in self.output_dir.glob("*_bass.wav"):
            if file.is_file():
                logger.debug(f"Removing: {file}")
                file.unlink()

    def __enter__(self) -> "BassIsolator":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - cleanup temporary files."""
        self.cleanup()
