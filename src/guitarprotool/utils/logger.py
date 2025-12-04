"""Logging configuration using loguru.

This module provides a centralized logging setup for the entire application.
Uses loguru for simpler API and better formatting compared to stdlib logging.
"""

import sys
from pathlib import Path
from typing import Optional

from loguru import logger


def setup_logging(
    level: str = "INFO",
    log_file: Optional[Path] = None,
    rotation: str = "10 MB",
    retention: str = "1 week",
    colorize: bool = True,
) -> None:
    """Configure loguru logger with console and optional file output.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional path to log file. If None, only logs to console
        rotation: When to rotate log file (e.g., "10 MB", "1 day")
        retention: How long to keep old log files (e.g., "1 week", "30 days")
        colorize: Whether to colorize console output

    Example:
        >>> from pathlib import Path
        >>> log_path = Path.home() / ".local/share/guitarprotool/logs/guitarprotool.log"
        >>> setup_logging(level="DEBUG", log_file=log_path)
    """
    # Remove default handler
    logger.remove()

    # Console handler (INFO and above, colored)
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level=level,
        colorize=colorize,
        backtrace=True,
        diagnose=True,
    )

    # File handler (DEBUG and above, rotated)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        logger.add(
            log_file,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
            level="DEBUG",
            rotation=rotation,
            retention=retention,
            compression="zip",
            backtrace=True,
            diagnose=True,
        )
        logger.info(f"Logging to file: {log_file}")


def get_default_log_file() -> Path:
    """Get the default log file path.

    Returns:
        Path to default log file in user's local share directory
    """
    return Path.home() / ".local/share/guitarprotool/logs/guitarprotool.log"


# Export logger for use throughout the application
__all__ = ["logger", "setup_logging", "get_default_log_file"]
