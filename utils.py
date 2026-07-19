"""
AIROS Opportunity OS v1.0
Shared utility functions — no business logic, no external calls.
"""

import hashlib
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("airos.utils")


# ── Result envelope ──────────────────────────────────────────────────────────

class Result:
    SUCCESS = "SUCCESS"
    RETRY = "RETRY"
    FAILED = "FAILED"

    def __init__(self, status: str, data: Any = None, error: str = ""):
        self.status = status
        self.data = data
        self.error = error

    def ok(self) -> bool:
        return self.status == self.SUCCESS

    def should_retry(self) -> bool:
        return self.status == self.RETRY

    def to_dict(self) -> dict:
        return {"status": self.status, "data": self.data, "error": self.error}

    @classmethod
    def success(cls, data: Any = None) -> "Result":
        return cls(cls.SUCCESS, data=data)

    @classmethod
    def retry(cls, error: str = "") -> "Result":
        return cls(cls.RETRY, error=error)

    @classmethod
    def failed(cls, error: str = "") -> "Result":
        return cls(cls.FAILED, error=error)

    def __repr__(self):
        return f"Result({self.status}, error={self.error!r})"


# ── ID / hashing ─────────────────────────────────────────────────────────────

def new_id() -> str:
    return str(uuid.uuid4())


def mission_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"mission_{ts}_{uuid.uuid4().hex[:6]}"


def opportunity_hash(title: str, organization: str, url: str = "") -> str:
    """Stable fingerprint for duplicate detection."""
    raw = f"{title.lower().strip()}|{organization.lower().strip()}|{url.strip()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ── JSON helpers ─────────────────────────────────────────────────────────────

def safe_json(text: str) -> Optional[dict]:
    """Extract and parse JSON from an LLM response that may contain markdown fences."""
    # Strip markdown fences
    text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find the first {...} block
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    logger.warning(f"Failed to parse JSON from LLM output: {text[:200]}")
    return None


def to_json(obj: Any, indent: int = 2) -> str:
    return json.dumps(obj, indent=indent, default=str, ensure_ascii=False)


# ── Date helpers ──────────────────────────────────────────────────────────────

def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utcnow_iso() -> str:
    return utcnow().isoformat()


def days_until(deadline_str: str) -> Optional[int]:
    """Parse a deadline string and return days remaining. Returns None if unparseable."""
    formats = ["%Y-%m-%d", "%d %B %Y", "%B %d, %Y", "%d/%m/%Y", "%m/%d/%Y"]
    for fmt in formats:
        try:
            deadline = datetime.strptime(deadline_str.strip(), fmt).replace(tzinfo=timezone.utc)
            return (deadline - utcnow()).days
        except ValueError:
            continue
    return None


# ── Text helpers ──────────────────────────────────────────────────────────────

def truncate(text: str, max_chars: int = 4000) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 3] + "..."


def clean_text(text: str) -> str:
    """Collapse whitespace and strip."""
    return re.sub(r"\s+", " ", text).strip()


def extract_emails(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)


def extract_urls(text: str) -> list[str]:
    return re.findall(r"https?://[^\s\"'>]+", text)


# ── Telegram formatting ───────────────────────────────────────────────────────

def escape_markdown(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    special = r"_*[]()~`>#+-=|{}.!"
    return re.sub(r"([" + re.escape(special) + r"])", r"\\\1", str(text))


def bold(text: str) -> str:
    return f"*{escape_markdown(str(text))}*"


def code_block(text: str) -> str:
    return f"```\n{text}\n```"
