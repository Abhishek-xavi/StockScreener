"""
Stock analysis module for trend detection, financial metrics interpretation,
and management guidance tracking across quarters.
"""
import re
from dataclasses import dataclass
from typing import List, Optional, Dict, Tuple
from enum import Enum

from logger import app_logger


class TrendDirection(Enum):
    """Trend classification for metrics."""
    IMPROVING = "improving"
    DECLINING = "declining"
    STABLE = "stable"
    VOLATILE = "volatile"


@dataclass
class TrendAnalysis:
    """Analysis of metric trend over time."""
    metric_name: str
    values: List[float]
    quarters: List[str]
    direction: TrendDirection
    avg_growth: float
    latest_vs_avg: float
    insight: str


@dataclass
class GuidanceItem:
    """Single guidance item from management."""
    category: str  # "revenue", "profit", "expansion", "debt", "margin", etc.
    guidance_text: str
    target_value: Optional[str]
    timeframe: str


@dataclass
class ManagementAnalysis:
    """Analysis of management guidance and delivery."""
    previous_guidance: List[GuidanceItem]
    delivery_assessment: str  # "delivered", "partial", "missed", "exceeded"
    key_promises: List[str]
    fulfilled_promises: List[str]
    unfulfilled_promises: List[str]
    consistency_score: float  # 0-100
    narrative: str


@dataclass
class FinancialStory:
    """Combined narrative from numbers and transcript."""
    headline: str
    numbers_summary: str
    trend_summary: str
    current_transcript_summary: Optional[str]
    previous_transcript_summary: Optional[str]
    management_analysis: Optional[ManagementAnalysis]
    key_takeaways: List[str]
    outlook: str
    red_flags: List[str]


