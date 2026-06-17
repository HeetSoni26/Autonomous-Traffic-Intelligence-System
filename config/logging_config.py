"""
config/logging_config.py
Configures loguru for structured JSON logging and colored console output.
Import this module once at entry-points (coordinator, api, dashboard).
"""
import sys
import os
from loguru import logger

# Avoid importing settings here to prevent circular import;
# read LOG_LEVEL directly from env.
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


def setup_logging() -> None:
    logger.remove()  # Remove default handler

    # ── Console: human-readable, colorized ───────────────────────
    logger.add(
        sys.stdout,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> — "
            "<level>{message}</level>"
        ),
        level=LOG_LEVEL,
        colorize=True,
        backtrace=True,
        diagnose=True,
    )

    # ── File: structured JSON, rotated ───────────────────────────
    os.makedirs("logs", exist_ok=True)
    logger.add(
        "logs/traffic_system.log",
        format="{message}",
        level=LOG_LEVEL,
        rotation="10 MB",
        retention="7 days",
        serialize=True,      # → JSON lines
        backtrace=True,
        diagnose=False,      # Don't leak sensitive data in JSON
    )

    logger.info("Logging initialised — level={}", LOG_LEVEL)


# Auto-configure when this module is imported
setup_logging()
