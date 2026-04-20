"""
Main orchestrator for the Screener Automation Agent.
Coordinates scraping, trend analysis, transcript comparison, and posting workflow.
"""
import time
from datetime import datetime
from typing import List, Optional

import config
from logger import (
    app_logger,
    log_job_start,
    log_job_end,
)
from browser_utils import get_chrome_driver, close_driver
from screener_client import ScreenerClient, Company, QuarterlyResult, ConcallInfo
from twitter_poster import post_update, post_error_report, format_alert_tweet
from email_sender import send_report_email
from ai_summarizer import summarize_transcript, compare_quarterly_guidance, TranscriptInsights
from analyzer import (
    StockAnalyzer,
    TrendAnalysis,
    FinancialStory,
    FinancialStoryBuilder,
    ManagementTracker,
    ManagementAnalysis
)


class ScreenerAgent:
    """Main agent that runs the complete workflow with trend analysis and transcript comparison."""

    def __init__(self):
        self.results_found = 0
        self.companies_checked = 0
        self.transcripts_processed = 0
        self.errors = []
        self.analyzer = StockAnalyzer()
        self.tracker = ManagementTracker()
        self.story_builder = FinancialStoryBuilder()

    def process_company_transcripts(
        self,
        client: ScreenerClient,
        company: Company,
        quarters_list: List[str]
    ) -> tuple:
        """
        Process transcripts for current and previous quarters.

        Args:
            client: ScreenerClient
            company: Company
            quarters_list: List of quarters (last 3)

        Returns:
            Tuple of (current_insights, previous_insights, management_analysis)
        """
        current_quarter = quarters_list[-1]
        previous_quarter = quarters_list[-2] if len(quarters_list) >= 2 else None

        # Find concalls section via documents URL
        target_quarters = [q for q in [current_quarter, previous_quarter] if q]
        app_logger.info(f"Searching transcripts for {company.name}: {', '.join(target_quarters)}")
        concall_info = client.find_concalls_section(company, target_quarters)

        current_insights = None
        previous_insights = None

        # Process each transcript found
        for transcript in concall_info.transcripts:
            pdf_url = transcript.pdf_url
            link_element = getattr(transcript, "_link_element", None)

            transcript_text = None

            if pdf_url and pdf_url != "CLICKABLE" and pdf_url.startswith("http"):
                # Direct PDF URL — download and extract
                app_logger.info(f"Downloading transcript for {company.name} {transcript.quarter}...")
                transcript_text = client.download_and_extract_transcript(pdf_url)
            elif link_element is not None:
                # Transcript button opens a new window — click and extract
                app_logger.info(f"Clicking transcript button for {company.name} {transcript.quarter}...")
                transcript_text = client.click_and_extract_transcript(link_element)
            else:
                app_logger.warning(f"No PDF URL or clickable element for {transcript.quarter}, skipping")
                continue

            if transcript_text:
                app_logger.info(f"Summarizing {transcript.quarter} transcript ({len(transcript_text)} chars)...")
                insights = summarize_transcript(transcript_text, transcript.quarter)

                if insights:
                    self.transcripts_processed += 1
                    app_logger.info(f"✓ Transcript processed for {transcript.quarter}")
                    app_logger.debug(f"Summary: {insights.summary[:100]}...")
                    app_logger.debug(f"Guidance points: {len(insights.management_guidance)}")

                    if transcript.quarter == current_quarter:
                        current_insights = insights
                    elif transcript.quarter == previous_quarter:
                        previous_insights = insights
                    elif current_insights is None:
                        # Fallback transcript (e.g. latest concall doesn't match exact quarter)
                        current_insights = insights
                        app_logger.info(f"Using {transcript.quarter} transcript as current-quarter insights")
                else:
                    app_logger.warning(f"Failed to summarize {transcript.quarter} transcript")

        # If we have both quarters, compare management guidance
        management_analysis = None
        if current_insights and previous_insights and previous_quarter:
            app_logger.info(f"Comparing {previous_quarter} guidance vs {current_quarter} delivery...")

            # Get current results data for comparison
            current_results_data = {
                "sales_growth": "TBD",  # Will be populated from results
                "profit_growth": "TBD"
            }

            management_analysis = self.tracker.analyze_management_delivery(
                previous_quarter_summary=previous_insights.summary,
                current_results=current_results_data,
                previous_quarter=previous_quarter,
                current_quarter=current_quarter
            )

            # Enhance with AI comparison
            comparison = compare_quarterly_guidance(
                current_insights,
                previous_insights,
                current_quarter,
                previous_quarter
            )
            management_analysis.narrative = comparison

            app_logger.info(f"Management analysis: {management_analysis.narrative}")

        return current_insights, previous_insights, management_analysis

    def process_company(self, client: ScreenerClient, company: Company) -> bool:
        """
        Process a single company with full analysis pipeline:
        1. Get quarterly results with trend data
        2. Find and process current + previous quarter transcripts
        3. Analyze trends
        4. Compare management guidance vs delivery
        5. Generate financial story
        6. Post to Twitter

        Args:
            client: ScreenerClient instance
            company: Company to process

        Returns:
            True if results found and processed, False otherwise
        """
        # Step 1: Get quarterly results with trend data
        result = client.get_quarterly_results_with_trend(company)

        if not result:
            app_logger.info(f"No results found for {company.name}")
            return False

        # Step 2: Analyze trends
        sales_trend = None
        profit_trend = None

        if result.sales_trend and result.quarters_list:
            sales_trend = self.analyzer.analyze_trend(
                "Sales", result.sales_trend, result.quarters_list
            )
            if sales_trend:
                app_logger.info(f"{company.name} Sales: {sales_trend.direction.value} ({sales_trend.avg_growth:.1f}%)")

        if result.profit_trend and result.quarters_list:
            profit_trend = self.analyzer.analyze_trend(
                "Net Profit", result.profit_trend, result.quarters_list
            )
            if profit_trend:
                app_logger.info(f"{company.name} Profit: {profit_trend.direction.value} ({profit_trend.avg_growth:.1f}%)")

        # Step 3: Process transcripts (current + previous quarter)
        current_quarter = result.quarter
        previous_quarter = result.quarters_list[-2] if len(result.quarters_list) >= 2 else None

        current_insights, previous_insights, management_analysis = self.process_company_transcripts(
            client, company, result.quarters_list
        )

        # Step 4: Generate comprehensive financial story
        story = self.story_builder.create_financial_story(
            company_name=company.name,
            quarter=result.quarter,
            sales=result.sales,
            sales_yoy=result.sales_growth_yoy,
            profit=result.net_profit,
            profit_yoy=result.profit_growth_yoy,
            eps=result.eps,
            sales_trend=sales_trend,
            profit_trend=profit_trend,
            current_transcript_summary=current_insights.summary if current_insights else None,
            previous_transcript_summary=previous_insights.summary if previous_insights else None,
            previous_quarter=previous_quarter,
            management_analysis=management_analysis
        )

        # Step 5: Log the full analysis
        app_logger.info(f"\n{'='*60}")
        app_logger.info(f"FINANCIAL STORY: {company.name}")
        app_logger.info(f"{'='*60}")
        app_logger.info(f"Headline: {story.headline}")
        app_logger.info(f"Numbers: {story.numbers_summary}")
        app_logger.info(f"Trend: {story.trend_summary}")

        if story.current_transcript_summary:
            app_logger.info(f"Current Transcript: {story.current_transcript_summary[:150]}...")

        if story.previous_transcript_summary:
            app_logger.info(f"Previous Transcript: {story.previous_transcript_summary[:150]}...")

        if story.management_analysis:
            app_logger.info(f"Management Track Record: {story.management_analysis.narrative}")
            app_logger.info(f"Consistency Score: {story.management_analysis.consistency_score}/100")

        if story.red_flags:
            app_logger.warning(f"Red Flags: {story.red_flags}")

        app_logger.info(f"{'='*60}\n")

        # Step 6: Post Twitter alert + send email (skipped in dry-run)
        tweet_text = format_alert_tweet(result, current_insights)
        app_logger.info(f"Tweet preview:\n{tweet_text}")

        if getattr(self, "dry_run", False):
            app_logger.info("DRY-RUN: skipping tweet and email")
            self.results_found += 1
            return True

        tweet_ok = post_update(
            company=result.company_name,
            quarter=result.quarter,
            text=tweet_text
        )

        email_ok = send_report_email(
            result=result,
            insights=current_insights,
            sales_trend=sales_trend,
            profit_trend=profit_trend,
        )

        if tweet_ok or email_ok:
            self.results_found += 1
            return True
        else:
            self.errors.append((company.name, "Failed to post tweet and send email"))
            return False

    def run(self, headless: bool = False, dry_run: bool = False) -> bool:
        """
        Execute the complete agent workflow.
        headless: run Chrome without GUI (required in CI)
        dry_run: skip posting tweets and emails
        """
        log_job_start()
        self.results_found = 0
        self.companies_checked = 0
        self.transcripts_processed = 0
        self.errors = []
        self.dry_run = dry_run

        driver = None
        success = True

        try:
            driver = get_chrome_driver(headless=headless)
            client = ScreenerClient(driver)

            # Login
            if not client.login(config.SCREENER_USERNAME, config.SCREENER_PASSWORD):
                app_logger.error("Failed to login - aborting job")
                return False

            # Get watchlist (DYNAMIC - fetches whatever is in your screener watchlist)
            companies = client.get_watchlist_companies()
            if not companies:
                app_logger.warning("No companies found in watchlist")
                return True

            app_logger.info(f"Processing {len(companies)} companies from watchlist...")
            app_logger.info(f"Watchlist: {', '.join([c.name for c in companies])}")

            # Process each company
            for company in companies:
                self.companies_checked += 1

                try:
                    self.process_company(client, company)
                except Exception as e:
                    app_logger.error(f"Unexpected error processing {company.name}: {e}")
                    self.errors.append((company.name, str(e)))

                # Delay between companies
                time.sleep(config.REQUEST_DELAY)

            # Collect scraping errors
            self.errors.extend(client.get_errors())

        except Exception as e:
            app_logger.error(f"Critical error during job: {e}")
            success = False
        finally:
            if driver:
                close_driver(driver)

        # Post error report
        if self.errors:
            post_error_report(self.errors)

        # Job summary
        app_logger.info("\n" + "=" * 60)
        app_logger.info("JOB SUMMARY")
        app_logger.info(f"Companies checked: {self.companies_checked}")
        app_logger.info(f"Results found & posted: {self.results_found}")
        app_logger.info(f"Transcripts processed: {self.transcripts_processed}")
        app_logger.info(f"Errors: {len(self.errors)}")
        app_logger.info("=" * 60)

        log_job_end(success, self.companies_checked, self.results_found)
        return success


def main(headless: bool = False, dry_run: bool = False):
    """Entry point for running the agent."""
    agent = ScreenerAgent()
    agent.run(headless=headless, dry_run=dry_run)


if __name__ == "__main__":
    main()