class StockAnalyzer:
    """Analyze stock financials and generate insights."""

    @staticmethod
    def parse_number(value: str) -> Optional[float]:
        """
        Parse numeric values with various formats.
        Supports: 1,234.56 | 1.2 Cr | 123% | (45) for negative
        """
        if not value or value in ["N/A", "-", "", " "]:
            return None

        # Remove commas
        cleaned = value.replace(",", "").strip()

        # Handle negative numbers in parentheses: (45) -> -45
        if cleaned.startswith("(") and cleaned.endswith(")"):
            cleaned = "-" + cleaned[1:-1]

        # Extract number and multiplier
        multiplier = 1
        if "cr" in cleaned.lower():
            multiplier = 1  # Already in crores
            cleaned = re.sub(r'(?i)cr', '', cleaned)
        elif "cr" in cleaned.lower():
            multiplier = 100  # Lakhs to crores conversion if needed
            cleaned = re.sub(r'(?i)lakh?s?', '', cleaned)

        # Remove % sign if present
        is_percentage = "%" in cleaned
        cleaned = cleaned.replace("%", "").strip()

        try:
            result = float(cleaned) * multiplier
            return result
        except ValueError:
            return None

    @classmethod
    def analyze_trend(cls, metric_name: str, values: List[str], quarters: List[str]) -> Optional[TrendAnalysis]:
        """
        Analyze trend for a specific metric over last N quarters.

        Args:
            metric_name: Name of the metric (e.g., "Sales", "Net Profit")
            values: List of string values from last N quarters (oldest first)
            quarters: Quarter labels corresponding to values

        Returns:
            TrendAnalysis object or None if insufficient data
        """
        parsed_values = [cls.parse_number(v) for v in values]
        parsed_values = [v for v in parsed_values if v is not None]

        if len(parsed_values) < 2:
            return None

        # Calculate growth rates between consecutive quarters
        growth_rates = []
        for i in range(1, len(parsed_values)):
            if parsed_values[i-1] != 0:
                growth = ((parsed_values[i] - parsed_values[i-1]) / abs(parsed_values[i-1])) * 100
                growth_rates.append(growth)

        if not growth_rates:
            return None

        avg_growth = sum(growth_rates) / len(growth_rates)
        latest_vs_avg = parsed_values[-1] - (sum(parsed_values[:-1]) / len(parsed_values[:-1]))

        # Determine trend direction
        positive_count = sum(1 for g in growth_rates if g > 0)
        negative_count = sum(1 for g in growth_rates if g < 0)

        if len(growth_rates) >= 3:
            if positive_count >= 2 and all(g > -10 for g in growth_rates):
                direction = TrendDirection.IMPROVING
            elif negative_count >= 2:
                direction = TrendDirection.DECLINING
            elif max(abs(g) for g in growth_rates) > 50:
                direction = TrendDirection.VOLATILE
            else:
                direction = TrendDirection.STABLE
        else:
            direction = TrendDirection.STABLE if abs(avg_growth) < 10 else (
                TrendDirection.IMPROVING if avg_growth > 0 else TrendDirection.DECLINING
            )

        # Generate insight
        if direction == TrendDirection.IMPROVING:
            insight = f"{metric_name} showing consistent growth, up {avg_growth:.1f}% on average"
        elif direction == TrendDirection.DECLINING:
            insight = f"{metric_name} under pressure, down {abs(avg_growth):.1f}% on average"
        elif direction == TrendDirection.VOLATILE:
            insight = f"{metric_name} highly volatile, unpredictable pattern"
        else:
            insight = f"{metric_name} stable with minor fluctuations"

        return TrendAnalysis(
            metric_name=metric_name,
            values=parsed_values,
            quarters=quarters,
            direction=direction,
            avg_growth=avg_growth,
            latest_vs_avg=latest_vs_avg,
            insight=insight
        )

    @classmethod
    def classify_performance(cls, sales_growth: Optional[float], profit_growth: Optional[float]) -> str:
        """
        Classify overall company performance.

        Returns:
            Performance classification string
        """
        if sales_growth is None and profit_growth is None:
            return "Data Unavailable"

        # Strong performance: both positive
        if (sales_growth and sales_growth > 15) and (profit_growth and profit_growth > 20):
            return "Strong Growth"

        # Profit focused: profit up, sales moderate
        if (profit_growth and profit_growth > 20) and (sales_growth and sales_growth > 0):
            return "Profit Expansion"

        # Revenue growth story
        if (sales_growth and sales_growth > 20) and (profit_growth and profit_growth > 0):
            return "Revenue Growth"

        # Margin pressure: sales up but profit down
        if (sales_growth and sales_growth > 0) and (profit_growth and profit_growth < 0):
            return "Margin Pressure"

        # Double decline
        if (sales_growth and sales_growth < 0) and (profit_growth and profit_growth < 0):
            return "Declining Performance"

        # Mixed/Stable
        if (sales_growth and abs(sales_growth) < 10) and (profit_growth and abs(profit_growth) < 10):
            return "Stable Performance"

        return "Mixed Signals"

    @classmethod
    def generate_red_flags(cls, sales_trend: Optional[TrendAnalysis],
                          profit_trend: Optional[TrendAnalysis]) -> List[str]:
        """Identify potential red flags from trends."""
        flags = []

        if sales_trend:
            if sales_trend.direction == TrendDirection.DECLINING:
                flags.append("📉 Revenue declining over last 3 quarters")
            if sales_trend.avg_growth < -20:
                flags.append("⚠️ Significant revenue contraction")

        if profit_trend:
            if profit_trend.direction == TrendDirection.DECLINING:
                flags.append("📉 Profitability under pressure")
            if profit_trend.avg_growth < -30:
                flags.append("⚠️ Sharp profit decline")

        # Divergence check
        if sales_trend and profit_trend:
            if (sales_trend.direction == TrendDirection.IMPROVING and
                profit_trend.direction == TrendDirection.DECLINING):
                flags.append("🔍 Margin compression: Sales up but Profits down")

        return flags


