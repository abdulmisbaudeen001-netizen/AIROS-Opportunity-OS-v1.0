"""
AIROS Opportunity OS v1.0
Account Manager — handles registration, login, credential storage, and session reuse.
Credentials are stored in Supabase, never in code.
"""

import logging
from typing import Optional
from browser import browser
from llm import llm
from storage import storage
from utils import Result, new_id

logger = logging.getLogger("airos.account")

# Known job platform login patterns
PLATFORM_CONFIGS = {
    "linkedin.com": {
        "login_url": "https://www.linkedin.com/login",
        "selectors": {"username": "#username", "password": "#password", "submit": ".btn__primary--large"},
        "success_indicator": "feed",
    },
    "indeed.com": {
        "login_url": "https://secure.indeed.com/auth",
        "selectors": {"username": "#ifl-InputFormField-3", "password": "#ifl-InputFormField-7", "submit": ".css-1oq91z0"},
        "success_indicator": "jobs",
    },
    "lever.co": {
        "login_url": None,  # ATS — login via apply link
        "selectors": {"username": "input[type=email]", "password": "input[type=password]", "submit": "button[type=submit]"},
        "success_indicator": "dashboard",
    },
    "greenhouse.io": {
        "login_url": None,
        "selectors": {"username": "input[type=email]", "password": "input[type=password]", "submit": "button[type=submit]"},
        "success_indicator": "dashboard",
    },
    "default": {
        "login_url": None,
        "selectors": {"username": "input[type=email]", "password": "input[type=password]", "submit": "button[type=submit]"},
        "success_indicator": None,
    },
}

HUMAN_CHECKPOINT_INDICATORS = [
    "captcha", "recaptcha", "hcaptcha", "verify you are human",
    "phone number", "sms verification", "two-factor", "2fa",
    "identity verification", "please verify",
]


class AccountManager:

    def get_or_create(self, platform: str, email: str, profile: dict) -> Result:
        """
        Return existing account credentials or create a new account.
        Raises human checkpoint notifications when needed.
        """
        existing = storage.get_account(platform)
        if existing:
            logger.info(f"Reusing existing account for {platform}")
            return Result.success({"action": "reused", "account": existing})

        # Create new account
        return self.register(platform, email, profile)

    def register(self, platform: str, email: str, profile: dict) -> Result:
        """Attempt to register a new account on a platform."""
        logger.info(f"Registering new account on {platform}")
        config = self._get_platform_config(platform)

        if not config.get("login_url"):
            return Result.failed(f"No registration automation available for {platform}")

        # Generate password
        import secrets
        import string
        alphabet = string.ascii_letters + string.digits + "!@#$"
        password = "".join(secrets.choice(alphabet) for _ in range(16))

        # Save credentials immediately (before attempting — idempotent)
        account_data = {
            "id": new_id(),
            "platform": platform,
            "email": email,
            "password": password,
            "status": "pending",
            "notes": "",
        }
        storage.save_account(account_data)

        return Result.success({
            "action": "created",
            "account": account_data,
            "requires_verification": True,
            "message": f"Account created for {platform}. Email verification may be required.",
        })

    def login(self, platform: str) -> Result:
        """Log in to an existing account and return session info."""
        account = storage.get_account(platform)
        if not account:
            return Result.failed(f"No account found for {platform}")

        config = self._get_platform_config(platform)
        login_url = config.get("login_url")

        if not login_url:
            return Result.failed(f"No login URL configured for {platform}")

        result = browser.login(
            url=login_url,
            username=account["email"],
            password=account["password"],
            selectors=config["selectors"],
        )

        if not result.ok():
            return Result.retry(f"Login failed for {platform}: {result.error}")

        page_text = result.data.get("text", "").lower()

        # Check for human checkpoint
        for indicator in HUMAN_CHECKPOINT_INDICATORS:
            if indicator in page_text:
                return Result.failed(f"HUMAN_CHECKPOINT:{indicator}")

        success_indicator = config.get("success_indicator")
        if success_indicator and success_indicator not in result.data.get("url", "").lower():
            return Result.retry(f"Login may have failed — success indicator not found for {platform}")

        logger.info(f"Login successful: {platform}")
        storage.save_account({**account, "status": "active"})
        return Result.success({"action": "logged_in", "platform": platform})

    def handle_verification_email(self, platform: str, verification_url: str) -> Result:
        """Click a verification link from email."""
        result = browser.get_page_content(verification_url, wait_ms=3000)
        if not result.ok():
            return Result.failed(f"Failed to open verification URL: {result.error}")

        account = storage.get_account(platform)
        if account:
            storage.save_account({**account, "status": "verified"})

        logger.info(f"Account verified: {platform}")
        return Result.success({"verified": True})

    def is_human_checkpoint(self, result: Result) -> bool:
        """Check if a result indicates a human checkpoint."""
        return result.error.startswith("HUMAN_CHECKPOINT:") if result.error else False

    def get_checkpoint_type(self, result: Result) -> str:
        """Extract checkpoint type from error."""
        if result.error and result.error.startswith("HUMAN_CHECKPOINT:"):
            return result.error.replace("HUMAN_CHECKPOINT:", "")
        return "unknown"

    def detect_human_checkpoint_in_page(self, page_text: str) -> tuple[bool, str]:
        """
        Scan page text for human checkpoint indicators.
        Returns (is_checkpoint, checkpoint_type).
        """
        text_lower = page_text.lower()
        for indicator in HUMAN_CHECKPOINT_INDICATORS:
            if indicator in text_lower:
                return True, indicator
        return False, ""

    def update_account_status(self, platform: str, status: str, notes: str = "") -> None:
        account = storage.get_account(platform)
        if account:
            storage.save_account({**account, "status": status, "notes": notes})

    def list_accounts(self) -> list[dict]:
        return storage.get_all_accounts()

    def _get_platform_config(self, platform: str) -> dict:
        """Return platform-specific config, falling back to default."""
        for key, cfg in PLATFORM_CONFIGS.items():
            if key in platform.lower():
                return cfg
        return PLATFORM_CONFIGS["default"]

    def infer_platform_from_url(self, url: str) -> str:
        """Extract platform identifier from a URL."""
        import re
        match = re.search(r"https?://(?:www\.)?([^/]+)", url)
        if match:
            return match.group(1).lower()
        return url


# Singleton
account_manager = AccountManager()
