#!/usr/bin/env python3
"""Debug script to inspect the concalls section HTML for a company."""
import time
import config
from browser_utils import get_chrome_driver, close_driver
from screener_client import ScreenerClient, Company
from selenium.webdriver.common.by import By

company_code = "skygold"  # change to a company with known concalls
company = Company(
    name=company_code.upper(),
    code=company_code,
    url=f"{config.SCREENER_BASE_URL}/company/{company_code}/consolidated/",
)

driver = get_chrome_driver(headless=False)
client = ScreenerClient(driver)

try:
    client.login(config.SCREENER_USERNAME, config.SCREENER_PASSWORD)

    url = f"{config.SCREENER_BASE_URL}/company/{company_code}/consolidated/#documents"
    print(f"\nNavigating to: {url}")
    driver.get(url)
    time.sleep(3)

    # Click any "Show more" buttons so hidden content loads
    from selenium.webdriver.common.by import By as _By
    show_more_buttons = driver.find_elements(_By.XPATH,
        "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'show more') or "
        "contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'load more')]"
    )
    for btn in show_more_buttons:
        try:
            if btn.is_displayed():
                print(f"  Clicking show-more button: '{btn.text}'")
                btn.click()
                time.sleep(1)
        except Exception:
            pass

    # Print all section/heading text on the page
    print("\n--- All h2/h3 headings ---")
    for tag in ["h2", "h3", "h4"]:
        for el in driver.find_elements(By.TAG_NAME, tag):
            print(f"  <{tag}>: {repr(el.text)}")

    # Find concalls section
    concalls_section = None
    for heading in driver.find_elements(By.TAG_NAME, "h2") + driver.find_elements(By.TAG_NAME, "h3"):
        if "concall" in heading.text.lower():
            concalls_section = heading.find_element(By.XPATH, "..")
            print(f"\nFound concalls parent via heading: <{heading.tag_name}> '{heading.text}'")
            break

    if concalls_section:
        # Walk up to find the real containing section (grandparent, great-grandparent…)
        print(f"\n--- Walking up from h3 parent to find list-links ---")
        el = concalls_section
        for level in range(5):
            inner = el.get_attribute("innerHTML") or ""
            has_list = "list-links" in inner or "list_links" in inner
            print(f"  level={level} tag={el.tag_name} has_list_links={has_list} len={len(inner)}")
            if has_list:
                print(f"\n--- Container innerHTML (first 4000 chars) ---")
                print(inner[:4000])
                break
            try:
                el = el.find_element(By.XPATH, "..")
            except Exception:
                print("  Reached top of DOM")
                break

        # Also try finding list-links directly on the page
        print(f"\n--- Searching for list-links anywhere on page ---")
        for cls in ["list-links", "list_links"]:
            els = driver.find_elements(By.CLASS_NAME, cls)
            print(f"  .{cls}: {len(els)} found")
            for i, e in enumerate(els[:3]):
                print(f"    [{i}] innerHTML: {e.get_attribute('innerHTML')[:500]}")

        # Also look for any anchor tags near 'transcript' keyword
        print(f"\n--- All <a> tags containing 'transcript' or 'concall' ---")
        for a in driver.find_elements(By.XPATH, "//a[contains(translate(@href,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'concall') or contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'transcript')]"):
            print(f"  text={repr(a.text.strip()[:60])} href={repr(a.get_attribute('href'))}")
    else:
        print("\nConcalls section NOT found. Printing #documents innerHTML:")
        try:
            doc_section = driver.find_element(By.ID, "documents")
            print(doc_section.get_attribute("innerHTML")[:3000])
        except Exception as e:
            print(f"  No #documents section either: {e}")
            print("\nPrinting full page body text (first 2000 chars):")
            print(driver.find_element(By.TAG_NAME, "body").text[:2000])

finally:
    input("\nPress Enter to close browser...")
    close_driver(driver)
