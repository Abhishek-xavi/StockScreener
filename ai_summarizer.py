"""
AI Summarization for earnings call transcripts.
Primary: Claude API (Anthropic) — accurate, structured.
Fallback: local Ollama — free, runs offline.
"""
import requests
from typing import Optional, List
from dataclasses import dataclass

import config
from logger import app_logger


@dataclass
class TranscriptInsights:
    """Structured insights from transcript."""
    summary: str
    key_highlights: List[str]
    management_guidance: List[str]   # "metric: target | status: X" lines
    risks_challenges: List[str]
    outlook: str
    guidance_vs_delivery: Optional[str] = None


# ── Shared prompt & parser ────────────────────────────────────────────────────

def _build_prompt(text: str, quarter: str) -> str:
    return f"""You are a careful financial analyst reviewing an earnings call transcript.

Your job is to extract information ONLY from what is explicitly stated in the transcript.
Do NOT invent numbers. Do NOT confuse PAT/profit with Revenue/Sales. Use the exact metric name as spoken.

Read this {quarter} earnings call transcript and respond using ONLY these four section headers, in order:

SUMMARY:
2-3 sentences describing overall business performance this quarter.

TARGETS:
List every specific quantitative target or commitment management made.
Rules:
- Each line: [exact metric name as stated]: [exact target value] by [timeframe] | status: [on track / ahead / behind / unclear]
- Use the EXACT metric label from the transcript (e.g. "PAT", "Revenue", "EBITDA margin", "store count")
- If a number seems inconsistent with current performance, double-check the metric label before writing it
- Skip any target that has no specific number or percentage
- If no targets were stated, write: none

RISKS:
Key risks or challenges explicitly mentioned. One per line starting with -.
If none mentioned, write: none

OUTLOOK:
One sentence on management's stated expectation for the next quarter or year.

Current quarter actual numbers for reference (use these to assess "on track" status):
- Quarter: {quarter}

Transcript:
{text}

Answer (use the four headers above, nothing else):"""


def _parse_response(response: str, quarter: str) -> "TranscriptInsights":
    """Parse the structured AI response into TranscriptInsights."""
    summary_lines = []
    targets = []
    risks = []
    outlook = ""
    current_section = None

    for line in response.split("\n"):
        line = line.strip()
        if not line:
            continue

        # Normalise headers — handle plain, markdown bold, with/without colon
        clean = line.strip("*").strip().upper().rstrip(":")

        if clean == "SUMMARY":
            current_section = "summary"
            rest = line.strip("*").strip()[len("SUMMARY"):].lstrip(":").strip()
            if rest:
                summary_lines.append(rest)
        elif clean == "TARGETS":
            current_section = "targets"
        elif clean == "RISKS":
            current_section = "risks"
        elif clean == "OUTLOOK":
            current_section = "outlook"
            rest = line.strip("*").strip()[len("OUTLOOK"):].lstrip(":").strip()
            if rest:
                outlook = rest
        elif line.startswith(("-", "•", "*")):
            item = line.lstrip("-•* ").strip()
            if not item or item.lower() == "none":
                continue
            if current_section == "targets":
                targets.append(item)
            elif current_section == "risks":
                risks.append(item)
        else:
            if current_section == "summary":
                summary_lines.append(line)
            elif current_section == "targets" and line.lower() != "none":
                # Claude sometimes writes targets as plain lines without bullet prefix
                targets.append(line)
            elif current_section == "risks" and line.lower() != "none":
                risks.append(line)
            elif current_section == "outlook" and not outlook:
                outlook = line

    summary = " ".join(summary_lines).strip() or response[:300]

    return TranscriptInsights(
        summary=summary,
        key_highlights=[],
        management_guidance=targets,
        risks_challenges=risks,
        outlook=outlook or "See transcript for details",
    )


# ── Claude API summarizer ─────────────────────────────────────────────────────

class ClaudeSummarizer:
    """Summarizer using Anthropic Claude API."""

    def __init__(self):
        self._client = None

    def is_available(self) -> bool:
        return bool(config.ANTHROPIC_API_KEY)

    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        return self._client

    def summarize_transcript(self, text: str, quarter: str) -> Optional[TranscriptInsights]:
        if not self.is_available():
            return None

        # Claude Haiku context window is ~180k tokens (~140k chars) — send full transcript
        MAX_CHARS = 140_000
        if len(text) > MAX_CHARS:
            app_logger.warning(f"Transcript very long ({len(text)} chars), truncating to {MAX_CHARS}")
            text = text[:MAX_CHARS] + "... [truncated]"

        try:
            client = self._get_client()
            message = client.messages.create(
                model=config.ANTHROPIC_MODEL,
                max_tokens=1024,
                messages=[{"role": "user", "content": _build_prompt(text, quarter)}]
            )
            response = message.content[0].text.strip()
            app_logger.info(f"Claude API used ({message.usage.input_tokens} in / {message.usage.output_tokens} out tokens)")
            app_logger.debug(f"Claude response:\n{response}")
            return _parse_response(response, quarter)

        except Exception as e:
            app_logger.error(f"Claude API error: {e}")
            return None

    def compare_quarters(self, current: TranscriptInsights, previous: TranscriptInsights,
                         current_q: str, previous_q: str) -> str:
        if not self.is_available():
            return f"Unable to compare {previous_q} vs {current_q}"

        prompt = f"""You are a financial analyst. Compare management commentary across two quarters.

{previous_q} targets set by management:
{chr(10).join(['- ' + g for g in previous.management_guidance]) or '- none recorded'}

{previous_q} outlook stated:
{previous.outlook}

{current_q} actual performance summary:
{current.summary}

{current_q} risks now mentioned:
{chr(10).join(['- ' + r for r in current.risks_challenges]) or '- none'}

In 2-3 sentences: Did management deliver on what they promised in {previous_q}?
What has changed in their narrative? Be specific about any targets met or missed."""

        try:
            client = self._get_client()
            message = client.messages.create(
                model=config.ANTHROPIC_MODEL,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}]
            )
            return message.content[0].text.strip()
        except Exception as e:
            app_logger.error(f"Claude API compare error: {e}")
            return f"Unable to compare {previous_q} vs {current_q}"


