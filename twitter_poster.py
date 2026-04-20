"""
Twitter/X API integration with duplicate detection via log file.
Reports errors to Twitter if posting fails.
"""
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import requests
from requests_oauthlib import OAuth1

import config
from logger import app_logger, log_tweet_posted, log_duplicate_detected


class TwitterPoster:
    """Handle posting to Twitter/X with duplicate detection."""

    def __init__(self):
        self.auth = OAuth1(
            config.TWITTER_API_KEY,
            config.TWITTER_API_SECRET,
            config.TWITTER_ACCESS_TOKEN,
            config.TWITTER_ACCESS_TOKEN_SECRET
        )
        self.tweet_log = Path(config.TWEET_LOG_FILE)
        self._ensure_log_exists()

    def _ensure_log_exists(self):
        """Create tweet log file if it doesn't exist."""
        if not self.tweet_log.exists():
            self.tweet_log.parent.mkdir(parents=True, exist_ok=True)
            self.tweet_log.write_text("# Tweet Log - Format: timestamp | company | quarter | tweet_hash\n")

    def _is_duplicate(self, company: str, quarter: str, content: str) -> bool:
        """
        Check if this content has already been posted.

        Args:
            company: Company name/code
            quarter: Quarter identifier (e.g., "Q2 FY25")
            content: Tweet content

        Returns:
            True if already posted, False otherwise
        """
        if not self.tweet_log.exists():
            return False

        # Create a simple hash/identifier for this content
        content_hash = f"{company.lower()}|{quarter.lower()}"

        try:
            log_content = self.tweet_log.read_text()
            return content_hash in log_content.lower()
        except Exception as e:
            app_logger.error(f"Error reading tweet log: {e}")
            return False  # If we can't read log, proceed with caution

    def _log_tweet(self, company: str, quarter: str, content: str, success: bool):
        """Record posted tweet in log file."""
        timestamp = datetime.now().isoformat()
        status = "SUCCESS" if success else "FAILED"
        content_hash = f"{company.lower()}|{quarter.lower()}"

        log_entry = f"{timestamp} | {status} | {content_hash}\n"

        try:
            with open(self.tweet_log, "a") as f:
                f.write(log_entry)
        except Exception as e:
            app_logger.error(f"Failed to write to tweet log: {e}")

    def post_tweet(self, text: str, company: str = "", quarter: str = "", skip_duplicate_check: bool = False) -> bool:
        """
        Post a tweet with automatic duplicate detection and chunking.

        Args:
            text: Tweet content
            company: Company name (for duplicate detection)
            quarter: Quarter identifier (for duplicate detection)
            skip_duplicate_check: Skip check if True

        Returns:
            True if posted successfully, False otherwise
        """
        # Validate input
        if not text or not isinstance(text, str):
            app_logger.error("Invalid tweet text provided")
            return False

        # Check for duplicates
        if not skip_duplicate_check and company and quarter:
            if self._is_duplicate(company, quarter, text):
                log_duplicate_detected(company, quarter)
                return True  # Treat as success (already posted)

        # Post single or threaded tweet
        max_length = 280
        if len(text) <= max_length:
            success = self._post_single_tweet(text)
        else:
            success = self._post_thread(text)

        # Log result
        if company and quarter:
            self._log_tweet(company, quarter, text, success)

        if success:
            log_tweet_posted(company or "Unknown", quarter or "Update")

        return success

    def _post_single_tweet(self, text: str) -> bool:
        """Post a single tweet."""
        url = "https://api.twitter.com/2/tweets"
        payload = {"text": text}

        try:
            response = requests.post(url, auth=self.auth, json=payload)

            if response.status_code == 201:
                app_logger.info(f"Tweet posted: {text[:50]}...")
                return True
            elif response.status_code == 403 and "duplicate" in response.text.lower():
                app_logger.warning("Duplicate tweet detected by Twitter API")
                return True  # Treat as success
            else:
                app_logger.error(f"Twitter API error: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            app_logger.error(f"Failed to post tweet: {e}")
            return False

    def _post_thread(self, text: str) -> bool:
        """Post a long tweet as a thread."""
        max_length = 270  # Leave room for thread indicator
        chunks = []

        # Split into chunks
        while len(text) > 0:
            if len(text) <= max_length:
                chunks.append(text)
                break
            # Find last space within limit
            split_point = text.rfind(" ", 0, max_length)
            if split_point == -1:
                split_point = max_length
            chunks.append(text[:split_point])
            text = text[split_point:].strip()

        # Post thread
        total = len(chunks)
        for i, chunk in enumerate(chunks):
            numbered_chunk = f"{chunk} ({i+1}/{total})"
            if not self._post_single_tweet(numbered_chunk):
                return False
            if i < total - 1:  # Don't delay after last tweet
                time.sleep(2)  # Rate limiting

        return True

    def post_error_report(self, errors: List[tuple]):
        """
        Post a summary of errors encountered during run.

        Args:
            errors: List of (company, error_message) tuples
        """
        if not errors:
            return

        # Format error report
        error_text = "⚠️ Screener Bot Errors\n\n"
        for company, error in errors[:5]:  # Max 5 errors
            error_text += f"• {company}: {error[:50]}...\n"

        if len(errors) > 5:
            error_text += f"\n...and {len(errors) - 5} more"

        # Post without duplicate check (errors should always go through)
        self.post_tweet(error_text, skip_duplicate_check=True)


# Global instance
twitter = TwitterPoster()


def format_alert_tweet(result, insights=None) -> str:
    """
    Build a crisp alert tweet with numbers + one-line guidance check.
    Stays within 280 chars.
    """
    import re as _re

    lines = []
    lines.append(f"📊 ${result.company_code.upper()} | {result.quarter}")
    lines.append(f"")
    lines.append(f"💰 Sales: ₹{result.sales}Cr  YoY {result.sales_growth_yoy or 'N/A'}")
    lines.append(f"📈 Profit: ₹{result.net_profit}Cr  YoY {result.profit_growth_yoy or 'N/A'}")

    if result.eps:
        lines.append(f"⚡ EPS: ₹{result.eps}")

    # Guidance check — find revenue/CAGR target and compare vs actual YoY
    if insights and insights.management_guidance:
        yoy_str = result.sales_growth_yoy or ""
        yoy_num = None
        m = _re.search(r'([+-]?\d+\.?\d*)', yoy_str.replace(",", ""))
        if m:
            yoy_num = float(m.group(1))

        for target in insights.management_guidance:
            tl = target.lower()
            if any(k in tl for k in ["revenue", "sales", "cagr", "topline"]):
                pct = _re.search(r'(\d+)%\s*[-–to]+\s*(\d+)%|(\d+)%', target)
                if pct and yoy_num is not None:
                    low = int(pct.group(1) or pct.group(3))
                    high = int(pct.group(2)) if pct.group(2) else low
                    if yoy_num >= high:
                        verdict = f"✅ Ahead ({low}-{high}% target → {yoy_num:.0f}% YoY)"
                    elif yoy_num >= low:
                        verdict = f"✅ On Track ({low}-{high}% target → {yoy_num:.0f}% YoY)"
                    else:
                        verdict = f"⚠️ Behind ({low}-{high}% target → {yoy_num:.0f}% YoY)"
                    lines.append(f"")
                    lines.append(f"🎯 Guidance: {verdict}")
                    break

    lines.append(f"")
    lines.append("#StockAlert #Investing #NSE")

    tweet = "\n".join(lines)

    # Trim to 280 if somehow over
    if len(tweet) > 280:
        tweet = tweet[:277] + "..."

    return tweet


def post_update(company: str, quarter: str, text: str) -> bool:
    """Convenience function to post an update."""
    return twitter.post_tweet(text, company, quarter)


def post_error_report(errors: List[tuple]):
    """Convenience function to post error report."""
    return twitter.post_error_report(errors)
