import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

def mask_key(key: str) -> str:
    """Masks sensitive API keys for safe logging."""
    if not key or len(key) < 8:
        return "***"
    return key[:4] + "***" + key[-4:]

def setup_logging(app_dir: str) -> logging.Logger:
    log_dir = Path(app_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Rotating file handler: max 5 MB per file, keep 3 backups
    file_handler = RotatingFileHandler(
        log_dir / "overlay.log",
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))

    # Console handler: INFO and above only
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(
        "[%(levelname)s] %(name)s: %(message)s"
    ))

    root = logging.getLogger()
    if not root.handlers:
        root.setLevel(logging.DEBUG)
        root.addHandler(file_handler)
        root.addHandler(console_handler)

    logger = logging.getLogger("invisibleai")
    logger.setLevel(logging.DEBUG)
    return logger