# ── Ollama summarizer (fallback) ──────────────────────────────────────────────

class OllamaSummarizer:
    """Fallback summarizer using local Ollama."""

    def __init__(self):
        self.model = config.OLLAMA_MODEL
        self.host = config.OLLAMA_HOST
        self._available = None

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            response = requests.get(f"{self.host}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get("models", [])
                names = [m["name"] for m in models]
                self._available = any(
                    m == self.model or m.startswith(self.model + ":") or self.model.startswith(m.split(":")[0])
                    for m in names
                )
                level = "info" if self._available else "warning"
                msg = f"Ollama ready: {self.model}" if self._available else f"Ollama running but {self.model} not found"
                getattr(app_logger, level)(msg)
                return self._available
        except Exception as e:
            app_logger.warning(f"Ollama not available: {e}")
            self._available = False
            return False

    def _call(self, prompt: str, max_tokens: int = 500) -> Optional[str]:
        if not self.is_available():
            return None
        try:
            response = requests.post(
                f"{self.host}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False,
                      "options": {"temperature": 0.1, "num_predict": max_tokens}},
                timeout=90
            )
            response.raise_for_status()
            return response.json().get("response", "").strip()
        except Exception as e:
            app_logger.error(f"Ollama error: {e}")
            return None

    def summarize_transcript(self, text: str, quarter: str) -> Optional[TranscriptInsights]:
        # Ollama local models degrade on very long context — cap at 12k chars
        if len(text) > 12000:
            app_logger.warning(f"Ollama: truncating transcript to 12,000 chars (was {len(text)})")
            text = text[:12000] + "... [truncated]"
        response = self._call(_build_prompt(text, quarter))
        if not response:
            return None
        app_logger.debug(f"Ollama response:\n{response}")
        insights = _parse_response(response, quarter)
        if not insights.management_guidance and not insights.risks_challenges \
                and insights.outlook == "See transcript for details":
            insights.summary = response.strip()
        return insights

    def compare_quarters(self, current: TranscriptInsights, previous: TranscriptInsights,
                         current_q: str, previous_q: str) -> str:
        prompt = f"""Compare management commentary: {previous_q} promises vs {current_q} delivery.

{previous_q} targets: {chr(10).join(['- ' + g for g in previous.management_guidance]) or 'none'}
{previous_q} outlook: {previous.outlook}
{current_q} summary: {current.summary}

In 2-3 sentences: were targets met? What changed in their narrative?"""
        return self._call(prompt, max_tokens=200) or f"Unable to compare {previous_q} vs {current_q}"


# ── Unified summarizer: Claude first, Ollama fallback ────────────────────────

class AISummarizer:
    """Uses Claude API if key is set, falls back to Ollama."""

    def __init__(self):
        self._claude = ClaudeSummarizer()
        self._ollama = OllamaSummarizer()

    def _active(self):
        if self._claude.is_available():
            return self._claude, "Claude API"
        if self._ollama.is_available():
            return self._ollama, "Ollama"
        return None, None

    def summarize_transcript(self, text: str, quarter: str) -> Optional[TranscriptInsights]:
        backend, name = self._active()
        if not backend:
            app_logger.error("No AI backend available (no ANTHROPIC_API_KEY and Ollama not running)")
            return None
        app_logger.info(f"Summarizing with {name}...")
        return backend.summarize_transcript(text, quarter)

    def compare_quarters(self, current: TranscriptInsights, previous: TranscriptInsights,
                         current_q: str, previous_q: str) -> str:
        backend, _ = self._active()
        if not backend:
            return f"Unable to compare {previous_q} vs {current_q}"
        return backend.compare_quarters(current, previous, current_q, previous_q)

    # Keep legacy method names used by orchestrator/analyzer
    def analyze_management_consistency(self, transcript_text: str, quarter: str) -> Optional[str]:
        return None  # Covered by summarize_transcript now


# Global instance
summarizer = AISummarizer()


def summarize_transcript(text: str, quarter: str) -> Optional[TranscriptInsights]:
    return summarizer.summarize_transcript(text, quarter)


def compare_quarterly_guidance(current: TranscriptInsights, previous: TranscriptInsights,
                                current_q: str, previous_q: str) -> str:
    return summarizer.compare_quarters(current, previous, current_q, previous_q)
