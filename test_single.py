#!/usr/bin/env python3
"""
Quick single-company test. Runs the full pipeline for one company
without posting to Twitter. Prints rich output to console.

Usage:
    python test_single.py skygold
"""
import sys

import subprocess
import config
from logger import app_logger
from browser_utils import get_chrome_driver, close_driver
from screener_client import ScreenerClient, Company
from orchestrator import ScreenerAgent
from analyzer import StockAnalyzer
from twitter_poster import format_alert_tweet
from email_sender import build_html_report


SEP  = "=" * 60
SEP2 = "-" * 60


def print_section(title, content):
    print(f"\n{SEP2}")
    print(f"  {title}")
    print(SEP2)
    print(content)


def test_company(company_code: str):
    company = Company(
        name=company_code.upper(),
        code=company_code.lower(),
        url=f"{config.SCREENER_BASE_URL}/company/{company_code.lower()}/consolidated/",
    )

    print(f"\n{SEP}")
    print(f"  SKYGOLD FULL ANALYSIS")
    print(SEP)

    driver = get_chrome_driver(headless=False)
    client = ScreenerClient(driver)
    analyzer = StockAnalyzer()

    try:
        if not client.login(config.SCREENER_USERNAME, config.SCREENER_PASSWORD):
            print("ERROR: Login failed")
            return

        # ── Quarterly Results ──────────────────────────────────────────────
        result = client.get_quarterly_results_with_trend(company)
        if not result:
            print("No quarterly results found.")
            return

        print_section("LATEST QUARTERLY RESULTS", f"""
  Company   : {result.company_name}
  Quarter   : {result.quarter}
  Sales     : ₹{result.sales} Cr      YoY: {result.sales_growth_yoy}
  Net Profit: ₹{result.net_profit} Cr     YoY: {result.profit_growth_yoy}
  Op. Profit: ₹{result.operating_profit or 'N/A'} Cr
  EPS       : ₹{result.eps or 'N/A'}""")

        # ── Trend ──────────────────────────────────────────────────────────
        if result.quarters_list and result.sales_trend and result.profit_trend:
            quarters  = result.quarters_list
            sales_t   = result.sales_trend
            profit_t  = result.profit_trend

            trend_text = f"\n  {'Quarter':<12} {'Sales':>10} {'Net Profit':>12}"
            trend_text += f"\n  {'-'*36}"
            for i, q in enumerate(quarters):
                s = sales_t[i]  if i < len(sales_t)  else "N/A"
                p = profit_t[i] if i < len(profit_t) else "N/A"
                marker = " ◄ latest" if i == len(quarters) - 1 else ""
                trend_text += f"\n  {q:<12} {s:>10} {p:>12}{marker}"

            # Trend direction
            sales_trend  = analyzer.analyze_trend("Sales",      sales_t,  quarters)
            profit_trend = analyzer.analyze_trend("Net Profit", profit_t, quarters)
            if sales_trend:
                trend_text += f"\n\n  Sales trend  : {sales_trend.direction.value.upper()} (avg growth {sales_trend.avg_growth:.1f}%)"
                trend_text += f"\n  {sales_trend.insight}"
            if profit_trend:
                trend_text += f"\n\n  Profit trend : {profit_trend.direction.value.upper()} (avg growth {profit_trend.avg_growth:.1f}%)"
                trend_text += f"\n  {profit_trend.insight}"

            print_section("3-QUARTER TREND", trend_text)

        # ── Transcript ─────────────────────────────────────────────────────
        agent = ScreenerAgent()
        current_insights, previous_insights, mgmt = agent.process_company_transcripts(
            client, company, result.quarters_list or []
        )

        if current_insights:
            print_section("CONCALL TRANSCRIPT SUMMARY", f"""
  {current_insights.summary}""")

            if current_insights.management_guidance:
                print_section("MANAGEMENT TARGETS & GUIDANCE", "\n".join(
                    f"  • {g}" for g in current_insights.management_guidance
                ))
            else:
                print_section("MANAGEMENT TARGETS & GUIDANCE", "  (none extracted — see summary above)")

            if current_insights.risks_challenges:
                print_section("RISKS & CHALLENGES", "\n".join(
                    f"  • {r}" for r in current_insights.risks_challenges
                ))
            else:
                print_section("RISKS & CHALLENGES", "  (not parsed — see summary above)")

            print_section("OUTLOOK", f"  {current_insights.outlook}")
        else:
            print_section("CONCALL TRANSCRIPT", "  No transcript found or summarization failed.")

        if mgmt:
            print_section("MANAGEMENT TRACK RECORD", f"""
  Delivery  : {mgmt.delivery_assessment}
  Consistency Score: {mgmt.consistency_score}/100
  {mgmt.narrative}""")

        # ── Twitter Alert Preview ───────────────────────────────────────────
        tweet = format_alert_tweet(result, current_insights)
        print_section(f"TWITTER ALERT PREVIEW  ({len(tweet)}/280 chars)", tweet)

        # ── Email Report ────────────────────────────────────────────────────
        st = analyzer.analyze_trend("Sales",      result.sales_trend,  result.quarters_list) if result.sales_trend  else None
        pt = analyzer.analyze_trend("Net Profit", result.profit_trend, result.quarters_list) if result.profit_trend else None

        html = build_html_report(result, current_insights, st, pt)
        preview_path = "/tmp/screener_report_preview.html"
        with open(preview_path, "w") as f:
            f.write(html)
        print_section("EMAIL REPORT", f"  HTML report saved → {preview_path}\n  Opening in browser...")
        subprocess.Popen(["open", preview_path])

        print(f"\n{SEP}\n")

    finally:
        close_driver(driver)


if __name__ == "__main__":
    code = sys.argv[1] if len(sys.argv) > 1 else "skygold"
    test_company(code)
