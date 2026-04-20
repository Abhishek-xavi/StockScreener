# Screener Automation Agent - Algorithm Documentation

## Overview

This agent monitors your Screener.in watchlist for quarterly results, analyzes trends across 3 quarters, fetches earnings transcripts, and posts comprehensive analysis to Twitter.

---

## Algorithm Flow

```
START
  │
  ▼
┌─────────────────────┐
│ 1. LOGIN TO SCREENER│
│   - Authenticate      │
│   - Session cookies   │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 2. FETCH WATCHLIST  │
│   - Get ALL dynamic │
│     companies       │
│   - No limit on qty │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 3. FOR EACH COMPANY │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────────────┐
│ A. SCRAPE QUARTERLY RESULTS │
│   - Navigate to company page  │
│   - Find "Quarters" table     │
│   - Extract LAST 3 quarters:  │
│     Q1 (oldest) → Q2 → Q3   │
│     (current)                 │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ B. EXTRACT RAW DATA         │
│   - Sales: [Q1, Q2, Q3]     │
│   - Profit: [Q1, Q2, Q3]    │
│   - YoY Growth: Q3 only       │
│   - EPS: Q3 only              │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ C. TREND ANALYSIS           │
│   For Sales & Profit:         │
│   - Parse values to numbers   │
│   - Calculate Q→Q growth      │
│   - Determine direction:      │
│     ├─ IMPROVING (2+ up)    │
│     ├─ DECLINING (2+ down)  │
│     ├─ VOLATILE (wild swings)│
│     └─ STABLE (flat)          │
│   - Avg growth %              │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ D. FIND CONCALLS SECTION    │
│   - Look for "Concalls"     │
│     section on company page │
│   - Find Transcript links   │
│   - Get CURRENT quarter     │
│   - Get PREVIOUS quarter    │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ E. DOWNLOAD TRANSCRIPTS     │
│   For both quarters:        │
│   - Download PDF            │
│   - Extract text            │
│   - Send to Ollama          │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ F. AI ANALYSIS              │
│   For each transcript:      │
│   - Summary of highlights   │
│   - Management GUIDANCE     │
│   - Risks/challenges        │
│   - Forward outlook         │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ G. MANAGEMENT TRACK RECORD  │
│   Compare Previous vs Now:│
│   - What did they promise?  │
│   - Did they deliver?       │
│   - Consistency score       │
│   ├─ ✅ Delivered          │
│   ├─ ⚠️ Partial            │
│   └─ ❌ Missed             │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ H. GENERATE FINANCIAL STORY │
│   Combine:                  │
│   ├─ Numbers (Sales/Profit) │
│   ├─ YoY Growth %           │
│   ├─ 3-Q Trend Direction    │
│   ├─ Current Transcript     │
│   ├─ Previous Transcript    │
│   ├─ Management Delivery    │
│   └─ Red Flags              │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ I. POST TO TWITTER          │
│   Format:                   │
│   📊 Company - Q: Category  │
│   Sales: ₹X (YoY: Y%)       │
│   Profit: ₹X (YoY: Y%)      │
│   Trend: Direction          │
│   ✅/⚠️/❌ Management       │
│   🎙️ Key highlights         │
│   ⚠️ Red flags              │
└──────────────┬──────────────┘
               │
               ▼ (Next Company)
        ┌────────────┐
        │ 4. REPORT  │
        │ ERRORS     │
        └─────┬──────┘
              │
              ▼
        ┌────────────┐
        │   END      │
        └────────────┘
```

---

## Detailed Analysis Steps

### 1. Trend Calculation

**Input:** Sales values for last 3 quarters
```
Q1 (Mar 2024): ₹100 Cr
Q2 (Jun 2024): ₹110 Cr  
Q3 (Sep 2024): ₹125 Cr  ← Current
```

**Process:**
1. Parse: [100, 110, 125]
2. Calculate QoQ growth: +10%, +13.6%
3. Average growth: +11.8%
4. Direction: Both positive → **IMPROVING**

**Classification Rules:**
- **IMPROVING**: 2+ quarters of positive growth
- **DECLINING**: 2+ quarters of negative growth
- **VOLATILE**: Any quarter with >50% swing
- **STABLE**: Within ±10% range