class ManagementTracker:
    """Track management guidance and assess delivery vs promises."""

    @staticmethod
    def extract_guidance_from_transcript(transcript_text: str, quarter: str) -> List[GuidanceItem]:
        """
        Extract management guidance from transcript using AI.

        Args:
            transcript_text: Full transcript text
            quarter: Quarter identifier

        Returns:
            List of GuidanceItem objects
        """
        # This will be populated by Ollama summarization
        # For now, return empty list (actual extraction happens in AI summarizer)
        return []

    @staticmethod
    def analyze_management_delivery(
        previous_quarter_summary: str,
        current_results: Dict[str, str],
        previous_quarter: str,
        current_quarter: str
    ) -> ManagementAnalysis:
        """
        Compare what management guided vs what they delivered.

        Args:
            previous_quarter_summary: AI summary of previous quarter transcript
            current_results: Current quarter results (sales, profit, etc.)
            previous_quarter: Previous quarter label
            current_quarter: Current quarter label

        Returns:
            ManagementAnalysis object
        """
        guidance_items = []
        fulfilled = []
        unfulfilled = []

        # Parse previous summary for guidance indicators
        guidance_keywords = [
            "guidance", "expect", "anticipate", "target", "aim", "goal",
            "project", "forecast", "outlook", "should be", "plan to",
            "next quarter", "coming quarter", "following quarter"
        ]

        summary_lower = previous_quarter_summary.lower()

        # Check for specific guidance patterns
        if any(kw in summary_lower for kw in guidance_keywords):
            # Extract sentences with guidance
            sentences = previous_quarter_summary.split('.')
            for sentence in sentences:
                sentence_lower = sentence.lower()
                if any(kw in sentence_lower for kw in guidance_keywords):
                    guidance_items.append(GuidanceItem(
                        category="general",
                        guidance_text=sentence.strip(),
                        target_value=None,
                        timeframe="next quarter"
                    ))

        # Compare with current results
        sales_growth = StockAnalyzer.parse_number(current_results.get("sales_growth", "0"))
        profit_growth = StockAnalyzer.parse_number(current_results.get("profit_growth", "0"))

        # Simple assessment logic
        if sales_growth and profit_growth:
            if sales_growth > 10 and profit_growth > 10:
                delivery = "delivered"
                fulfilled = ["Revenue growth", "Profit growth"]
            elif sales_growth > 0 and profit_growth > 0:
                delivery = "partial"
                fulfilled = ["Positive growth maintained"]
                unfulfilled = ["Growth below optimal targets"]
            else:
                delivery = "missed"
                unfulfilled = ["Growth targets not met"]
        else:
            delivery = "unknown"

        # Calculate consistency score
        consistency = 75 if delivery == "delivered" else (
            50 if delivery == "partial" else (
                25 if delivery == "missed" else 50
            )
        )

        # Build narrative
        if guidance_items:
            if delivery == "delivered":
                narrative = f"Management delivered on guidance from {previous_quarter}"
            elif delivery == "partial":
                narrative = f"Management partially delivered; some targets missed"
            elif delivery == "missed":
                narrative = f"Management missed guidance from {previous_quarter}"
            else:
                narrative = f"Unable to assess delivery against prior guidance"
        else:
            narrative = f"No specific guidance found in {previous_quarter} transcript"

        return ManagementAnalysis(
            previous_guidance=guidance_items,
            delivery_assessment=delivery,
            key_promises=[g.guidance_text for g in guidance_items],
            fulfilled_promises=fulfilled,
            unfulfilled_promises=unfulfilled,
            consistency_score=consistency,
            narrative=narrative
        )

    @classmethod
    def create_combined_transcript_summary(
        cls,
        current_summary: str,
        previous_summary: Optional[str],
        current_quarter: str,
        previous_quarter: Optional[str]
    ) -> str:
        """
        Create combined summary comparing current and previous quarter commentary.

        Args:
            current_summary: Current quarter transcript summary
            previous_summary: Previous quarter transcript summary
            current_quarter: Current quarter label
            previous_quarter: Previous quarter label

        Returns:
            Combined narrative
        """
        if not previous_summary:
            return current_summary

        # Extract key themes from both
        combined = f"{current_quarter}: {current_summary}\n\n"
        combined += f"vs {previous_quarter}: {previous_summary}"

        return combined


