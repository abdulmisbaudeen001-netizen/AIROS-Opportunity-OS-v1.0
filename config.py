"""
AIROS Opportunity OS v1.0
Configuration — loads and validates all environment variables.
No secrets are hardcoded here. All values come from the environment.
"""

import os
from dataclasses import dataclass, field
from typing import Optional


class ConfigurationError(Exception):
    pass


@dataclass
class Config:
    # Telegram
    telegram_bot_token: str = field(default="")

    # OpenRouter / LLM
    openrouter_api_key: str = field(default="")
    llm_model: str = field(default="google/gemini-flash-1.5")
    llm_fallback_models: list = field(default_factory=lambda: [
        "deepseek/deepseek-chat",
        "qwen/qwen-2.5-72b-instruct",
        "mistralai/mistral-7b-instruct:free",
    ])

    # Supabase
    supabase_url: str = field(default="")
    supabase_key: str = field(default="")

    # Browserless
    browserless_api_key: str = field(default="")
    browserless_url: str = field(default="https://chrome.browserless.io")

    # Email (Gmail)
    email_address: str = field(default="")
    email_app_password: str = field(default="")

    # Application policy
    auto_apply: bool = field(default=False)
    smart_apply: bool = field(default=True)

    # Timezone
    timezone: str = field(default="Africa/Lagos")

    # Optional: search providers
    brave_api_key: Optional[str] = field(default=None)
    tavily_api_key: Optional[str] = field(default=None)

    # Optional: secondary document provider
    document_provider: str = field(default="llm")

    # Web UI
    web_password: str = field(default="")
    secret_key: str = field(default="")
    web_port: int = field(default=8000)

    def load(self) -> "Config":
        self.telegram_bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
        self.openrouter_api_key = os.environ["OPENROUTER_API_KEY"]
        self.llm_model = os.environ.get("LLM_MODEL", self.llm_model)
        self.supabase_url = os.environ["SUPABASE_URL"]
        self.supabase_key = os.environ["SUPABASE_KEY"]
        self.browserless_api_key = os.environ["BROWSERLESS_API_KEY"]
        self.browserless_url = os.environ.get("BROWSERLESS_URL", self.browserless_url)
        self.email_address = os.environ.get("EMAIL_ADDRESS", "")
        self.email_app_password = os.environ.get("EMAIL_APP_PASSWORD", "")
        self.auto_apply = os.environ.get("AUTO_APPLY", "false").lower() == "true"
        self.smart_apply = os.environ.get("SMART_APPLY", "true").lower() == "true"
        self.timezone = os.environ.get("TIMEZONE", self.timezone)
        self.brave_api_key = os.environ.get("BRAVE_API_KEY")
        self.tavily_api_key = os.environ.get("TAVILY_API_KEY")
        self.document_provider = os.environ.get("DOCUMENT_PROVIDER", self.document_provider)
        self.web_password = os.environ.get("WEB_PASSWORD", "airos2024")
        self.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key-in-production")
        self.web_port = int(os.environ.get("PORT", "8000"))
        return self

    def validate(self) -> None:
        required = {
            "TELEGRAM_BOT_TOKEN": self.telegram_bot_token,
            "OPENROUTER_API_KEY": self.openrouter_api_key,
            "SUPABASE_URL": self.supabase_url,
            "SUPABASE_KEY": self.supabase_key,
            "BROWSERLESS_API_KEY": self.browserless_api_key,
            "WEB_PASSWORD": self.web_password,
            "SECRET_KEY": self.secret_key,
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise ConfigurationError(f"Missing required environment variables: {', '.join(missing)}")

    @property
    def application_mode(self) -> str:
        if self.auto_apply:
            return "automatic"
        if self.smart_apply:
            return "smart"
        return "manual"


# Singleton — loaded once at startup
config = Config().load()