### 2. Performance Category

Combines Sales & Profit trends:

| Sales Trend | Profit Trend | Category | Emoji |
|-------------|--------------|----------|-------|
| Strong Up | Strong Up | Strong Growth | 🚀 |
| Moderate | Strong Up | Profit Expansion | 💰 |
| Strong Up | Moderate | Revenue Growth | 📈 |
| Up | Down | Margin Pressure | ⚠️ |
| Down | Down | Declining | 📉 |
| Flat | Flat | Stable | ⚖️ |

### 3. Transcript Analysis

**What Ollama extracts:**
- Key business highlights
- Management guidance forward
- Risks/challenges mentioned
- Strategic initiatives

**Prompt sent to Ollama - Current Quarter:**
```
Analyze this earnings call transcript and extract:
1. Executive Summary (2 sentences on key business highlights)
2. Management Guidance (What did they promise or forecast?)
3. Key Challenges/Risks mentioned
4. Forward Outlook

Transcript:
[PDF text content...]
```

**Prompt sent to Ollama - Guidance Comparison:**
```
Compare management commentary from Q1 vs Q2:

Q1 Guidance/Promises:
- [Extracted guidance points]

Q1 Outlook:
[Previous outlook]

Q2 Results Commentary:
[Current summary]

Question: Did management deliver on what they promised in Q1?
What's changed in their narrative?

Answer:
```

### 4. Management Track Record Assessment

**What gets compared:**
- Previous quarter promises → Current results
- Forward guidance consistency
- Tone changes (confident vs defensive)

**Assessment Categories:**
| Status | Meaning | Icon |
|--------|---------|------|
| **Delivered** | Met or exceeded guidance | ✅ |
| **Partial** | Some targets met | ⚠️ |
| **Missed** | Failed to deliver | ❌ |
| **Unknown** | No clear prior guidance | ❓ |

**Consistency Score:** 0-100 based on delivery history

### 4. Red Flag Detection

Automatic alerts for:
- 📉 Revenue declining 3Q straight
- 📉 Profit declining 3Q straight
- 🔍 Margin compression (Sales ↑ but Profit ↓)
- ⚠️ >20% revenue contraction
- ⚠️ >30% profit decline

---

## Data Sources

| Data | Source | Frequency | Note |
|------|--------|-----------|------|
| Company List | Screener Watchlist | Real-time | **Dynamic** - all companies |
| Sales/Profit | Screener Quarters Table | Quarterly | Last 3Q trend |
| YoY Growth | Screener Quarters Table | Quarterly | Calculated |
| **Concalls Section** | **Screener Company Page** | Quarterly | **New: Transcript links** |
| Transcript PDF | Screener Documents | Quarterly | Download + AI analysis |
| Management Guidance | AI Extraction from Transcript | Quarterly | Compared across quarters |

---

## Customization Points

You can add more analysis in `analyzer.py`:

### Example: Add PE Ratio Check
```python
def get_valuation_metrics(self, company):
    # Scrape PE, PBV, EV/EBITDA
    # Compare to sector average
    # Add to FinancialStory
```

### Example: Add Price Change
```python
def get_price_reaction(self, company, result_date):
    # Fetch price on result day vs day after
    # Add "Stock moved +X% on results" to tweet
```

### Example: Add Sector Comparison
```python
def compare_to_sector(self, company_growth, sector_avg):
    # "Company growing 2x faster than sector"
```

---

## File Structure

```
analyzer.py          ← ADD NEW ANALYSIS HERE
screener_client.py   ← ADD MORE SCRAPERS HERE
orchestrator.py      ← COORDINATES THE FLOW
ai_summarizer.py     ← OLLAMA INTEGRATION
twitter_poster.py    ← POSTING LOGIC
```

---

## Next Ideas to Add

1. **Price Action Scraper**: Check how stock moved after previous results
2. **Broker Estimates**: Compare actual vs consensus estimates
3. **Peer Comparison**: "Growing faster than competitors"
4. **Cash Flow Analysis**: Operating cash flow trend
5. **Debt Check**: Rising debt as red flag
6. **Promoter Holdings**: Changes in promoter stake

**Which analysis do you want to add next?**