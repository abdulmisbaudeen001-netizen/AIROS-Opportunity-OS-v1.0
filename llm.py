"""
AIROS Opportunity OS v1.0
LLM Engine — the only module that communicates with OpenRouter.
Handles model selection, failover, retries, and structured JSON responses.
"""

import logging
import time
from typing import Any, Optional
import httpx
from config import config
from utils import safe_json

logger = logging.getLogger("airos.llm")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
TIMEOUT = 60
MAX_RETRIES = 2


class LLMError(Exception):
    pass


class LLM:
    def __init__(self):
        self._models = [config.llm_model] + config.llm_fallback_models

    def ping(self) -> None:
        """Verify LLM connectivity."""
        result = self.generate(prompt="Reply with the word PONG and nothing else.")
        if not result:
            raise LLMError("LLM ping returned empty response.")

    def generate(
        self,
        prompt: str,
        system: str = "",
        json_mode: bool = False,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> Optional[str]:
        """
        Send a prompt to OpenRouter.
        Tries models in priority order with per-model retries.
        Returns the raw text response, or None on complete failure.
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        for model in self._models:
            for attempt in range(MAX_RETRIES + 1):
                try:
                    response = self._call(
                        model=model,
                        messages=messages,
                        json_mode=json_mode,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    logger.debug(f"LLM success: model={model} attempt={attempt+1}")
                    return response
                except LLMError as exc:
                    logger.warning(f"LLM error on model={model} attempt={attempt+1}: {exc}")
                    if attempt < MAX_RETRIES:
                        time.sleep(2 ** attempt)  # exponential back-off: 1s, 2s
                    else:
                        logger.warning(f"Model {model} exhausted retries, trying next.")
                        break

        logger.error("All LLM models failed.")
        return None

    def generate_json(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> Optional[dict]:
        """
        Generate a response and parse it as JSON.
        Forces JSON mode in the prompt and validates the response.
        """
        json_system = (system + "\n\n" if system else "") + (
            "You must respond ONLY with valid JSON. "
            "No markdown, no code fences, no explanation. "
            "Pure JSON object only."
        )
        raw = self.generate(
            prompt=prompt,
            system=json_system,
            json_mode=True,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if not raw:
            return None
        parsed = safe_json(raw)
        if parsed is None:
            logger.warning(f"LLM returned non-JSON: {raw[:300]}")
        return parsed

    def _call(
        self,
        model: str,
        messages: list[dict],
        json_mode: bool,
        temperature: float,
        max_tokens: int,
    ) -> str:
        headers = {
            "Authorization": f"Bearer {config.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://airos-opportunity-os.render.com",
            "X-Title": "AIROS Opportunity OS",
        }
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.post(OPENROUTER_URL, json=payload, headers=headers)

        if response.status_code == 429:
            raise LLMError(f"Rate limited on model {model}")
        if response.status_code >= 500:
            raise LLMError(f"Server error {response.status_code} on model {model}")
        if response.status_code != 200:
            raise LLMError(f"HTTP {response.status_code}: {response.text[:200]}")

        data = response.json()
        choices = data.get("choices", [])
        if not choices:
            raise LLMError(f"Empty choices from model {model}")

        content = choices[0].get("message", {}).get("content", "")
        if not content:
            raise LLMError(f"Empty content from model {model}")

        return content.strip()


# Singleton
llm = LLM()
