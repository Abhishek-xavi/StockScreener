"""
HTML email report sender via Gmail SMTP.
Generates a rich, mobile-friendly report with trend charts and guidance scorecard.
"""
import smtplib
import base64
import io
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from typing import Optional, List

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

import config
from logger import app_logger
from screener_client import QuarterlyResult
from ai_summarizer import TranscriptInsights
from analyzer import TrendAnalysis


# ── Chart generation ──────────────────────────────────────────────────────────

def _make_trend_chart(quarters: List[str], sales: List[str], profits: List[str]) -> str:
    """Generate a dual-axis bar+line trend chart. Returns base64 PNG string."""

    def _parse(vals):
        result = []
        for v in vals:
            try:
                result.append(float(v.replace(",", "").replace(" ", "")))
            except Exception:
                result.append(0.0)
        return result

    s_vals = _parse(sales)
    p_vals = _parse(profits)
    x = np.arange(len(quarters))

    fig, ax1 = plt.subplots(figsize=(6, 3.2))
    fig.patch.set_facecolor("#f9f9f9")
    ax1.set_facecolor("#f9f9f9")

    # Sales bars
    bars = ax1.bar(x, s_vals, color="#2563eb", alpha=0.85, width=0.5, zorder=3)
    ax1.set_ylabel("Sales (₹ Cr)", color="#2563eb", fontsize=9)
    ax1.tick_params(axis="y", labelcolor="#2563eb", labelsize=8)
    ax1.set_xticks(x)
    ax1.set_xticklabels(quarters, fontsize=9)
    ax1.yaxis.grid(True, linestyle="--", alpha=0.4, zorder=0)
    ax1.set_axisbelow(True)

    # Value labels on bars
    for bar, val in zip(bars, s_vals):
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(s_vals) * 0.02,
                 f"₹{val:,.0f}", ha="center", va="bottom", fontsize=8, color="#2563eb", fontweight="bold")

    # Profit line on secondary axis
    ax2 = ax1.twinx()
    ax2.plot(x, p_vals, color="#16a34a", marker="o", linewidth=2.5, markersize=7, zorder=4)
    ax2.set_ylabel("Net Profit (₹ Cr)", color="#16a34a", fontsize=9)
    ax2.tick_params(axis="y", labelcolor="#16a34a", labelsize=8)

    for xi, val in zip(x, p_vals):
        ax2.text(xi, val + max(p_vals) * 0.06, f"₹{val:,.0f}",
                 ha="center", va="bottom", fontsize=8, color="#16a34a", fontweight="bold")

    # Legend
    legend_handles = [
        mpatches.Patch(color="#2563eb", alpha=0.85, label="Sales"),
        mpatches.Patch(color="#16a34a", label="Net Profit"),
    ]
    fig.legend(handles=legend_handles, loc="upper left", bbox_to_anchor=(0.08, 0.95),
               fontsize=8, framealpha=0.7)

    plt.title("Quarterly Trend", fontsize=10, fontweight="bold", pad=10, color="#374151")
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=120, bbox_inches="tight", facecolor="#f9f9f9")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


# ── Guidance helpers ──────────────────────────────────────────────────────────

def _status_badge(status: str) -> str:
    s = status.lower()
    if "ahead" in s:
        return "🟢 Ahead"
    if "on track" in s or "on_track" in s:
        return "✅ On Track"
    if "behind" in s:
        return "🔴 Behind"
    return "🟡 Unclear"


def _target_rows(targets: List[str]) -> str:
    if not targets:
        return "<tr><td colspan='3' style='color:#6b7280;padding:8px'>No specific targets recorded</td></tr>"
    rows = ""
    for t in targets:
        # Format: "Metric: value by timeframe | status: X"
        if "|" in t:
            left, right = t.split("|", 1)
            status_raw = right.replace("status:", "").strip()
            badge = _status_badge(status_raw)
        else:
            left = t
            badge = "🟡 Unclear"

        if ":" in left:
            metric, detail = left.split(":", 1)
        else:
            metric, detail = left, ""

        rows += f"""
        <tr>
          <td style="padding:7px 10px;border-bottom:1px solid #e5e7eb;font-weight:600;color:#111827;white-space:nowrap">{metric.strip()}</td>
          <td style="padding:7px 10px;border-bottom:1px solid #e5e7eb;color:#374151">{detail.strip()}</td>
          <td style="padding:7px 10px;border-bottom:1px solid #e5e7eb;white-space:nowrap">{badge}</td>
        </tr>"""
    return rows


# ── HTML template ─────────────────────────────────────────────────────────────

