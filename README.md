# Screener Automation Agent

Daily automation that monitors your Screener.in watchlist for quarterly results and posts updates to Twitter/X.

## Features

- **Dynamic Watchlist**: Automatically fetches companies from your Screener.in watchlist
- **Quarterly Results Detection**: Identifies when new quarterly results are published
- **Smart Posting**: Posts to Twitter with duplicate detection (no spam)
- **AI Summarization**: Uses local Ollama (Llama 3.1) for PDF summary generation
- **Error Reporting**: Reports failures via Twitter DM or summary tweet
- **Structured Logging**: Clear, timestamped logs for debugging

## Project Structure

```
ScreenerAutomation/
├── config.py              # Configuration settings
├── logger.py              # Centralized logging
├── browser_utils.py       # WebDriver utilities
├── screener_client.py     # Screener.in scraper
├── twitter_poster.py      # Twitter/X API client
├── ai_summarizer.py       # Ollama AI integration
├── orchestrator.py        # Main workflow coordinator
├── main.py                # Entry point
├── .env                   # Secrets (not in git)
├── .env.example           # Template for secrets
├── logs/                  # Log files
│   ├── screener_automation.log
│   ├── posted_tweets.log
│   └── errors.log
└── venv/                  # Virtual environment
```

## Setup

### 1. Clone and Setup Environment

```bash
cd ~/Documents/ClaudeProject/ScreenerAutomation
source venv/bin/activate
```

### 2. Configure Environment Variables

```bash
cp .env.example .env
# Edit .env with your credentials
```

Required variables:
- `SCREENER_USERNAME` / `SCREENER_PASSWORD` - Your Screener.in login
- `TWITTER_API_KEY` etc. - Twitter API v2 credentials

### 3. Install Ollama (for AI summaries)

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull Llama 3.1 model
ollama pull llama3.1
```

### 4. Test Run

```bash
# Dry run (no tweets posted)
python main.py --dry-run

# Full run with GUI visible
python main.py

# Headless mode (production)
python main.py --headless
```

## Scheduling (Local)

Add to crontab for 8 PM IST daily:

```bash
# Open crontab
crontab -e

# Add line:
0 20 * * * cd ~/Documents/ClaudeProject/ScreenerAutomation && source venv/bin/activate && python main.py --headless >> logs/cron.log 2>&1
```

## Cloud Hosting (Future)

For GitHub Actions (free):
- 2,000 minutes/month
- Built-in cron scheduling
- Secrets management

See `.github/workflows/` (to be created for cloud deployment).

## Logs

Check logs for debugging:

```bash
# Real-time log tail
tail -f logs/screener_automation.log

# Posted tweets
cat logs/posted_tweets.log

# Errors only
cat logs/errors.log
```

## Troubleshooting

**Ollama not responding?**
```bash
ollama serve  # Start server
ollama list   # Verify model loaded
```

**ChromeDriver issues?**
```bash
# Update webdriver-manager
pip install --upgrade webdriver-manager
```

**Twitter API errors?**
- Verify credentials in `.env`
- Check Twitter Developer Portal for rate limits

## Roadmap

- [ ] GitHub Actions workflow for cloud hosting
- [ ] SQLite database for result storage
- [ ] Email/Slack notifications as alternative to Twitter
- [ ] More robust AI analysis of results
- [ ] Support for additional data sources (Yahoo Finance, etc.)
