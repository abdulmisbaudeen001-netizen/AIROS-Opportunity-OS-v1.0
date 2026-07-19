"""
AIROS Opportunity OS v1.0
Main application entry point.
Initializes all providers and starts the Telegram bot.
"""

import logging
import sys
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
    """Verify all required providers are reachable before accepting messages."""

    logger.info("AIROS Opportunity OS v1.0 starting...")

    # Config validation
    logger.info("Loading configuration...")
    config.validate()
    logger.info("Configuration OK")

    # Storage
    logger.info("Connecting to Supabase...")
    storage.ping()
    logger.info("Supabase OK")

    # LLM
    logger.info("Initializing LLM engine...")
    llm.ping()
    logger.info("LLM engine OK")

    # Browser (non-fatal — missions can still run without browser if degraded)
    logger.info("Initializing browser engine...")
    try:
        browser.ping()
        logger.info("Browser engine OK")
    except Exception as exc:
        logger.warning(f"Browser engine unavailable: {exc}. Browser-dependent tasks will fail gracefully.")

    logger.info("All systems ready. Starting Telegram bot...")


def main() -> None:
    try:
        startup_checks()
        run_bot()
    except KeyboardInterrupt:
        logger.info("Shutdown requested. Exiting.")
        sys.exit(0)
    except Exception as exc:
        logger.critical(f"Fatal startup error: {exc}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