def build_html_report(
    result: QuarterlyResult,
    insights: Optional[TranscriptInsights],
    sales_trend_analysis: Optional[TrendAnalysis] = None,
    profit_trend_analysis: Optional[TrendAnalysis] = None,
) -> str:

    # Trend chart
    chart_b64 = ""
    if result.sales_trend and result.profit_trend and result.quarters_list:
        try:
            chart_b64 = _make_trend_chart(result.quarters_list, result.sales_trend, result.profit_trend)
        except Exception as e:
            app_logger.warning(f"Chart generation failed: {e}")

    chart_html = (
        f'<img src="data:image/png;base64,{chart_b64}" style="width:100%;max-width:560px;border-radius:8px" alt="Trend Chart">'
        if chart_b64 else ""
    )

    # YoY colour
    def yoy_colour(yoy: str) -> str:
        if yoy and yoy.startswith("+"):
            return "#16a34a"
        if yoy and yoy.startswith("-"):
            return "#dc2626"
        return "#374151"

    sy_col = yoy_colour(result.sales_growth_yoy)
    py_col = yoy_colour(result.profit_growth_yoy)

    # Trend direction pill
    def trend_pill(t: Optional[TrendAnalysis]) -> str:
        if not t:
            return ""
        colour = {"improving": "#16a34a", "declining": "#dc2626",
                  "stable": "#d97706", "volatile": "#7c3aed"}.get(t.direction.value, "#6b7280")
        label = t.direction.value.upper()
        return (f'<span style="background:{colour};color:#fff;padding:2px 8px;'
                f'border-radius:12px;font-size:11px;font-weight:600">{label}</span>')

    # Risks list
    risks_html = ""
    if insights and insights.risks_challenges:
        items = "".join(f"<li style='margin-bottom:6px;color:#374151'>{r}</li>"
                        for r in insights.risks_challenges)
        risks_html = f"<ul style='padding-left:20px;margin:0'>{items}</ul>"
    else:
        risks_html = "<p style='color:#6b7280;margin:0'>No specific risks flagged.</p>"

    # Outlook
    outlook_text = (insights.outlook if insights and insights.outlook != "See transcript for details"
                    else "Not available.")

    # Summary
    summary_text = insights.summary if insights else "Transcript not available."

    # Targets table
    targets_html = _target_rows(insights.management_guidance if insights else [])

    # Trend insight lines
    sales_insight = sales_trend_analysis.insight if sales_trend_analysis else ""
    profit_insight = profit_trend_analysis.insight if profit_trend_analysis else ""

    generated = datetime.now().strftime("%d %b %Y, %I:%M %p")

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
<div style="max-width:600px;margin:24px auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08)">

  <!-- Header -->
  <div style="background:linear-gradient(135deg,#1e3a5f,#2563eb);padding:24px 28px;color:#fff">
    <div style="font-size:22px;font-weight:700;letter-spacing:0.5px">{result.company_name}</div>
    <div style="font-size:14px;opacity:0.85;margin-top:4px">{result.quarter} Earnings Report &nbsp;·&nbsp; Generated {generated}</div>
  </div>

  <!-- Key Numbers -->
  <div style="padding:20px 28px 0">
    <div style="font-size:13px;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:12px">Key Numbers</div>
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td width="50%" style="padding-right:8px">
          <div style="background:#f0f7ff;border-radius:10px;padding:14px 16px">
            <div style="font-size:11px;color:#6b7280;font-weight:600;text-transform:uppercase">Sales</div>
            <div style="font-size:22px;font-weight:700;color:#111827;margin:4px 0">₹{result.sales} Cr</div>
            <div style="font-size:13px;font-weight:600;color:{sy_col}">YoY {result.sales_growth_yoy} &nbsp;{trend_pill(sales_trend_analysis)}</div>
            <div style="font-size:11px;color:#9ca3af;margin-top:3px">{sales_insight}</div>
          </div>
        </td>
        <td width="50%" style="padding-left:8px">
          <div style="background:#f0fdf4;border-radius:10px;padding:14px 16px">
            <div style="font-size:11px;color:#6b7280;font-weight:600;text-transform:uppercase">Net Profit</div>
            <div style="font-size:22px;font-weight:700;color:#111827;margin:4px 0">₹{result.net_profit} Cr</div>
            <div style="font-size:13px;font-weight:600;color:{py_col}">YoY {result.profit_growth_yoy} &nbsp;{trend_pill(profit_trend_analysis)}</div>
            <div style="font-size:11px;color:#9ca3af;margin-top:3px">{profit_insight}</div>
          </div>
        </td>
      </tr>
      <tr><td colspan="2" style="padding-top:8px"></td></tr>
      <tr>
        <td width="50%" style="padding-right:8px">
          <div style="background:#fafafa;border:1px solid #e5e7eb;border-radius:10px;padding:12px 16px">
            <div style="font-size:11px;color:#6b7280;font-weight:600;text-transform:uppercase">Operating Profit</div>
            <div style="font-size:18px;font-weight:700;color:#111827;margin-top:4px">₹{result.operating_profit or 'N/A'} Cr</div>
          </div>
        </td>
        <td width="50%" style="padding-left:8px">
          <div style="background:#fafafa;border:1px solid #e5e7eb;border-radius:10px;padding:12px 16px">
            <div style="font-size:11px;color:#6b7280;font-weight:600;text-transform:uppercase">EPS</div>
            <div style="font-size:18px;font-weight:700;color:#111827;margin-top:4px">₹{result.eps or 'N/A'}</div>
          </div>
        </td>
      </tr>
    </table>
  </div>

  <!-- Trend Chart -->
  <div style="padding:20px 28px 0">
    <div style="font-size:13px;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:12px">3-Quarter Trend</div>
    {chart_html}
  </div>

  <!-- Concall Summary -->
  <div style="padding:20px 28px 0">
    <div style="font-size:13px;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:10px">Management Commentary</div>
    <div style="background:#fffbeb;border-left:4px solid #f59e0b;padding:12px 16px;border-radius:0 8px 8px 0;font-size:14px;color:#374151;line-height:1.6">
      {summary_text}
    </div>
  </div>

  <!-- Management Targets -->
  <div style="padding:20px 28px 0">
    <div style="font-size:13px;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:10px">Guidance Scorecard</div>
    <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;border-collapse:collapse">
      <tr style="background:#f9fafb">
        <th style="padding:8px 10px;text-align:left;font-size:11px;color:#6b7280;font-weight:700;text-transform:uppercase;border-bottom:1px solid #e5e7eb">Metric</th>
        <th style="padding:8px 10px;text-align:left;font-size:11px;color:#6b7280;font-weight:700;text-transform:uppercase;border-bottom:1px solid #e5e7eb">Target</th>
        <th style="padding:8px 10px;text-align:left;font-size:11px;color:#6b7280;font-weight:700;text-transform:uppercase;border-bottom:1px solid #e5e7eb">Status</th>
      </tr>
      {targets_html}
    </table>
  </div>

  <!-- Risks -->
  <div style="padding:20px 28px 0">
    <div style="font-size:13px;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:10px">⚠️ Key Risks</div>
    <div style="background:#fff5f5;border-radius:8px;padding:14px 16px">
      {risks_html}
    </div>
  </div>

  <!-- Outlook -->
  <div style="padding:20px 28px 24px">
    <div style="font-size:13px;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:10px">🔭 Outlook</div>
    <div style="background:#f0fdf4;border-radius:8px;padding:14px 16px;font-size:14px;color:#374151;line-height:1.6">
      {outlook_text}
    </div>
  </div>

  <!-- Footer -->
  <div style="background:#f9fafb;border-top:1px solid #e5e7eb;padding:14px 28px;text-align:center">
    <div style="font-size:11px;color:#9ca3af">Generated by ScreenerBot &nbsp;·&nbsp; Data from Screener.in &nbsp;·&nbsp; Not investment advice</div>
  </div>