class FinancialStoryBuilder:
    """Build comprehensive financial story from all data sources."""

    @staticmethod
    def create_financial_story(
        company_name: str,
        quarter: str,
        sales: str,
        sales_yoy: str,
        profit: str,
        profit_yoy: str,
        eps: Optional[str] = None,
        sales_trend: Optional[TrendAnalysis] = None,
        profit_trend: Optional[TrendAnalysis] = None,
        current_transcript_summary: Optional[str] = None,
        previous_transcript_summary: Optional[str] = None,
        previous_quarter: Optional[str] = None,
        management_analysis: Optional[ManagementAnalysis] = None
    ) -> FinancialStory:
        """
        Create comprehensive financial story from all data sources.

        Args:
            company_name: Company name
            quarter: Current quarter
            sales, sales_yoy: Sales figures
            profit, profit_yoy: Profit figures
            eps: EPS if available
            sales_trend: Sales trend analysis
            profit_trend: Profit trend analysis
            current_transcript_summary: AI summary of current earnings transcript
            previous_transcript_summary: AI summary of previous earnings transcript
            previous_quarter: Previous quarter label
            management_analysis: Management guidance analysis

        Returns:
            FinancialStory object
        """
        # Parse growth numbers
        sales_growth = StockAnalyzer.parse_number(sales_yoy)
        profit_growth = StockAnalyzer.parse_number(profit_yoy)

        # Performance classification
        performance = StockAnalyzer.classify_performance(sales_growth, profit_growth)

        # Create headline
        emoji_map = {
            "Strong Growth": "🚀",
            "Profit Expansion": "💰",
            "Revenue Growth": "📈",
            "Margin Pressure": "⚠️",
            "Declining Performance": "📉",
            "Stable Performance": "⚖️",
            "Mixed Signals": "🔍",
            "Data Unavailable": "❓"
        }
        emoji = emoji_map.get(performance, "📊")
        headline = f"{emoji} {company_name} - {quarter}: {performance}"

        # Numbers summary
        numbers_summary = f"Sales: ₹{sales} (YoY {sales_yoy}) | Profit: ₹{profit} (YoY {profit_yoy})"
        if eps:
            numbers_summary += f" | EPS: ₹{eps}"

        # Trend summary
        trend_parts = []
        if sales_trend:
            trend_parts.append(sales_trend.insight)
        if profit_trend:
            trend_parts.append(profit_trend.insight)
        trend_summary = " | ".join(trend_parts) if trend_parts else "Trend analysis not available"

        # Key takeaways
        takeaways = []
        if sales_growth and sales_growth > 0:
            takeaways.append(f"Revenue grew {sales_growth:.1f}% YoY")
        if profit_growth and profit_growth > 0:
            takeaways.append(f"Profits up {profit_growth:.1f}% YoY")

        # Red flags
        red_flags = StockAnalyzer.generate_red_flags(sales_trend, profit_trend)

        # Outlook - combine management guidance with trend
        if management_analysis:
            outlook = management_analysis.narrative
            if current_transcript_summary:
                outlook += f" | Current: {current_transcript_summary[:100]}"
        elif current_transcript_summary:
            outlook = f"Management: {current_transcript_summary[:150]}"
        elif profit_trend and profit_trend.direction == TrendDirection.IMPROVING:
            outlook = "Positive momentum expected to continue"
        elif red_flags:
            outlook = "Monitor for recovery signs"
        else:
            outlook = "Stable outlook"

        return FinancialStory(
            headline=headline,
            numbers_summary=numbers_summary,
            trend_summary=trend_summary,
            current_transcript_summary=current_transcript_summary,
            previous_transcript_summary=previous_transcript_summary,
            management_analysis=management_analysis,
            key_takeaways=takeaways,
            outlook=outlook,
            red_flags=red_flags
        )

    @staticmethod
    def format_tweet_from_story(story: FinancialStory, max_length: int = 280) -> str:
        """
        Format FinancialStory into Twitter-friendly text.

        Args:
            story: FinancialStory object
            max_length: Maximum tweet length

        Returns:
            Formatted tweet text
        """
        lines = [story.headline, ""]
        lines.append(story.numbers_summary)

        if story.trend_summary and len("\n".join(lines)) < max_length - 60:
            lines.append("")
            lines.append(story.trend_summary)

        # Add management guidance assessment
        if story.management_analysis and len("\n".join(lines)) < max_length - 80:
            lines.append("")
            emoji = "✅" if story.management_analysis.delivery_assessment == "delivered" else (
                "⚠️" if story.management_analysis.delivery_assessment == "partial" else "❌"
            )
            lines.append(f"{emoji} {story.management_analysis.narrative}")

        # Add current transcript insights
        if story.current_transcript_summary and len("\n".join(lines)) < max_length - 100:
            lines.append("")
            lines.append(f"🎙️ {story.current_transcript_summary[:100]}...")

        if story.red_flags and len("\n".join(lines)) < max_length - 50:
            lines.append("")
            lines.append(f"⚠️ {story.red_flags[0]}")

        return "\n".join(lines)


# Keep backward compatibility
StockAnalyzer.create_financial_story = FinancialStoryBuilder.create_financial_story
StockAnalyzer.format_tweet_from_story = FinancialStoryBuilder.format_tweet_from_story
