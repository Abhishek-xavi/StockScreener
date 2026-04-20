"""
Browser/WebDriver utilities for Selenium automation.
"""
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

import config
from logger import app_logger

# True when running inside GitHub Actions or any CI environment
_IS_CI = os.environ.get("CI", "").lower() in ("true", "1")


def get_chrome_driver(headless: bool = False, user_data_dir: str = None) -> webdriver.Chrome:
    """
    Create and configure Chrome WebDriver.
    Automatically runs headless + uses Linux user agent when in CI.
    """
    app_logger.info("Initializing Chrome WebDriver...")

    chrome_options = Options()

    # Core stability flags (required on Linux/CI)
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--window-size=1920,1080")

    if _IS_CI:
        chrome_options.add_argument("--remote-debugging-port=9222")
        chrome_options.add_argument("--disable-extensions")

    # User agent — Linux on CI, macOS locally
    if _IS_CI:
        chrome_options.add_argument(
            "--user-agent=Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    else:
        chrome_options.add_argument(
            "--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

    # Always headless in CI; otherwise respect the caller's flag
    if headless or _IS_CI:
        chrome_options.add_argument("--headless=new")
        app_logger.info("Running in headless mode")

    if user_data_dir:
        chrome_options.add_argument(f"--user-data-dir={user_data_dir}")

    # Suppress automation detection (skip experimental options on CI — can cause crashes)
    if not _IS_CI:
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )

    app_logger.info("Chrome WebDriver initialized")
    return driver


def close_driver(driver: webdriver.Chrome):
    """
    Safely close WebDriver.

    Args:
        driver: WebDriver instance to close
    """
    if driver:
        try:
            driver.quit()
            app_logger.info("Chrome WebDriver closed")
        except Exception as e:
            app_logger.warning(f"Error closing WebDriver: {e}")


def retry_with_backoff(func, max_attempts: int = config.RETRY_ATTEMPTS, delay: int = config.RETRY_DELAY):
    """
    Retry a function with exponential backoff.

    Args:
        func: Function to retry
        max_attempts: Maximum number of attempts
        delay: Initial delay between retries (doubles each time)

    Returns:
        Function result

    Raises:
        Last exception if all attempts fail
    """
    import time
    last_exception = None

    for attempt in range(max_attempts):
        try:
            return func()
        except Exception as e:
            last_exception = e
            app_logger.warning(f"Attempt {attempt + 1}/{max_attempts} failed: {e}")
            if attempt < max_attempts - 1:
                wait_time = delay * (2 ** attempt)
                app_logger.info(f"Retrying in {wait_time}s...")
                time.sleep(wait_time)

    raise last_exception
