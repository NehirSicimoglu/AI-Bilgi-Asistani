"""Gemini LLM sağlayıcısı (fake istemci ile, ağsız)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.config import Settings
from app.exceptions import ProviderError
from app.models.domain import Role
from app.providers.llm.base import LLMMessage, LLMProvider
from app.providers.llm.gemini import GeminiLLMProvider


class _FakeAioModels:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.last_call: dict | None = None

    async def generate_content(self, *, model, contents, config):
        self.last_call = {"model": model, "contents": contents, "config": config}
        if self.fail:
            raise RuntimeError("boom")
        return SimpleNamespace(
            text="merhaba dünya",
            usage_metadata=SimpleNamespace(
                prompt_token_count=10, candidates_token_count=5, total_token_count=15
            ),
        )

    async def generate_content_stream(self, *, model, contents, config):
        if self.fail:
            raise RuntimeError("boom")

        async def _gen():
            for piece in ["mer", "haba", " dünya"]:
                yield SimpleNamespace(text=piece)

        return _gen()


class _FakeClient:
    def __init__(self, fail: bool = False) -> None:
        self.aio = SimpleNamespace(models=_FakeAioModels(fail))


def _settings() -> Settings:
    return Settings(llm_model="gemini-flash-latest", llm_temperature=0.3)


def _msgs() -> list[LLMMessage]:
    return [LLMMessage(role=Role.USER, content="selam")]


def test_satisfies_interface() -> None:
    assert isinstance(GeminiLLMProvider(_settings(), client=_FakeClient()), LLMProvider)


async def test_generate_returns_text_and_usage() -> None:
    provider = GeminiLLMProvider(_settings(), client=_FakeClient())
    resp = await provider.generate(_msgs(), system="Sen bir asistansın.")
    assert resp.text == "merhaba dünya"
    assert resp.usage.total_tokens == 15
    assert resp.usage.prompt_tokens == 10


async def test_role_mapping_and_system() -> None:
    client = _FakeClient()
    provider = GeminiLLMProvider(_settings(), client=client)
    await provider.generate(
        [
            LLMMessage(role=Role.USER, content="soru"),
            LLMMessage(role=Role.ASSISTANT, content="cevap"),
        ],
        system="sistem",
    )
    call = client.aio.models.last_call
    assert [c.role for c in call["contents"]] == ["user", "model"]
    assert call["config"].system_instruction == "sistem"


async def test_stream_yields_pieces() -> None:
    provider = GeminiLLMProvider(_settings(), client=_FakeClient())
    out = [chunk async for chunk in provider.stream(_msgs())]
    assert "".join(out) == "merhaba dünya"


async def test_generate_error_wrapped() -> None:
    provider = GeminiLLMProvider(_settings(), client=_FakeClient(fail=True))
    with pytest.raises(ProviderError):
        await provider.generate(_msgs())


async def test_stream_error_wrapped() -> None:
    provider = GeminiLLMProvider(_settings(), client=_FakeClient(fail=True))
    with pytest.raises(ProviderError):
        _ = [c async for c in provider.stream(_msgs())]


def test_missing_api_key_raises() -> None:
    with pytest.raises(RuntimeError):
        GeminiLLMProvider(Settings(gemini_api_key=None))
