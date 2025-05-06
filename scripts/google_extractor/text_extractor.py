# text_extractor.py
# -*- coding: utf-8 -*-

"""
Functions for extracting main text content from URLs.
Includes a requests-based version and a Playwright-based version for dynamic content.
"""

import logging
import asyncio
from typing import Optional

import requests
import trafilatura
try:
    from playwright.async_api import async_playwright, Error as PlaywrightError
    PLAYWRIGHT_AVAILABLE = True
    logging.info("Playwright found and available.")
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    PlaywrightError = Exception # Define a placeholder
    logging.info("Playwright not found. JS rendering will not be available.")

from config import EXTRACTION_HEADERS, DEFAULT_EXTRACTION_TIMEOUT


def extract_main_text_requests(url: str, timeout: int = DEFAULT_EXTRACTION_TIMEOUT) -> Optional[str]:
    """
    Fetches content from URL, extracts main text using trafilatura.
    Uses lazy % formatting for logging. Returns text string or None on failure.
    """
    logging.debug("[Requests] Attempting text extraction from: %s", url)
    try:
        response = requests.get(url, headers=EXTRACTION_HEADERS, timeout=timeout, allow_redirects=True)
        response.raise_for_status() # Check for HTTP errors (4xx, 5xx)
        content_type = response.headers.get('content-type', '').lower()

        # Check if content type seems appropriate before parsing
        if 'html' not in content_type and 'xml' not in content_type:
            logging.warning("[Requests] Content type '%s' for URL %s not HTML/XML. Skipping extraction.", content_type, url)
            return None

        html_content = response.text
        if not html_content:
            logging.warning("[Requests] No HTML/text content retrieved from %s", url)
            return None

        # Use trafilatura for extraction
        # Consider adding error_recovery=True for more resilience if needed
        main_text = trafilatura.extract(
            html_content,
            include_comments=False,
            include_tables=True, # Adjust as needed
            output_format='txt'
            # target_language='en' # Optional: specify if known
        )

        if main_text:
            logging.debug("[Requests] Successfully extracted text from: %s", url)
            return main_text.strip() # Remove leading/trailing whitespace

        # It's not necessarily an error if a page has no extractable main text
        logging.info("[Requests] Trafilatura found no main text in: %s", url)
        return None

    except requests.exceptions.Timeout:
        logging.error("[Requests] Timeout occurred while fetching URL for extraction: %s", url)
        return None
    except requests.exceptions.TooManyRedirects:
        logging.error("[Requests] Too many redirects for URL: %s", url)
        return None
    except requests.exceptions.RequestException as e:
        # Log other request errors but allow the main script to continue
        logging.error("[Requests] Extraction error fetching %s: %s", url, e)
        return None
    except Exception as e:
        # Catch potential trafilatura or other unexpected errors
        logging.error(
            "[Requests] Unexpected error during text extraction for %s: %s",
            url,
            e,
            exc_info=False) # Set exc_info=True for full traceback if needed
        return None


# --- Async Playwright-based function ---
async def extract_main_text_playwright(
    url: str,
    timeout: int = 30,
    wait_seconds: float = 2.0
) -> Optional[str]:
    """
    Fetches URL using Async Playwright (renders JS), waits, then extracts text.
    Handles dynamic content but requires Playwright setup and async execution.

    Args:
        url: The URL to process.
        timeout: Overall timeout for Playwright navigation/operations (seconds).
        wait_seconds: Explicit time to wait after initial load (seconds).

    Returns:
        Extracted text string or None on failure.
    """
    if not PLAYWRIGHT_AVAILABLE:
        logging.error("Playwright is not installed. Cannot use async Playwright extraction.")
        # Fallback could potentially call the sync requests version, but needs care in async context
        # Option 1: Just return None
        return None
        # Option 2: Run sync requests in executor (safer in async)
        # loop = asyncio.get_running_loop()
        # return await loop.run_in_executor(None, extract_main_text_requests, url, timeout)


    logging.debug("[Playwright][Async] Attempting extraction for: %s", url)
    html_content = None
    browser = None # Initialize browser variable

    try:
        # Use async context manager and await calls
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=EXTRACTION_HEADERS['User-Agent'],
                java_script_enabled=True,
                ignore_https_errors=True # Use with caution
            )
            # Apply timeouts directly to context actions if needed, or rely on default
            # context.set_default_navigation_timeout(timeout * 1000) # Set for context
            # context.set_default_timeout(timeout * 1000)         # Set for context

            page = await context.new_page()
            logging.debug("[Playwright][Async] Navigating to %s", url)
            # Navigate with potentially adjusted timeout for the specific goto action
            await page.goto(url, timeout=timeout * 1000, wait_until='domcontentloaded')

            # *** Use asyncio.sleep for non-blocking wait ***
            logging.info("[Playwright][Async] Waiting %.1f seconds for dynamic content on %s...", wait_seconds, url)
            await asyncio.sleep(wait_seconds)

            # Get the page's HTML content *after* JS execution and waiting
            html_content = await page.content()
            logging.debug("[Playwright][Async] HTML content retrieved for %s", url)

            # Close context and browser gracefully
            await context.close()
            await browser.close()

    except PlaywrightError as e:
        # Catch specific Playwright errors (TimeoutError, etc.)
        logging.error("[Playwright][Async] Playwright error for %s: %s", url, e)
        if browser and browser.is_connected():
            await browser.close() # Ensure cleanup
        return None
    except Exception as e:
        # Catch any other unexpected errors
        logging.error("[Playwright][Async] Unexpected error during Playwright processing for %s: %s", url, e, exc_info=False)
        if browser and browser.is_connected():
            await browser.close() # Ensure cleanup
        return None

    # --- Trafilatura extraction (still synchronous CPU-bound task) ---
    # Running this directly is usually fine unless it's extremely slow.
    # For very heavy parsing, could consider loop.run_in_executor
    if not html_content:
        logging.warning("[Playwright][Async] No HTML content retrieved via Playwright from %s", url)
        return None

    logging.debug("[Playwright][Async] Starting Trafilatura extraction on rendered HTML for %s", url)
    try:
        # Trafilatura itself is sync
        main_text = trafilatura.extract(html_content, include_comments=False, include_tables=True, output_format='txt')
        if main_text:
            logging.debug("[Playwright][Async] Successfully extracted text via Trafilatura from: %s", url)
            return main_text.strip()
        logging.info("[Playwright][Async] Trafilatura found no main text via Playwright in: %s", url)
        return None
    except Exception as e:
        logging.error("[Playwright][Async] Error during Trafilatura extraction after Playwright for %s: %s", url, e)
        return None