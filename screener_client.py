"""
Screener.in web scraper using Selenium.
Handles login, watchlist fetching, quarterly results extraction, and transcript downloads.
"""
import time
import re
import tempfile
import os
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Tuple
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

import config
from logger import app_logger, log_company_start, log_company_success, log_company_error


@dataclass
class QuarterlyResult:
    """Data class for quarterly result metrics."""
    company_name: str
    company_code: str
    quarter: str
    # Current quarter data
    sales: str
    sales_growth_yoy: str
    net_profit: str
    profit_growth_yoy: str
    eps: Optional[str] = None
    operating_profit: Optional[str] = None
    # 3-quarter trend data
    sales_trend: List[str] = None  # Last 3 quarters sales
    profit_trend: List[str] = None  # Last 3 quarters profit
    quarters_list: List[str] = None  # Quarter labels


@dataclass
class Company:
    """Company information from watchlist."""
    name: str
    code: str
    url: str


@dataclass
class TranscriptInfo:
    """Earnings transcript information."""
    company_name: str
    quarter: str
    pdf_url: Optional[str] = None
    text_content: Optional[str] = None
    is_available: bool = False


@dataclass
class ConcallInfo:
    """Concall section information with multiple quarters."""
    company_name: str
    transcripts: List[TranscriptInfo]  # Last 2 quarters


