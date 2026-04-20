#!/usr/bin/env python3
"""
Screener Automation Agent

Monitors Screener.in watchlist for quarterly results and posts updates to Twitter.
Designed to run daily at 8 PM IST via cron or GitHub Actions.

Usage:
    python main.py              # Run once
    python main.py --dry-run    # Test without posting to Twitter
"""
import argparse
import sys

from orchestrator import main as run_agent
from logger import app_logger


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Screener.in Quarterly Results Monitor"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without posting to Twitter (test mode)"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode"
    )
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    if args.dry_run:
        app_logger.info("Running in DRY-RUN mode (no tweets will be posted)")

    try:
        run_agent(headless=args.headless, dry_run=args.dry_run)
        return 0
    except KeyboardInterrupt:
        app_logger.info("Interrupted by user")
        return 130
    except Exception as e:
        app_logger.error(f"Fatal error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
