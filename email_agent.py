"""
AIROS Opportunity OS v1.0
Email Agent — monitors the career Gmail account, classifies emails, extracts actions.
"""

import imaplib
import email
import logging
from email.header import decode_header
from typing import Optional
from config import config
from llm import llm
from prompts import prompts
from storage import storage
from utils import Result, utcnow_iso

logger = logging.getLogger("airos.email")

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993

HIGH_PRIORITY_CATEGORIES = {"interview", "offer", "coding_test", "verification"}


class EmailAgent:

    def check_inbox(self, limit: int = 20) -> Result:
        """
        Connect to Gmail via IMAP, fetch unread emails, classify them, store results.
        Returns structured list of processed emails.
        """
        if not config.email_address or not config.email_app_password:
            return Result.failed("Email credentials not configured.")

        try:
            mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
            mail.login(config.email_address, config.email_app_password)
            mail.select("inbox")
        except imaplib.IMAP4.error as e:
            return Result.retry(f"IMAP connection failed: {e}")
        except Exception as e:
            return Result.failed(f"Email connection error: {e}")

        try:
            _, message_numbers = mail.search(None, "UNSEEN")
            ids = message_numbers[0].split()[-limit:]  # Most recent N unread

            processed = []
            for msg_id in reversed(ids):  # Newest first
                result = self._process_email(mail, msg_id)
                if result:
                    processed.append(result)

            mail.logout()
            logger.info(f"Email check complete: {len(processed)} emails processed")
            return Result.success({"emails": processed, "count": len(processed)})

        except Exception as e:
            logger.error(f"Email processing error: {e}")
            try:
                mail.logout()
            except Exception:
                pass
            return Result.retry(str(e))

    def _process_email(self, mail: imaplib.IMAP4_SSL, msg_id: bytes) -> Optional[dict]:
        """Fetch, parse, classify, and store a single email."""
        try:
            _, msg_data = mail.fetch(msg_id, "(RFC822)")
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            subject = self._decode_header(msg.get("Subject", ""))
            sender = msg.get("From", "")
            date_str = msg.get("Date", "")
            message_id = msg.get("Message-ID", str(msg_id))

            body = self._extract_body(msg)

            # Classify
            classification = llm.generate_json(
                prompt=prompts.EMAIL_CLASSIFY.format(subject=subject, body=body[:2000]),
                temperature=0.1,
            )
            if not classification:
                classification = {
                    "category": "general",
                    "priority": "low",
                    "requires_action": False,
                    "action_type": "none",
                    "summary": subject,
                    "sender_organization": sender,
                    "deadline": None,
                }

            record = {
                "message_id": message_id,
                "subject": subject,
                "sender": sender,
                "body_preview": body[:500],
                "received_at": date_str,
                "category": classification.get("category", "general"),
                "priority": classification.get("priority", "low"),
                "requires_action": classification.get("requires_action", False),
                "action_type": classification.get("action_type", "none"),
                "summary": classification.get("summary", subject),
                "sender_organization": classification.get("sender_organization", sender),
                "deadline": classification.get("deadline"),
            }

            storage.save_email_record(record)
            return record

        except Exception as e:
            logger.warning(f"Failed to process email {msg_id}: {e}")
            return None

    def get_high_priority(self, processed_emails: list[dict]) -> list[dict]:
        """Filter emails requiring immediate notification."""
        return [e for e in processed_emails if e.get("category") in HIGH_PRIORITY_CATEGORIES]

    def get_verification_links(self, processed_emails: list[dict]) -> list[dict]:
        """Extract emails that contain verification links."""
        return [e for e in processed_emails if e.get("action_type") == "click_link" and e.get("category") == "verification"]

    def get_interview_emails(self, processed_emails: list[dict]) -> list[dict]:
        return [e for e in processed_emails if e.get("category") == "interview"]

    def get_summary(self, processed_emails: list[dict]) -> dict:
        """Aggregate email session statistics."""
        categories = {}
        high_priority = []

        for e in processed_emails:
            cat = e.get("category", "general")
            categories[cat] = categories.get(cat, 0) + 1
            if e.get("category") in HIGH_PRIORITY_CATEGORIES:
                high_priority.append(e)

        return {
            "total": len(processed_emails),
            "categories": categories,
            "high_priority": high_priority,
            "interviews": categories.get("interview", 0),
            "offers": categories.get("offer", 0),
            "verifications": categories.get("verification", 0),
            "tests": categories.get("coding_test", 0),
            "rejections": categories.get("rejection", 0),
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _decode_header(self, raw: str) -> str:
        try:
            parts = decode_header(raw)
            decoded = []
            for part, encoding in parts:
                if isinstance(part, bytes):
                    decoded.append(part.decode(encoding or "utf-8", errors="replace"))
                else:
                    decoded.append(str(part))
            return " ".join(decoded)
        except Exception:
            return str(raw)

    def _extract_body(self, msg: email.message.Message) -> str:
        """Extract plain text body from email."""
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))
                if content_type == "text/plain" and "attachment" not in content_disposition:
                    try:
                        charset = part.get_content_charset() or "utf-8"
                        body = part.get_payload(decode=True).decode(charset, errors="replace")
                        break
                    except Exception:
                        continue
        else:
            try:
                charset = msg.get_content_charset() or "utf-8"
                body = msg.get_payload(decode=True).decode(charset, errors="replace")
            except Exception:
                body = str(msg.get_payload())
        return body.strip()


# Singleton
email_agent = EmailAgent()
