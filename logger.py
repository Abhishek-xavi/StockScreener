"""
Centralized logging configuration for clear, crisp debugging.
Outputs to console and rotating log files.
"""
import logging
import logging.handlers
from datetime import datetime
from pathlib import Path

import config


def setup_logger(name: str, log_file: Path = None, level: str = "INFO") -> logging.Logger:
    """
    Configure logger with console and file handlers.

    Args:
        name: Logger name (usually __name__)
        log_file: Optional specific log file path
        level: Logging level (DEBUG, INFO, WARNING, ERROR)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    # Clear existing handlers (avoid duplicates)
    logger.handlers = []

    # Format: timestamp | level | module | message
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (rotating - keeps last 5 files, 1MB each)
    if log_file:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=1024 * 1024,  # 1 MB
            backupCount=5
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


# Main application logger
app_logger = setup_logger("screener_agent", config.LOG_FILE, config.LOG_LEVEL)


def log_job_start():
    """Log the start of a new job run."""
    app_logger.info("=" * 60)
    app_logger.info("JOB STARTED")
    app_logger.info(f"Timestamp: {datetime.now().isoformat()}")
    app_logger.info("=" * 60)


def log_job_end(success: bool, companies_checked: int = 0, results_found: int = 0):
    """Log the end of a job run with summary stats."""
    app_logger.info("=" * 60)
    if success:
        app_logger.info("JOB COMPLETED SUCCESSFULLY")
        app_logger.info(f"Companies checked: {companies_checked}")
        app_logger.info(f"New results found: {results_found}")
    else:
        app_logger.error("JOB FAILED")
    app_logger.info(f"Timestamp: {datetime.now().isoformat()}")
    app_logger.info("=" * 60)


def log_company_start(company_name: str):
    """Log when starting to process a company."""
    app_logger.info(f"[START] Processing: {company_name}")


def log_company_success(company_name: str, action: str):
    """Log successful completion for a company."""
    app_logger.info(f"[SUCCESS] {company_name}: {action}")


def log_company_error(company_name: str, error: str, skipped: bool = True):
    """Log error for a company (will be skipped or retried)."""
    if skipped:
        app_logger.warning(f"[SKIPPED] {company_name}: {error}")
    else:
        app_logger.error(f"[ERROR] {company_name}: {error}")


def log_tweet_posted(company_name: str, tweet_type: str):
    """Log when a tweet is successfully posted."""
    app_logger.info(f"[TWEET] {company_name}: Posted {tweet_type} update")


def log_duplicate_detected(company_name: str, quarter: str):
    """Log when duplicate is detected and skipped."""
    app_logger.info(f"[DUPLICATE] {company_name}: {quarter} already posted, skipping")
