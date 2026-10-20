"""
tests/unit/test_groq_client.py — Unit tests for the Groq client wrapper.

All LLM calls are mocked — no real API key is needed to run these tests.
"""
from __future__ import annotations

import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from llm.groq_client import GroqClient


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    """A GroqClient instance with a fake API key."""
    return GroqClient(
        api_key="gsk_fake_key_for_testing",
        primary_model="openai/gpt-oss-120b",
        fallback_model="llama-3.3-70b-versatile",
    )


def _make_mock_response(content: str):
    """Build a mock ChatCompletion response object."""
    choice = MagicMock()
    choice.message.content = content
    choice.delta = MagicMock()
    usage = MagicMock()
    usage.total_tokens = 42
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = usage
    return resp


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestGroqClientInit:
    def test_uses_provided_api_key(self):
        c = GroqClient(api_key="gsk_test123")
        assert c._api_key == "gsk_test123"

    def test_uses_settings_model_by_default(self):
        c = GroqClient(api_key="gsk_test")
        from core.config import settings
        assert c.primary_model == settings.primary_model

    def test_raises_when_no_api_key(self):
        c = GroqClient(api_key="")
        with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
            _ = c.client  # accessing .client triggers validation


class TestGroqClientComplete:
    @pytest.mark.asyncio
    async def test_complete_returns_string(self, client):
        mock_resp = _make_mock_response("Hello from GPT-OSS!")
        with patch.object(client, "_client", new=MagicMock()) as mock_groq:
            mock_groq.chat.completions.create = AsyncMock(return_value=mock_resp)
            client._client = mock_groq
            result = await client.complete("You are helpful.", "Hi!")
        assert result == "Hello from GPT-OSS!"

    @pytest.mark.asyncio
    async def test_complete_json_parses_dict(self, client):
        payload = json.dumps({"status": "ok", "value": 42})
        mock_resp = _make_mock_response(payload)
        with patch.object(client, "_client", new=MagicMock()) as mock_groq:
            mock_groq.chat.completions.create = AsyncMock(return_value=mock_resp)
            client._client = mock_groq
            result = await client.complete_json("System.", "User.")
        assert result == {"status": "ok", "value": 42}

    @pytest.mark.asyncio
    async def test_complete_json_strips_markdown_fences(self, client):
        fenced = "```json\n{\"key\": \"val\"}\n```"
        mock_resp = _make_mock_response(fenced)
        with patch.object(client, "_client", new=MagicMock()) as mock_groq:
            mock_groq.chat.completions.create = AsyncMock(return_value=mock_resp)
            client._client = mock_groq
            result = await client.complete_json("System.", "User.")
        assert result == {"key": "val"}

    @pytest.mark.asyncio
    async def test_complete_json_raises_on_invalid_json(self, client):
        mock_resp = _make_mock_response("not json at all!!!")
        with patch.object(client, "_client", new=MagicMock()) as mock_groq:
            mock_groq.chat.completions.create = AsyncMock(return_value=mock_resp)
            client._client = mock_groq
            with pytest.raises(ValueError, match="non-JSON"):
                await client.complete_json("System.", "User.")

    @pytest.mark.asyncio
    async def test_fallback_on_primary_500(self, client):
        """Should switch to fallback model on 5xx errors."""
        from groq import APIStatusError
        import httpx

        primary_call_count = 0
        fallback_call_count = 0

        async def mock_create(**kwargs):
            nonlocal primary_call_count, fallback_call_count
            if kwargs.get("model") == "openai/gpt-oss-120b":
                primary_call_count += 1
                raise APIStatusError(
                    message="Server error",
                    response=MagicMock(status_code=500, headers={}),
                    body={},
                )
            else:
                fallback_call_count += 1
                return _make_mock_response("fallback response")

        with patch.object(client, "_client", new=MagicMock()) as mock_groq:
            mock_groq.chat.completions.create = mock_create
            client._client = mock_groq
            result = await client.complete("System.", "User.")

        assert fallback_call_count == 1
        assert result == "fallback response"


class TestGroqClientEdgeCases:
    @pytest.mark.asyncio
    async def test_empty_system_prompt_accepted(self, client):
        mock_resp = _make_mock_response("ok")
        with patch.object(client, "_client", new=MagicMock()) as mock_groq:
            mock_groq.chat.completions.create = AsyncMock(return_value=mock_resp)
            client._client = mock_groq
            result = await client.complete("", "Hello")
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_large_token_budget_passed(self, client):
        """Verify max_tokens is forwarded to the API call."""
        mock_resp = _make_mock_response("big response")
        with patch.object(client, "_client", new=MagicMock()) as mock_groq:
            mock_groq.chat.completions.create = AsyncMock(return_value=mock_resp)
            client._client = mock_groq
            await client.complete("Sys.", "User.", max_tokens=8192)
            call_kwargs = mock_groq.chat.completions.create.call_args.kwargs
        assert call_kwargs["max_tokens"] == 8192