class ScreenerClient:
    """Selenium-based client for Screener.in scraping."""

    def __init__(self, driver: webdriver.Chrome = None):
        self.driver = driver
        self.errors = []  # Track errors for reporting

    def login(self, username: str, password: str) -> bool:
        """
        Login to Screener.in.

        Args:
            username: Screener.in username
            password: Screener.in password

        Returns:
            True if login successful, False otherwise
        """
        if not self.driver:
            app_logger.error("No WebDriver provided")
            return False

        try:
            app_logger.info("Logging into Screener.in...")
            self.driver.get(f"{config.SCREENER_BASE_URL}/login/")

            # Wait for login form
            wait = WebDriverWait(self.driver, 10)
            email_field = wait.until(EC.presence_of_element_located((By.NAME, "username")))
            password_field = self.driver.find_element(By.NAME, "password")
            login_button = self.driver.find_element(By.XPATH, "//button[@type='submit']")

            # Fill credentials
            email_field.clear()
            email_field.send_keys(username)
            password_field.clear()
            password_field.send_keys(password)

            # Submit
            login_button.click()

            # Wait for redirect (dashboard or home)
            time.sleep(3)

            # Check if logged in by looking for watchlist link
            if "login" not in self.driver.current_url:
                app_logger.info("Login successful")
                return True
            else:
                app_logger.error("Login failed - still on login page")
                return False

        except TimeoutException:
            app_logger.error("Login timeout - page took too long to load")
            return False
        except Exception as e:
            app_logger.error(f"Login error: {e}")
            return False

    def get_watchlist_companies(self) -> List[Company]:
        """
        Fetch companies from user's watchlist.

        Returns:
            List of Company objects
        """
        companies = []

        try:
            app_logger.info("Fetching watchlist...")
            self.driver.get(f"{config.SCREENER_BASE_URL}/watchlist/")
            time.sleep(2)

            # Find watchlist table
            table = self.driver.find_element(By.XPATH, "//table")
            rows = table.find_elements(By.TAG_NAME, "tr")

            # Skip header row
            for row in rows[1:]:
                try:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) >= 3:
                        # Company name is typically in 3rd column
                        link = cells[2].find_element(By.TAG_NAME, "a")
                        name = link.text.strip()
                        href = link.get_attribute("href")
                        # Extract code from URL
                        code = href.split("/company/")[-1].split("/")[0] if "/company/" in href else name

                        companies.append(Company(name=name, code=code, url=href))
                        app_logger.debug(f"Found watchlist company: {name}")
                except NoSuchElementException:
                    continue

            app_logger.info(f"Found {len(companies)} companies in watchlist")
            return companies

        except Exception as e:
            app_logger.error(f"Failed to fetch watchlist: {e}")
            return []

    def get_quarterly_results_with_trend(self, company: Company) -> Optional[QuarterlyResult]:
        """
        Extract quarterly results with 3-quarter trend data.

        Args:
            company: Company object

        Returns:
            QuarterlyResult with trend data if found, None otherwise
        """
        log_company_start(company.name)

        try:
            # Navigate to company page
            self.driver.get(company.url)
            time.sleep(config.REQUEST_DELAY)

            # Find quarters section
            try:
                quarters_section = self.driver.find_element(By.ID, "quarters")
            except NoSuchElementException:
                log_company_error(company.name, "No quarters section found", skipped=True)
                return None

            # Find table
            table = quarters_section.find_element(By.TAG_NAME, "table")

            # Get headers to find column indices (represents quarters)
            headers = [th.text.strip() for th in table.find_elements(By.TAG_NAME, "th")]

            # We need at least 4 columns: metric name + 3 quarters of data
            if len(headers) < 4:
                log_company_error(company.name, f"Insufficient quarterly data: {headers}", skipped=True)
                return None

            # Get last 5 quarters (excluding "TTM") — 5 lets us compute YoY vs same quarter last year
            quarter_headers = [h for h in headers[1:] if h and h.lower() not in ["ttm", ""]]
            if len(quarter_headers) < 3:
                log_company_error(company.name, f"Less than 3 quarters available: {quarter_headers}", skipped=True)
                return None

            last_5_quarters = quarter_headers[-5:]
            last_3_quarters = last_5_quarters[-3:]
            current_quarter = last_3_quarters[-1]
            yoy_quarter = last_5_quarters[0] if len(last_5_quarters) == 5 else None  # same quarter last year
            app_logger.info(f"Analyzing {company.name} for {current_quarter} with trend from {', '.join(last_3_quarters)}")

            q_indices      = [headers.index(q) for q in last_3_quarters]
            yoy_idx        = headers.index(yoy_quarter) if yoy_quarter else None

            rows = table.find_elements(By.TAG_NAME, "tr")

            sales_trend  = []
            profit_trend = []
            data = {
                "sales": None, "sales_yoy": None,
                "net_profit": None, "profit_yoy": None,
                "eps": None, "operating_profit": None,
                "sales_yoy_quarter": None, "profit_yoy_quarter": None,
            }

            def _parse_num(text: str) -> Optional[float]:
                """Strip commas/spaces and convert to float."""
                try:
                    return float(text.replace(",", "").replace(" ", ""))
                except Exception:
                    return None

            def _yoy_pct(current_val: str, year_ago_val: str) -> Optional[str]:
                c = _parse_num(current_val)
                p = _parse_num(year_ago_val)
                if c is not None and p and p != 0:
                    pct = (c - p) / abs(p) * 100
                    sign = "+" if pct >= 0 else ""
                    return f"{sign}{pct:.1f}%"
                return None

            for row in rows[1:]:
                try:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if not cells:
                        continue

                    row_name = cells[0].text.strip().lower()

                    if "sales" in row_name and "growth" not in row_name and "yoy" not in row_name:
                        sales_trend = [cells[i].text.strip() if i < len(cells) else "N/A" for i in q_indices]
                        data["sales"] = sales_trend[-1]
                        if yoy_idx and yoy_idx < len(cells):
                            data["sales_yoy_quarter"] = cells[yoy_idx].text.strip()
                            data["sales_yoy"] = _yoy_pct(data["sales"], data["sales_yoy_quarter"])

                    elif "net profit" in row_name and "growth" not in row_name:
                        profit_trend = [cells[i].text.strip() if i < len(cells) else "N/A" for i in q_indices]
                        data["net_profit"] = profit_trend[-1]
                        if yoy_idx and yoy_idx < len(cells):
                            data["profit_yoy_quarter"] = cells[yoy_idx].text.strip()
                            data["profit_yoy"] = _yoy_pct(data["net_profit"], data["profit_yoy_quarter"])

                    elif "eps" in row_name:
                        data["eps"] = cells[q_indices[-1]].text.strip() if q_indices[-1] < len(cells) else None

                    elif "operating profit" in row_name and "growth" not in row_name:
                        data["operating_profit"] = cells[q_indices[-1]].text.strip() if q_indices[-1] < len(cells) else None

                except Exception:
                    continue

            if data["sales"] and data["net_profit"]:
                result = QuarterlyResult(
                    company_name=company.name,
                    company_code=company.code,
                    quarter=current_quarter,
                    sales=data["sales"],
                    sales_growth_yoy=data.get("sales_yoy") or "N/A",
                    net_profit=data["net_profit"],
                    profit_growth_yoy=data.get("profit_yoy") or "N/A",
                    eps=data.get("eps"),
                    operating_profit=data.get("operating_profit"),
                    sales_trend=sales_trend,
                    profit_trend=profit_trend,
                    quarters_list=last_3_quarters,
                )
                log_company_success(company.name, f"Found {current_quarter} results with trend data")
                return result
            else:
                log_company_error(
                    company.name,
                    f"Incomplete data - Sales: {data['sales']}, Profit: {data['net_profit']}",
                    skipped=True
                )
                return None

        except Exception as e:
            log_company_error(company.name, str(e), skipped=True)
            self.errors.append((company.name, str(e)))
            return None

    def find_concalls_section(self, company: Company, target_quarters: List[str]) -> ConcallInfo:
        """
        Find Concalls section via direct documents URL and extract transcript PDF links.

        Structure on Screener.in:
          <div>                          ← grandparent of h3
            <div><h3>Concalls</h3>...</div>
            <div class="show-more-box">
              <ul class="list-links">
                <li>
                  <div>Feb 2026</div>
                  <a class="concall-link" href="...pdf">Transcript</a>
                  ...
                </li>
              </ul>
            </div>
          </div>

        Strategy: find the h3, walk up to the ancestor that contains list-links,
        then match each <li> against target quarters.
        Falls back to the latest transcript if no quarter matches.
        """
        info = ConcallInfo(company_name=company.name, transcripts=[])

        try:
            documents_url = f"{config.SCREENER_BASE_URL}/company/{company.code}/consolidated/#documents"
            app_logger.info(f"Navigating to documents page: {documents_url}")
            self.driver.get(documents_url)
            time.sleep(2)

            # Find the h3 that says "Concalls"
            concalls_h3 = None
            for h3 in self.driver.find_elements(By.TAG_NAME, "h3"):
                if "concall" in h3.text.lower():
                    concalls_h3 = h3
                    break

            if not concalls_h3:
                app_logger.warning(f"No Concalls h3 found for {company.name}")
                return info

            # Walk up from h3 until we find the ancestor that contains ul.list-links
            container = concalls_h3
            list_links_ul = None
            for _ in range(6):
                try:
                    container = container.find_element(By.XPATH, "..")
                    uls = container.find_elements(By.CLASS_NAME, "list-links")
                    if uls:
                        list_links_ul = uls[0]
                        app_logger.info(f"Found list-links for {company.name}")
                        break
                except Exception:
                    break

            if not list_links_ul:
                app_logger.warning(f"No list-links found in Concalls section for {company.name}")
                return info

            # Each <li> is one concall entry: <div>Month Year</div> + <a>Transcript</a> ...
            rows = list_links_ul.find_elements(By.TAG_NAME, "li")
            app_logger.info(f"Found {len(rows)} concall entries for {company.name}")

            matched_quarters = set()

            for row in rows:
                # Get the date label (e.g. "Feb 2026")
                try:
                    date_div = row.find_element(By.XPATH, ".//div")
                    row_date = date_div.text.strip()  # e.g. "Feb 2026"
                except Exception:
                    row_date = row.text.split("\n")[0].strip()

                # Find best available link: Transcript first, PPT as fallback
                transcript_link = None
                ppt_link = None
                for a in row.find_elements(By.TAG_NAME, "a"):
                    text = a.text.lower()
                    if "transcript" in text:
                        transcript_link = a
                        break
                    if "ppt" in text and ppt_link is None:
                        ppt_link = a

                chosen = transcript_link or ppt_link
                if not chosen:
                    continue

                source = "Transcript" if transcript_link else "PPT"
                href = chosen.get_attribute("href") or ""

                # Check if this row matches any of our target quarters
                # Target quarters look like "Dec 2025"; row_date looks like "Feb 2026"
                # We try a loose match: same year + same month abbreviation
                row_date_lower = row_date.lower()
                matched_quarter = None
                for tq in target_quarters:
                    if tq in matched_quarters:
                        continue
                    tq_parts = tq.lower().split()  # ["dec", "2025"]
                    if len(tq_parts) == 2 and tq_parts[1] in row_date_lower:
                        # Year matches; check month (first 3 chars)
                        if tq_parts[0][:3] in row_date_lower:
                            matched_quarter = tq
                            break

                if matched_quarter:
                    app_logger.info(f"✓ Matched {row_date} → {matched_quarter} [{source}]: {href}")
                    info.transcripts.append(TranscriptInfo(
                        company_name=company.name,
                        quarter=matched_quarter,
                        pdf_url=href,
                        is_available=True,
                    ))
                    matched_quarters.add(matched_quarter)

            # If nothing matched, fall back to latest row — Transcript then PPT
            if not info.transcripts and rows:
                row = rows[0]
                try:
                    date_div = row.find_element(By.XPATH, ".//div")
                    row_date = date_div.text.strip()
                except Exception:
                    row_date = "Latest"

                chosen = None
                source = ""
                for a in row.find_elements(By.TAG_NAME, "a"):
                    text = a.text.lower()
                    if "transcript" in text:
                        chosen, source = a, "Transcript"
                        break
                    if "ppt" in text and chosen is None:
                        chosen, source = a, "PPT"

                if chosen:
                    href = chosen.get_attribute("href") or ""
                    app_logger.info(f"No quarter match — using latest [{source}]: {row_date} {href}")
                    info.transcripts.append(TranscriptInfo(
                        company_name=company.name,
                        quarter=row_date,
                        pdf_url=href,
                        is_available=True,
                    ))

            return info

        except Exception as e:
            app_logger.error(f"Error finding concalls for {company.name}: {e}")
            return info

    def download_and_extract_transcript(self, pdf_url: str) -> Optional[str]:
        """
        Download PDF and extract text content.

        Args:
            pdf_url: URL to the PDF file

        Returns:
            Extracted text or None if failed
        """
        try:
            import requests
            from io import BytesIO
            from PyPDF2 import PdfReader

            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }

            response = requests.get(pdf_url, headers=headers, timeout=30)
            response.raise_for_status()

            # Extract text from PDF
            pdf_file = BytesIO(response.content)
            reader = PdfReader(pdf_file)

            text = ""
            for page in reader.pages:
                text += page.extract_text() or ""

            app_logger.info(f"Extracted {len(text)} characters from transcript PDF")
            return text  # Return full transcript; AI backends handle their own limits

        except Exception as e:
            app_logger.error(f"Failed to download/extract transcript: {e}")
            return None

    def click_and_extract_transcript(self, transcript_link_element) -> Optional[str]:
        """
        Click on transcript button which opens a new window with the PDF, then extract text.

        Args:
            transcript_link_element: The Selenium element to click

        Returns:
            Extracted text content or None if failed
        """
        original_window = self.driver.current_window_handle
        original_handles = set(self.driver.window_handles)

        try:
            app_logger.info("Clicking transcript link (expecting new window)...")
            transcript_link_element.click()

            # Wait for new window to open (up to 10 seconds)
            wait = WebDriverWait(self.driver, 10)
            try:
                wait.until(lambda d: len(d.window_handles) > len(original_handles))
            except TimeoutException:
                app_logger.warning("No new window appeared after clicking transcript")

            new_handles = set(self.driver.window_handles) - original_handles

            if new_handles:
                new_window = new_handles.pop()
                self.driver.switch_to.window(new_window)
                time.sleep(2)  # Let the PDF/page load

                pdf_url = self.driver.current_url
                app_logger.info(f"New window URL: {pdf_url}")

                text_content = None

                # If the new window loaded a PDF URL, download and extract it
                if pdf_url and pdf_url.lower().endswith(".pdf") or "pdf" in pdf_url.lower():
                    app_logger.info("Detected PDF in new window, downloading and extracting...")
                    text_content = self.download_and_extract_transcript(pdf_url)

                # Fallback: try to read text rendered on the page (e.g., inline PDF viewer)
                if not text_content:
                    try:
                        body_text = self.driver.find_element(By.TAG_NAME, "body").text
                        if len(body_text) > 200:
                            text_content = body_text
                            app_logger.info(f"Extracted {len(text_content)} chars from page body")
                    except Exception:
                        pass

                # Close new window and switch back
                self.driver.close()
                self.driver.switch_to.window(original_window)

                if text_content:
                    text_content = "\n".join(
                        line.strip() for line in text_content.split("\n") if line.strip()
                    )
                    return text_content[:15000]

                app_logger.warning("New window opened but no transcript text could be extracted")
                return None

            # No new window — check for modal or same-page content
            app_logger.info("No new window, checking for modal or inline content...")
            time.sleep(2)
            text_content = None

            for selector, by, value in [
                ("modal", By.CLASS_NAME, "modal-content"),
                ("#transcript-content", By.ID, "transcript-content"),
                ("article", By.TAG_NAME, "article"),
                ("main", By.TAG_NAME, "main"),
            ]:
                try:
                    el = self.driver.find_element(by, value)
                    if el.is_displayed() and len(el.text) > 200:
                        text_content = el.text
                        app_logger.info(f"Found transcript in {selector} ({len(text_content)} chars)")
                        break
                except Exception:
                    pass

            # Try to close any modal
            try:
                for btn in self.driver.find_elements(By.XPATH, "//button[contains(@class,'close')]"):
                    if btn.is_displayed():
                        btn.click()
                        break
            except Exception:
                pass

            if text_content:
                text_content = "\n".join(line.strip() for line in text_content.split("\n") if line.strip())
                return text_content[:15000]

            app_logger.warning("Could not find transcript text content")
            return None

        except Exception as e:
            app_logger.error(f"Error clicking/extracting transcript: {e}")
            # Always switch back to original window on error
            try:
                self.driver.switch_to.window(original_window)
            except Exception:
                pass
            return None

    def get_errors(self) -> List[tuple]:
        """Return list of errors encountered during scraping."""
        return self.errors

    def clear_errors(self):
        """Clear error list."""
        self.errors = []
