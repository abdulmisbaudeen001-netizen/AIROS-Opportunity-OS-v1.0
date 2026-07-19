"""
AIROS Opportunity OS v1.0
Notification Engine — sends Telegram alerts and mission summaries.
Two levels: immediate (event-driven) and session summary.
"""

import logging
from typing import Optional
import httpx
from config import config
from utils import utcnow_iso

logger = logging.getLogger("airos.notification")

TELEGRAM_API = "https://api.telegram.org"
TIMEOUT = 15


class NotificationEngine:

    def __init__(self):
        self._chat_id: Optional[str] = None

    def set_chat_id(self, chat_id: str) -> None:
        """Set the active chat ID for notifications."""
        self._chat_id = str(chat_id)

    # ── Immediate notifications ───────────────────────────────────────────────

    def interview_invitation(self, organization: str, role: str, details: str = "") -> None:
        msg = (
            f"🎉 *Interview Invitation*\n\n"
            f"*Company:* {self._esc(organization)}\n"
            f"*Role:* {self._esc(role)}\n"
        )
        if details:
            msg += f"*Details:* {self._esc(details)}"
        self._send(msg)

    def offer_received(self, organization: str, role: str, details: str = "") -> None:
        msg = (
            f"🏆 *Job Offer Received\\!*\n\n"
            f"*Company:* {self._esc(organization)}\n"
            f"*Role:* {self._esc(role)}\n"
        )
        if details:
            msg += f"*Details:* {self._esc(details)}"
        self._send(msg)

    def verification_required(self, platform: str, email_subject: str = "") -> None:
        msg = (
            f"📧 *Verification Required*\n\n"
            f"*Platform:* {self._esc(platform)}\n"
            f"Please check your email and verify your account\\."
        )
        if email_subject:
            msg += f"\n*Email:* {self._esc(email_subject)}"
        self._send(msg)

    def approval_required(self, opportunity_title: str, organization: str, url: str, reason: str) -> None:
        msg = (
            f"⏳ *Approval Required*\n\n"
            f"*Opportunity:* {self._esc(opportunity_title)}\n"
            f"*Organization:* {self._esc(organization)}\n"
            f"*Reason:* {self._esc(reason)}\n\n"
            f"Reply /approve\\_{self._safe_id(opportunity_title)} to submit\\."
        )
        self._send(msg)

    def assessment_received(self, organization: str, details: str = "") -> None:
        msg = (
            f"📝 *Coding Assessment Received*\n\n"
            f"*From:* {self._esc(organization)}\n"
        )
        if details:
            msg += f"*Details:* {self._esc(details)}"
        self._send(msg)

    def browser_failure(self, task: str, error: str) -> None:
        msg = (
            f"⚠️ *Browser Error*\n\n"
            f"*Task:* {self._esc(task)}\n"
            f"*Error:* {self._esc(error[:200])}"
        )
        self._send(msg)

    def human_checkpoint(self, opportunity_title: str, checkpoint_type: str, url: str) -> None:
        msg = (
            f"🛑 *Human Action Required*\n\n"
            f"*Opportunity:* {self._esc(opportunity_title)}\n"
            f"*Type:* {self._esc(checkpoint_type)}\n"
            f"*URL:* {self._esc(url)}\n\n"
            f"Please complete this step manually\\."
        )
        self._send(msg)

    def mission_started(self, command: str) -> None:
        msg = f"🚀 *Mission Started*\n\nCommand: `{self._esc(command)}`\n_Processing\\.\\.\\._"
        self._send(msg)

    def plain_message(self, text: str) -> None:
        """Send a plain text message."""
        self._send(text, parse_mode="Markdown")

    # ── Session summary ───────────────────────────────────────────────────────

    def mission_summary(
        self,
        duration_seconds: int,
        jobs_found: int = 0,
        scholarships_found: int = 0,
        grants_found: int = 0,
        other_found: int = 0,
        applications_submitted: int = 0,
        awaiting_approval: int = 0,
        human_required: int = 0,
        emails_processed: int = 0,
        interviews: int = 0,
        offers: int = 0,
        errors: int = 0,
        notes: str = "",
    ) -> None:
        total_found = jobs_found + scholarships_found + grants_found + other_found
        minutes = duration_seconds // 60
        seconds = duration_seconds % 60

        lines = [
            "✅ *MISSION COMPLETE*\n",
            f"⏱ Duration: {minutes}m {seconds}s\n",
            "━━━━━━━━━━━━━━━━━━━━",
            "*Opportunities Found*",
            f"  📋 Jobs: {jobs_found}",
            f"  🎓 Scholarships: {scholarships_found}",
            f"  💰 Grants/Fellowships: {grants_found}",
        ]
        if other_found:
            lines.append(f"  🌐 Other: {other_found}")
        lines += [
            f"  📊 Total: {total_found}\n",
            "━━━━━━━━━━━━━━━━━━━━",
            "*Applications*",
            f"  ✔️ Submitted: {applications_submitted}",
            f"  ⏳ Awaiting Approval: {awaiting_approval}",
        ]
        if human_required:
            lines.append(f"  🛑 Human Required: {human_required}")
        lines += [
            f"\n━━━━━━━━━━━━━━━━━━━━",
            "*Email*",
            f"  📧 Processed: {emails_processed}",
            f"  🎤 Interviews: {interviews}",
            f"  🏆 Offers: {offers}",
            f"\n━━━━━━━━━━━━━━━━━━━━",
            f"⚠️ Errors: {errors}",
        ]
        if notes:
            lines.append(f"\n📝 {notes}")

        self._send("\n".join(lines))

    def email_summary(self, email_data: dict) -> None:
        categories = email_data.get("categories", {})
        total = email_data.get("total", 0)

        if total == 0:
            self._send("📭 *Email Check*\n\nNo new emails\\.")
            return

        lines = [f"📬 *Email Check — {total} new message(s)*\n"]
        for cat, count in categories.items():
            icon = {
                "interview": "🎤",
                "offer": "🏆",
                "verification": "📧",
                "coding_test": "📝",
                "rejection": "❌",
                "reminder": "🔔",
                "general": "📩",
            }.get(cat, "📩")
            lines.append(f"  {icon} {cat.replace('_', ' ').title()}: {count}")

        self._send("\n".join(lines))

    # ── File sending ──────────────────────────────────────────────────────────

    def send_document(self, pdf_bytes: bytes, filename: str, caption: str = "") -> None:
        """Send a PDF document via Telegram."""
        if not self._chat_id:
            logger.warning("No chat_id set — cannot send document")
            return
        url = f"{TELEGRAM_API}/bot{config.telegram_bot_token}/sendDocument"
        try:
            with httpx.Client(timeout=30) as client:
                client.post(url, data={
                    "chat_id": self._chat_id,
                    "caption": caption[:1024],
                }, files={"document": (filename, pdf_bytes, "application/pdf")})
        except Exception as e:
            logger.error(f"Failed to send document: {e}")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _send(self, text: str, parse_mode: str = "MarkdownV2") -> None:
        if not self._chat_id:
            logger.warning("No chat_id set — notification dropped")
            return
        url = f"{TELEGRAM_API}/bot{config.telegram_bot_token}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        try:
            with httpx.Client(timeout=TIMEOUT) as client:
                r = client.post(url, json=payload)
            if r.status_code != 200:
                # Try again without markdown if formatting issue
                payload["parse_mode"] = "Markdown"
                payload["text"] = text.replace("\\", "")
                with httpx.Client(timeout=TIMEOUT) as client:
                    client.post(url, json=payload)
        except Exception as e:
            logger.error(f"Notification send failed: {e}")

    def _esc(self, text: str) -> str:
        """Escape special MarkdownV2 characters."""
        import re
        special = r"_*[]()~`>#+-=|{}.!"
        return re.sub(r"([" + re.escape(special) + r"])", r"\\\1", str(text))

    def _safe_id(self, text: str) -> str:
        """Convert text to safe command suffix."""
        import re
        return re.sub(r"[^a-zA-Z0-9]", "_", text)[:20].lower()


# Singleton
notifier = NotificationEngine()
