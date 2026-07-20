"""
AIROS Opportunity OS v1.0
Main application entry point.
Runs FastAPI (web UI + REST API) and Telegram bot concurrently.
"""

import logging
import sys
import threading
import uvicorn
from config import config
from storage import storage
from llm import llm
from browser import browser
from telegram_bot import run_bot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger("airos.app")


def startup_checks() -> None:
    """Verify all required providers are reachable before accepting traffic."""
    logger.info("AIROS Opportunity OS v1.0 starting...")

    logger.info("Loading configuration...")
    config.validate()
    logger.info("Configuration OK")

    logger.info("Connecting to Supabase...")
    storage.ping()
    logger.info("Supabase OK")

    logger.info("Initializing LLM engine...")
    llm.ping()
    logger.info("LLM engine OK")

    logger.info("Initializing browser engine...")
    try:
        browser.ping()
        logger.info("Browser engine OK")
    except Exception as exc:
        logger.warning(f"Browser engine unavailable: {exc}. Browser-dependent tasks will fail gracefully.")

    logger.info("All systems ready.")


def run_telegram() -> None:
    """Run Telegram polling in a background thread."""
    try:
        run_bot()
    except Exception as exc:
        logger.error(f"Telegram bot crashed: {exc}", exc_info=True)


def main() -> None:
    try:
        startup_checks()

        # Start Telegram bot in background thread
        telegram_thread = threading.Thread(target=run_telegram, daemon=True)
        telegram_thread.start()
        logger.info("Telegram bot started in background thread.")

        # Start FastAPI (serves web UI + REST API) in main thread
        from api import create_app
        app = create_app()
        port = config.web_port
        logger.info(f"Starting web server on port {port}...")
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")

    except KeyboardInterrupt:
        logger.info("Shutdown requested. Exiting.")
        sys.exit(0)
    except Exception as exc:
        logger.critical(f"Fatal startup error: {exc}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
