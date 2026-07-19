"""
AIROS Opportunity OS v1.0
Browser Engine — the only module that controls Browserless.
No reasoning, no reports. Pure browser automation.
"""

import base64
import logging
import time
from typing import Any, Optional
import httpx
from config import config
from utils import Result

logger = logging.getLogger("airos.browser")

TIMEOUT = 60
MAX_RETRIES = 2


class BrowserError(Exception):
    pass


class Browser:
    """
    Provider interface for browser automation via Browserless CDP API.
    All methods return Result objects.
    """

    def __init__(self):
        self._base_url = config.browserless_url.rstrip("/")
        self._api_key = config.browserless_api_key

    def ping(self) -> None:
        """Verify Browserless is reachable."""
        url = f"{self._base_url}/pressure?token={self._api_key}"
        with httpx.Client(timeout=10) as client:
            r = client.get(url)
        if r.status_code != 200:
            raise BrowserError(f"Browserless ping failed: {r.status_code}")

    # ── Core automation ───────────────────────────────────────────────────────

    def get_page_content(self, url: str, wait_ms: int = 2000) -> Result:
        """Fetch rendered HTML content of a page."""
        script = f"""
        module.exports = async ({{ page }}) => {{
            await page.goto('{url}', {{ waitUntil: 'networkidle2', timeout: 30000 }});
            await page.waitForTimeout({wait_ms});
            const content = await page.content();
            const text = await page.evaluate(() => document.body.innerText);
            return {{ content, text, url: page.url() }};
        }};
        """
        return self._run_function(script)

    def get_links(self, url: str, selector: str = "a") -> Result:
        """Extract all links from a page."""
        script = f"""
        module.exports = async ({{ page }}) => {{
            await page.goto('{url}', {{ waitUntil: 'networkidle2', timeout: 30000 }});
            const links = await page.evaluate((sel) => {{
                return Array.from(document.querySelectorAll(sel)).map(a => ({{
                    href: a.href,
                    text: a.innerText.trim()
                }})).filter(l => l.href);
            }}, '{selector}');
            return {{ links }};
        }};
        """
        return self._run_function(script)

    def click_and_get_content(self, url: str, selector: str, wait_ms: int = 2000) -> Result:
        """Navigate to URL, click element, return resulting page content."""
        script = f"""
        module.exports = async ({{ page }}) => {{
            await page.goto('{url}', {{ waitUntil: 'networkidle2', timeout: 30000 }});
            await page.click('{selector}');
            await page.waitForTimeout({wait_ms});
            const text = await page.evaluate(() => document.body.innerText);
            return {{ text, url: page.url() }};
        }};
        """
        return self._run_function(script)

    def fill_form_and_submit(
        self,
        url: str,
        field_mappings: list[dict],
        submit_selector: str,
        wait_after_ms: int = 3000,
    ) -> Result:
        """
        Fill a form and submit it.
        field_mappings: [{"selector": "...", "value": "...", "type": "text|select|checkbox"}]
        """
        fill_steps = []
        for field in field_mappings:
            sel = field["selector"].replace("'", "\\'")
            val = str(field.get("value", "")).replace("'", "\\'")
            ftype = field.get("type", "text")
            if ftype == "text":
                fill_steps.append(f"await page.type('{sel}', '{val}', {{delay: 30}});")
            elif ftype == "select":
                fill_steps.append(f"await page.select('{sel}', '{val}');")
            elif ftype == "checkbox":
                fill_steps.append(f"await page.click('{sel}');")

        fill_code = "\n            ".join(fill_steps)
        submit_sel = submit_selector.replace("'", "\\'")

        script = f"""
        module.exports = async ({{ page }}) => {{
            await page.goto('{url}', {{ waitUntil: 'networkidle2', timeout: 30000 }});
            {fill_code}
            await page.click('{submit_sel}');
            await page.waitForTimeout({wait_after_ms});
            const text = await page.evaluate(() => document.body.innerText);
            return {{ text, url: page.url(), success: true }};
        }};
        """
        return self._run_function(script)

    def upload_file(self, url: str, input_selector: str, file_b64: str, filename: str) -> Result:
        """Upload a file to a file input. file_b64 is base64-encoded file content."""
        script = f"""
        const {{ writeFileSync }} = require('fs');
        const path = require('path');
        module.exports = async ({{ page }}) => {{
            await page.goto('{url}', {{ waitUntil: 'networkidle2', timeout: 30000 }});
            const tmpPath = path.join('/tmp', '{filename}');
            const buf = Buffer.from('{file_b64}', 'base64');
            writeFileSync(tmpPath, buf);
            const input = await page.$('{input_selector}');
            await input.uploadFile(tmpPath);
            await page.waitForTimeout(2000);
            return {{ uploaded: true, path: tmpPath }};
        }};
        """
        return self._run_function(script)

    def screenshot(self, url: str) -> Result:
        """Capture screenshot as base64 PNG."""
        script = f"""
        module.exports = async ({{ page }}) => {{
            await page.goto('{url}', {{ waitUntil: 'networkidle2', timeout: 30000 }});
            const screenshot = await page.screenshot({{ encoding: 'base64', type: 'png' }});
            return {{ screenshot }};
        }};
        """
        return self._run_function(script)

    def login(self, url: str, username: str, password: str, selectors: dict) -> Result:
        """
        Perform a login sequence.
        selectors: {"username": "...", "password": "...", "submit": "..."}
        """
        u = username.replace("'", "\\'")
        p = password.replace("'", "\\'")
        user_sel = selectors.get("username", "input[type=email]")
        pass_sel = selectors.get("password", "input[type=password]")
        submit_sel = selectors.get("submit", "button[type=submit]")

        script = f"""
        module.exports = async ({{ page }}) => {{
            await page.goto('{url}', {{ waitUntil: 'networkidle2', timeout: 30000 }});
            await page.type('{user_sel}', '{u}', {{delay: 50}});
            await page.type('{pass_sel}', '{p}', {{delay: 50}});
            await page.click('{submit_sel}');
            await page.waitForNavigation({{ waitUntil: 'networkidle2', timeout: 15000 }}).catch(() => {{}});
            const text = await page.evaluate(() => document.body.innerText);
            return {{ text, url: page.url() }};
        }};
        """
        return self._run_function(script)

    def extract_structured_data(self, url: str, extraction_js: str) -> Result:
        """
        Run custom extraction JS on a page.
        extraction_js should return a JSON-serializable object.
        """
        script = f"""
        module.exports = async ({{ page }}) => {{
            await page.goto('{url}', {{ waitUntil: 'networkidle2', timeout: 30000 }});
            const data = await page.evaluate(() => {{
                {extraction_js}
            }});
            return {{ data }};
        }};
        """
        return self._run_function(script)

    def scroll_and_collect(self, url: str, item_selector: str, max_items: int = 50) -> Result:
        """Scroll page and collect items matching selector."""
        script = f"""
        module.exports = async ({{ page }}) => {{
            await page.goto('{url}', {{ waitUntil: 'networkidle2', timeout: 30000 }});
            let items = [];
            let prevCount = 0;
            for (let i = 0; i < 10; i++) {{
                items = await page.evaluate((sel) => {{
                    return Array.from(document.querySelectorAll(sel)).map(el => el.innerText.trim());
                }}, '{item_selector}');
                if (items.length >= {max_items} || items.length === prevCount) break;
                prevCount = items.length;
                await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
                await page.waitForTimeout(1500);
            }}
            return {{ items: items.slice(0, {max_items}) }};
        }};
        """
        return self._run_function(script)

    # ── Internal execution ────────────────────────────────────────────────────

    def _run_function(self, script: str) -> Result:
        """Execute a Browserless /function script with retry logic."""
        url = f"{self._base_url}/function?token={self._api_key}"
        for attempt in range(MAX_RETRIES + 1):
            try:
                with httpx.Client(timeout=TIMEOUT) as client:
                    response = client.post(
                        url,
                        json={"code": script},
                        headers={"Content-Type": "application/json"},
                    )
                if response.status_code == 200:
                    data = response.json()
                    return Result.success(data)
                elif response.status_code == 429:
                    logger.warning(f"Browser rate limited, attempt {attempt+1}")
                    time.sleep(5)
                    if attempt < MAX_RETRIES:
                        continue
                    return Result.retry("Browser rate limited")
                else:
                    error = f"Browser HTTP {response.status_code}: {response.text[:200]}"
                    logger.warning(error)
                    if attempt < MAX_RETRIES:
                        time.sleep(2)
                        continue
                    return Result.failed(error)
            except httpx.TimeoutException:
                logger.warning(f"Browser timeout attempt {attempt+1}")
                if attempt < MAX_RETRIES:
                    time.sleep(2)
                    continue
                return Result.retry("Browser timeout")
            except Exception as exc:
                logger.error(f"Browser unexpected error: {exc}")
                return Result.failed(str(exc))
        return Result.failed("Browser failed after all retries")


# Singleton
browser = Browser()
