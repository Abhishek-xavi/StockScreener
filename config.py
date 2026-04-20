"""
Configuration settings for Screener Automation Agent.
All sensitive credentials should be in .env file (not committed to git).
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Base paths
BASE_DIR = Path(__file__).parent
LOG_DIR = BASE_DIR / "logs"
DATA_DIR = BASE_DIR / "data"

# Create directories if they don't exist
LOG_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

# Screener.in credentials
SCREENER_USERNAME = os.getenv("SCREENER_USERNAME")
SCREENER_PASSWORD = os.getenv("SCREENER_PASSWORD")

# Twitter API credentials
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_TOKEN_SECRET = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")

# Anthropic API (primary summarizer — set key in .env)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

# Ollama configuration (fallback summarizer — local/free)
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

# Gmail (report email)
GMAIL_FROM = os.getenv("GMAIL_FROM", "")          # your Gmail address
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")  # 16-char App Password
GMAIL_TO = os.getenv("GMAIL_TO", "")              # recipient (defaults to GMAIL_FROM)

# Scraping settings
SCREENER_BASE_URL = "https://screener.in"
REQUEST_TIMEOUT = 30
RETRY_ATTEMPTS = 3
RETRY_DELAY = 2  # seconds

# Rate limiting (to avoid being blocked)
REQUEST_DELAY = 1  # seconds between requests

# Logging
LOG_FILE = LOG_DIR / "screener_automation.log"
TWEET_LOG_FILE = LOG_DIR / "posted_tweets.log"
ERROR_LOG_FILE = LOG_DIR / "errors.log"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Job schedule (for reference - actual cron set in GitHub Actions later)
SCHEDULE_HOUR = 20  # 8 PM
SCHEDULE_MINUTE = 0
SCHEDULE_TIMEZONE = "Asia/Kolkata"