</div>
</body>
</html>"""

    return html


# ── Gmail sender ──────────────────────────────────────────────────────────────

def send_report_email(
    result: QuarterlyResult,
    insights: Optional[TranscriptInsights],
    sales_trend: Optional[TrendAnalysis] = None,
    profit_trend: Optional[TrendAnalysis] = None,
) -> bool:
    """Build and send the HTML report email via Gmail."""
    if not config.GMAIL_FROM or not config.GMAIL_APP_PASSWORD:
        app_logger.warning("Gmail not configured — skipping email (set GMAIL_FROM and GMAIL_APP_PASSWORD in .env)")
        return False

    try:
        html = build_html_report(result, insights, sales_trend, profit_trend)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"📊 {result.company_name} | {result.quarter} Earnings Report"
        msg["From"] = config.GMAIL_FROM
        msg["To"] = config.GMAIL_TO or config.GMAIL_FROM

        msg.attach(MIMEText(
            f"{result.company_name} {result.quarter} — Sales ₹{result.sales} Cr ({result.sales_growth_yoy} YoY), "
            f"Profit ₹{result.net_profit} Cr ({result.profit_growth_yoy} YoY)",
            "plain"
        ))
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(config.GMAIL_FROM, config.GMAIL_APP_PASSWORD)
            server.send_message(msg)

        app_logger.info(f"📧 Email sent for {result.company_name} {result.quarter}")
        return True

    except Exception as e:
        app_logger.error(f"Email send failed: {e}")
        return False
