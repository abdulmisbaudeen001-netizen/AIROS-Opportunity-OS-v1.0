"""
AIROS Opportunity OS v1.0
Telegram Bot — the only user interface.
Receives messages, routes to Planner, handles file uploads.
"""

import logging
import threading
from typing import Optional
import httpx
from config import config
from profile import profile_manager
from notification import notifier
from utils import Result

logger = logging.getLogger("airos.telegram")

TELEGRAM_API = "https://api.telegram.org"
POLL_TIMEOUT = 30
MAX_RETRIES = 3


class TelegramBot:

    def __init__(self):
        self._offset = 0
        self._running = False

    def run(self) -> None:
        """Start polling loop. Blocks until stopped."""
        self._running = True
        logger.info("Telegram bot polling started.")
        retry_count = 0

        while self._running:
            try:
                updates = self._get_updates()
                retry_count = 0
                for update in updates:
                    self._handle_update(update)
            except Exception as exc:
                retry_count += 1
                logger.warning(f"Polling error (attempt {retry_count}): {exc}")
                if retry_count >= MAX_RETRIES:
                    logger.error("Polling failed repeatedly. Waiting 30 seconds before retry.")
                    import time
                    time.sleep(30)
                    retry_count = 0

    def stop(self) -> None:
        self._running = False

    # ── Update handling ───────────────────────────────────────────────────────

    def _handle_update(self, update: dict) -> None:
        """Route a single Telegram update."""
        update_id = update.get("update_id", 0)
        self._offset = update_id + 1

        message = update.get("message") or update.get("edited_message")
        if not message:
            return

        chat_id = str(message.get("chat", {}).get("id", ""))
        if not chat_id:
            return

        # Authorize — single-user bot
        if not self._is_authorized(chat_id):
            self._send_message(chat_id, "⛔ Unauthorized.")
            return

        # Handle document upload (CV import)
        if message.get("document"):
            threading.Thread(
                target=self._handle_document_upload,
                args=(message, chat_id),
                daemon=True,
            ).start()
            return

        # Handle text message
        text = message.get("text", "").strip()
        if not text:
            return

        # Import planner here to avoid circular at module level
        from planner import planner
        notifier.set_chat_id(chat_id)

        threading.Thread(
            target=planner.handle,
            args=(text, chat_id),
            daemon=True,
        ).start()

    def _handle_document_upload(self, message: dict, chat_id: str) -> None:
        """Handle CV file upload."""
        from planner import planner
        notifier.set_chat_id(chat_id)

        doc = message.get("document", {})
        filename = doc.get("file_name", "")
        file_id = doc.get("file_id", "")
        caption = message.get("caption", "").lower()

        if not file_id:
            notifier.plain_message("❌ Could not retrieve file.")
            return

        is_cv = any(w in caption for w in ["cv", "resume", "curriculum"]) or \
                any(filename.lower().endswith(ext) for ext in [".pdf", ".docx", ".doc"])

        if not is_cv:
            notifier.plain_message("📎 File received. If this is your CV, please caption it with 'cv' or 'resume'.")
            return

        notifier.plain_message("📄 CV received. Extracting your profile...")

        try:
            file_bytes = self._download_file(file_id)
            if not file_bytes:
                notifier.plain_message("❌ Failed to download file.")
                return

            text = self._extract_text_from_file(file_bytes, filename)
            if not text:
                notifier.plain_message("❌ Could not read file content. Please send a text-based PDF.")
                return

            result = profile_manager.import_cv_text(text)
            if result.ok():
                notifier.plain_message(
                    "✅ *CV imported successfully\\!*\n\n"
                    "Your profile has been updated\\. Run /profile to review it\\."
                )
                planner.handle("/profile", chat_id)
            else:
                notifier.plain_message(f"❌ CV import failed: {result.error}")

        except Exception as e:
            logger.error(f"Document upload error: {e}")
            notifier.plain_message(f"❌ Error processing file: {str(e)[:100]}")

    def _is_authorized(self, chat_id: str) -> bool:
        """
        Single-user authorization.
        On first use, any user is accepted and their chat_id is stored.
        Subsequent messages only accepted from that chat_id.
        """
        from storage import storage
        try:
            profile = storage.get_profile()
            stored_chat_id = profile.get("telegram_chat_id") if profile else None

            if not stored_chat_id:
                # First user — register them
                storage.upsert_profile({"telegram_chat_id": chat_id})
                return True

            return str(stored_chat_id) == str(chat_id)
        except Exception:
            # If storage fails, allow — don't lock out the user
            return True

    # ── Telegram API ──────────────────────────────────────────────────────────

    def _get_updates(self) -> list[dict]:
        url = f"{TELEGRAM_API}/bot{config.telegram_bot_token}/getUpdates"
        params = {"offset": self._offset, "timeout": POLL_TIMEOUT, "limit": 10}
        with httpx.Client(timeout=POLL_TIMEOUT + 10) as client:
            r = client.get(url, params=params)
        if r.status_code != 200:
            raise Exception(f"getUpdates failed: {r.status_code}")
        data = r.json()
        if not data.get("ok"):
            raise Exception(f"Telegram error: {data.get('description')}")
        return data.get("result", [])

    def _send_message(self, chat_id: str, text: str, parse_mode: str = "Markdown") -> None:
        url = f"{TELEGRAM_API}/bot{config.telegram_bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        try:
            with httpx.Client(timeout=15) as client:
                client.post(url, json=payload)
        except Exception as e:
            logger.error(f"sendMessage failed: {e}")

    def _download_file(self, file_id: str) -> Optional[bytes]:
        """Download a file from Telegram servers."""
        try:
            # Get file path
            url = f"{TELEGRAM_API}/bot{config.telegram_bot_token}/getFile"
            with httpx.Client(timeout=15) as client:
                r = client.get(url, params={"file_id": file_id})
            data = r.json()
            if not data.get("ok"):
                return None
            file_path = data["result"]["file_path"]

            # Download
            download_url = f"https://api.telegram.org/file/bot{config.telegram_bot_token}/{file_path}"
            with httpx.Client(timeout=30) as client:
                r = client.get(download_url)
            return r.content
        except Exception as e:
            logger.error(f"File download error: {e}")
            return None

    def _extract_text_from_file(self, file_bytes: bytes, filename: str) -> Optional[str]:
        """Extract text from PDF or DOCX."""
        filename_lower = filename.lower()
        try:
            if filename_lower.endswith(".pdf"):
                import io
                try:
                    import pypdf
                    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
                    return "\n".join(page.extract_text() or "" for page in reader.pages)
                except ImportError:
                    import pdfminer.high_level
                    return pdfminer.high_level.extract_text(io.BytesIO(file_bytes))

            elif filename_lower.endswith((".docx", ".doc")):
                import io
                import docx
                doc = docx.Document(io.BytesIO(file_bytes))
                return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

            else:
                # Try plain text
                return file_bytes.decode("utf-8", errors="replace")

        except Exception as e:
            logger.error(f"Text extraction failed for {filename}: {e}")
            return None


# Bot instance and run entry point
_bot = TelegramBot()


def run_bot() -> None:
    """Called from app.py to start the bot."""
    _bot.run()
