"""Unit tests for ClaudeService ai_prompt trace and prompt_completion."""

from types import SimpleNamespace

from app.llm_defaults import CLAUDE_HAIKU_45_MODEL
from app.services.claude_service import ClaudeService


class _FakeMessagesAiPrompt:
    def __init__(self, response_text: str):
        self._response_text = response_text

    def create(self, **kwargs):
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=self._response_text)],
            usage=SimpleNamespace(input_tokens=10, output_tokens=5),
            model=CLAUDE_HAIKU_45_MODEL,
        )


class _FakeClientAiPrompt:
    def __init__(self, response_text: str):
        self.messages = _FakeMessagesAiPrompt(response_text)


def test_prompt_completion_records_ai_prompt_trace():
    service = ClaudeService(api_key="test-key")
    fake_client = _FakeClientAiPrompt("hello model")
    service._client = fake_client

    service.clear_last_ai_prompt_trace()
    result = service.prompt_completion("Say hi", "world", max_tokens=512)

    assert result == "hello model"
    trace = service.get_last_ai_prompt_llm_trace()
    assert trace is not None
    assert trace["operation"] == "ai_prompt"
    assert trace["model"] == CLAUDE_HAIKU_45_MODEL
    assert trace["max_tokens"] == 512
    assert "world" in trace["user_message"]
    assert trace["assistant_text"] == "hello model"
    assert trace["usage"] is not None
    assert trace["usage"]["input_tokens"] == 10
    assert trace["usage"]["output_tokens"] == 5
    assert "You follow instructions precisely" in trace["system_prompt"]


def test_clear_last_ai_prompt_trace_clears_snapshot():
    service = ClaudeService(api_key="test-key")
    service._client = _FakeClientAiPrompt("x")
    service.prompt_completion("p", "v")
    assert service.get_last_ai_prompt_llm_trace() is not None
    service.clear_last_ai_prompt_trace()
    assert service.get_last_ai_prompt_llm_trace() is None
