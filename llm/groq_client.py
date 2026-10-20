"""
llm/groq_client.py — Async Groq client wrapper for openai/gpt-oss-120b.

Handles:
- Structured JSON output with automatic retries
- Tool-calling schema formatting
- Rate-limit and transient error backoff via tenacity
- Model fallback when the primary model is unavailable
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

from groq import AsyncGroq, APIStatusError, APIConnectionError, RateLimitError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from core.config import settings

logger = logging.getLogger(__name__)

# Exceptions that are safe to retry
_RETRYABLE = (RateLimitError, APIConnectionError)


def _retry_decorator():
    return retry(
        retry=retry_if_exception_type(_RETRYABLE),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )


class GroqClient:
    """
    Async wrapper around the Groq Python SDK.
    All callers receive pure Python dicts/strings — no raw SDK objects leak out.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        primary_model: Optional[str] = None,
        fallback_model: Optional[str] = None,
    ) -> None:
        # An explicitly supplied empty key is a configuration error; do not
        # silently replace it with a process-wide key.
        self._api_key = settings.groq_api_key if api_key is None else api_key
        self.primary_model = primary_model or settings.primary_model
        self.fallback_model = fallback_model or settings.fallback_model
        self._client: Optional[AsyncGroq] = None

    @property
    def client(self) -> AsyncGroq:
        if self._client is None:
            if not self._api_key or self._api_key == "your_groq_api_key_here":
                raise RuntimeError(
                    "GROQ_API_KEY is not configured. "
                    "Set it in your .env file and restart."
                )
            self._client = AsyncGroq(api_key=self._api_key)
        return self._client

    # ── Low-level completion ──────────────────────────────────────────────

    async def _chat(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None,
    ) -> str:
        """Raw chat completion; returns the assistant's text content."""
        kwargs: Dict[str, Any] = dict(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if response_format:
            kwargs["response_format"] = response_format

        t0 = time.perf_counter()
        response = await self.client.chat.completions.create(**kwargs)
        elapsed = (time.perf_counter() - t0) * 1000

        content = response.choices[0].message.content or ""
        tokens = response.usage.total_tokens if response.usage else "?"
        logger.debug(
            "Groq [%s] | tokens=%s | %.0f ms | model=%s",
            model,
            tokens,
            elapsed,
            model,
        )
        return content

    # ── Public API ────────────────────────────────────────────────────────

    @_retry_decorator()
    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> str:
        """
        High-level text completion.  Uses primary model; falls back on failure.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        response_format = {"type": "json_object"} if json_mode else None

        try:
            return await self._chat(
                messages, self.primary_model, temperature, max_tokens, response_format
            )
        except APIStatusError as exc:
            if exc.status_code in (429, 503, 500):
                logger.warning(
                    "Primary model %s failed (%s). Falling back to %s.",
                    self.primary_model,
                    exc.status_code,
                    self.fallback_model,
                )
                return await self._chat(
                    messages, self.fallback_model, temperature, max_tokens, response_format
                )
            raise

    @_retry_decorator()
    async def complete_json(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> Dict[str, Any]:
        """
        Completion that guarantees a parsed JSON dict is returned.
        Raises ValueError if the model returns invalid JSON.
        """
        raw = await self.complete(
            system_prompt=system_prompt,
            user_message=user_message,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
        )
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            # Attempt lenient strip of markdown fences and retry parse
            stripped = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                raise ValueError(
                    f"Model returned non-JSON output.\nError: {exc}\nRaw: {raw[:500]}"
                ) from exc

    async def stream_complete(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ):
        """
        Async generator that yields text chunks for streaming displays.
        Usage:
            async for chunk in client.stream_complete(...):
                print(chunk, end="", flush=True)
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        stream = await self.client.chat.completions.create(
            model=self.primary_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


# Module-level singleton
groq_client = GroqClient()
