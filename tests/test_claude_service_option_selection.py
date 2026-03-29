"""Unit tests for ClaudeService option selection helper."""

from types import SimpleNamespace

import pytest
from loguru import logger

from app.services.claude_service import ClaudeAPIError, ClaudeService


class _FakeMessages:
    def __init__(self, response_text: str):
        self._response_text = response_text
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            content=[{"type": "text", "text": self._response_text}]
        )


# --- choose_emoji_for_place ---


def test_choose_emoji_for_place_returns_emoji():
    """Method returns emoji when Claude returns a short valid string."""
    service = ClaudeService(api_key="test-key")
    fake_client = _FakeClient("🌉")
    service._client = fake_client

    result = service.choose_emoji_for_place(
        candidate_context={
            "displayName": "Stone Arch Bridge",
            "primaryType": "bridge",
            "types": ["bridge", "landmark"],
        }
    )

    assert result == "🌉"
    assert len(fake_client.messages.calls) == 1


def test_choose_emoji_for_place_returns_none_when_empty_context():
    """Method returns None when candidate_context is empty."""
    service = ClaudeService(api_key="test-key")
    fake_client = _FakeClient("🌉")
    service._client = fake_client

    result = service.choose_emoji_for_place(candidate_context={})

    assert result is None
    assert len(fake_client.messages.calls) == 0


def test_choose_emoji_for_place_returns_none_when_response_too_long():
    """Method returns None when Claude returns a long string (not a single emoji)."""
    service = ClaudeService(api_key="test-key")
    fake_client = _FakeClient("A bridge emoji would be perfect for this landmark")
    service._client = fake_client

    result = service.choose_emoji_for_place(
        candidate_context={"displayName": "Stone Arch Bridge", "primaryType": "bridge"}
    )

    assert result is None
    assert len(fake_client.messages.calls) == 1


# --- choose_icon_search_term_for_place ---


def test_choose_icon_search_term_for_place_returns_term():
    """Method returns search term when Claude returns a short valid string."""
    service = ClaudeService(api_key="test-key")
    fake_client = _FakeClient("bridge")
    service._client = fake_client

    result = service.choose_icon_search_term_for_place(
        candidate_context={
            "displayName": "Stone Arch Bridge",
            "primaryType": "bridge",
            "types": ["bridge", "landmark"],
        }
    )

    assert result == "bridge"
    assert len(fake_client.messages.calls) == 1


def test_choose_icon_search_term_for_place_returns_none_when_empty_context():
    """Method returns None when candidate_context is empty."""
    service = ClaudeService(api_key="test-key")
    fake_client = _FakeClient("bridge")
    service._client = fake_client

    result = service.choose_icon_search_term_for_place(candidate_context={})

    assert result is None
    assert len(fake_client.messages.calls) == 0


def test_choose_icon_search_term_for_place_strips_punctuation():
    """Method strips punctuation from Claude output."""
    service = ClaudeService(api_key="test-key")
    fake_client = _FakeClient('"coffee shop"')
    service._client = fake_client

    result = service.choose_icon_search_term_for_place(
        candidate_context={"displayName": "Blue Bottle", "primaryType": "coffee_shop"}
    )

    assert result == "coffee shop"
    assert len(fake_client.messages.calls) == 1


def test_choose_icon_search_term_for_place_returns_none_when_response_too_long():
    """Method returns None when Claude returns a very long string."""
    service = ClaudeService(api_key="test-key")
    fake_client = _FakeClient("A" * 60)
    service._client = fake_client

    result = service.choose_icon_search_term_for_place(
        candidate_context={"displayName": "Test", "primaryType": "park"}
    )

    assert result is None
    assert len(fake_client.messages.calls) == 1


class _FakeClient:
    def __init__(self, response_text: str):
        self.messages = _FakeMessages(response_text)


def _capture_logs():
    captured = []

    def sink(message):
        record = message.record
        captured.append(
            {
                "message": record["message"],
                "extra": dict(record["extra"]),
                "level": record["level"].name,
            }
        )

    handler_id = logger.add(sink, level="INFO", format="{message}")
    return captured, handler_id


def test_choose_option_from_context_returns_canonical_allowed_option():
    """Method returns canonical option name on case-insensitive Claude match."""
    service = ClaudeService(api_key="test-key")
    fake_client = _FakeClient("park")
    service._client = fake_client

    result = service.choose_option_from_context(
        field_name="Main Type",
        options=["Museum", "Park"],
        candidate_context={"primaryType": "park", "displayName": "Loring Park"},
    )

    assert result == "Park"
    assert len(fake_client.messages.calls) == 1


def test_choose_option_from_context_rejects_non_allowed_response_and_logs():
    """Method returns None when Claude output is not in allowed options."""
    service = ClaudeService(api_key="test-key")
    fake_client = _FakeClient("Castle")
    service._client = fake_client
    logs, handler_id = _capture_logs()
    try:
        result = service.choose_option_from_context(
            field_name="Main Type",
            options=["Museum", "Park"],
            candidate_context={"primaryType": "tourist_attraction"},
        )
    finally:
        logger.remove(handler_id)

    assert result is None
    assert len(fake_client.messages.calls) == 1
    response_log = next(
        e for e in logs if e["message"] == "claude_option_selection_response"
    )
    assert response_log["extra"]["property_name"] == "Main Type"
    assert response_log["extra"]["claude_raw_value"] == "Castle"
    rejected_log = next(
        e for e in logs if e["message"] == "claude_option_selection_rejected"
    )
    assert rejected_log["level"] == "WARNING"


def test_choose_option_from_context_skips_when_no_options():
    """Method does not call Claude when options are empty."""
    service = ClaudeService(api_key="test-key")
    fake_client = _FakeClient("Park")
    service._client = fake_client

    result = service.choose_option_from_context(
        field_name="Main Type",
        options=[],
        candidate_context={"primaryType": "park"},
    )

    assert result is None
    assert len(fake_client.messages.calls) == 0


# --- choose_multi_select_from_context ---


def test_choose_multi_select_canonicalizes_and_dedupes():
    """Method returns canonical option names and deduplicates case variants."""
    service = ClaudeService(api_key="test-key")
    fake_client = _FakeClient("Landmark, restaurant, Restaurant, History")
    service._client = fake_client

    result = service.choose_multi_select_from_context(
        field_name="Tags",
        options=["Landmark", "History", "Always Free", "Restaurant"],
        candidate_context={"primaryType": "restaurant", "types": ["landmark"]},
        allow_suggest_new=False,
    )

    assert result == ["Landmark", "Restaurant", "History"]
    assert len(fake_client.messages.calls) == 1


def test_choose_multi_select_rejects_non_allowed_when_allow_suggest_new_false():
    """Method drops values not in options when allow_suggest_new=False."""
    service = ClaudeService(api_key="test-key")
    fake_client = _FakeClient("Landmark, Castle, History")
    service._client = fake_client

    result = service.choose_multi_select_from_context(
        field_name="Tags",
        options=["Landmark", "History"],
        candidate_context={"primaryType": "tourist_attraction"},
        allow_suggest_new=False,
    )

    assert result == ["Landmark", "History"]
    assert "Castle" not in result


def test_choose_multi_select_allows_new_when_allow_suggest_new_true():
    """Method keeps plausible new values when allow_suggest_new=True."""
    service = ClaudeService(api_key="test-key")
    fake_client = _FakeClient("Landmark, History, Bridge")
    service._client = fake_client

    result = service.choose_multi_select_from_context(
        field_name="Tags",
        options=["Landmark", "History", "Always Free"],
        candidate_context={"displayName": "Stone Arch Bridge", "primaryType": "bridge"},
        allow_suggest_new=True,
    )

    assert "Landmark" in result
    assert "History" in result
    assert "Bridge" in result
    assert result.count("Bridge") == 1


def test_choose_multi_select_skips_when_no_options():
    """Method returns empty list and does not call Claude when options are empty."""
    service = ClaudeService(api_key="test-key")
    fake_client = _FakeClient("Landmark, History")
    service._client = fake_client

    result = service.choose_multi_select_from_context(
        field_name="Tags",
        options=[],
        candidate_context={"primaryType": "landmark"},
        allow_suggest_new=True,
    )

    assert result == []
    assert len(fake_client.messages.calls) == 0


class _BoomMessages:
    def create(self, **kwargs):
        err = RuntimeError("simulated API failure")
        err.status_code = 503  # type: ignore[attr-defined]
        raise err


class _BoomClient:
    messages = _BoomMessages()


def test_choose_multi_select_raises_claude_api_error_on_messages_failure():
    """API errors become ClaudeAPIError with operation and structured fields."""
    service = ClaudeService(api_key="test-key")
    service._client = _BoomClient()
    with pytest.raises(ClaudeAPIError) as ei:
        service.choose_multi_select_from_context(
            field_name="Tags",
            options=["Landmark"],
            candidate_context={"primaryType": "landmark"},
            allow_suggest_new=False,
        )
    assert ei.value.operation == "choose_multi_select_from_context"
    assert ei.value.service == "ClaudeService"
    assert ei.value.status_code == 503
    assert ei.value.retryable is True


def test_choose_multi_select_returns_empty_when_no_match():
    """Method returns empty list when Claude returns empty or no valid options."""
    service = ClaudeService(api_key="test-key")
    fake_client = _FakeClient("")
    service._client = fake_client

    result = service.choose_multi_select_from_context(
        field_name="Tags",
        options=["Landmark", "History"],
        candidate_context={"primaryType": "point_of_interest"},
        allow_suggest_new=False,
    )

    assert result == []
    assert len(fake_client.messages.calls) == 1


def test_choose_multi_select_parses_json_values_shape():
    """Method accepts JSON object responses with values array."""
    service = ClaudeService(api_key="test-key")
    fake_client = _FakeClient('{"values":["Landmark","History","landmark"]}')
    service._client = fake_client

    result = service.choose_multi_select_from_context(
        field_name="Tags",
        options=["Landmark", "History"],
        candidate_context={"primaryType": "point_of_interest"},
        allow_suggest_new=False,
    )

    assert result == ["Landmark", "History"]


def test_choose_multi_select_rejects_prose_like_new_suggestions():
    """Method ignores sentence-like suggested tags even when suggest-new is enabled."""
    service = ClaudeService(api_key="test-key")
    fake_client = _FakeClient("Landmark, I don't see strong indicators that match tags")
    service._client = fake_client

    result = service.choose_multi_select_from_context(
        field_name="Tags",
        options=["Landmark", "History"],
        candidate_context={"primaryType": "landmark"},
        allow_suggest_new=True,
    )

    assert result == ["Landmark"]


# --- choose_option_with_suggest_from_context ---


def test_choose_option_with_suggest_returns_matched_option():
    """Method returns (canonical_option, False) when Claude matches an allowed option."""
    service = ClaudeService(api_key="test-key")
    fake_client = _FakeClient("South Minneapolis")
    service._client = fake_client

    from app.services.claude_service import OptionSelectionResult

    result = service.choose_option_with_suggest_from_context(
        field_name="Neighborhood",
        options=["South Minneapolis", "North Loop"],
        candidate_context={
            "neighborhood": "Loring Park",
            "formattedAddress": "1382 Willow St, Minneapolis, MN",
        },
        allow_suggest_new=True,
    )

    assert isinstance(result, OptionSelectionResult)
    assert result.value == "South Minneapolis"
    assert result.is_new is False
    assert len(fake_client.messages.calls) == 1


def test_choose_option_with_suggest_returns_new_value_when_allow_suggest_new():
    """Method returns (suggested_value, True) when no match and allow_suggest_new=True."""
    service = ClaudeService(api_key="test-key")
    fake_client = _FakeClient('{"value":"Uptown","confidence":0.92,"source":"address neighborhood"}')
    service._client = fake_client

    from app.services.claude_service import OptionSelectionResult

    result = service.choose_option_with_suggest_from_context(
        field_name="Neighborhood",
        options=["South Minneapolis", "North Loop"],
        candidate_context={
            "neighborhood": "Uptown",
            "formattedAddress": "1633 Lyndale Ave S, Minneapolis, MN",
        },
        allow_suggest_new=True,
    )

    assert isinstance(result, OptionSelectionResult)
    assert result.value == "Uptown"
    assert result.is_new is True
    assert len(fake_client.messages.calls) == 1


def test_choose_option_with_suggest_rejects_low_confidence_new_value():
    """Method rejects suggested new value when confidence is low."""
    service = ClaudeService(api_key="test-key")
    fake_client = _FakeClient('{"value":"Uptown","confidence":0.4,"source":"weak hint"}')
    service._client = fake_client

    result = service.choose_option_with_suggest_from_context(
        field_name="Neighborhood",
        options=["South Minneapolis", "North Loop"],
        candidate_context={"neighborhood": "Uptown"},
        allow_suggest_new=True,
    )

    assert result.value is None
    assert result.is_new is False


def test_choose_option_with_suggest_rejects_new_when_allow_suggest_new_false():
    """Method returns (None, False) when Claude suggests non-allowed and allow_suggest_new=False."""
    service = ClaudeService(api_key="test-key")
    fake_client = _FakeClient("Uptown")
    service._client = fake_client

    from app.services.claude_service import OptionSelectionResult

    result = service.choose_option_with_suggest_from_context(
        field_name="Neighborhood",
        options=["South Minneapolis", "North Loop"],
        candidate_context={"neighborhood": "Uptown"},
        allow_suggest_new=False,
    )

    assert isinstance(result, OptionSelectionResult)
    assert result.value is None
    assert result.is_new is False


def test_choose_option_with_suggest_skips_when_no_options():
    """Method returns (None, False) and does not call Claude when options are empty."""
    service = ClaudeService(api_key="test-key")
    fake_client = _FakeClient("Uptown")
    service._client = fake_client

    from app.services.claude_service import OptionSelectionResult

    result = service.choose_option_with_suggest_from_context(
        field_name="Neighborhood",
        options=[],
        candidate_context={"neighborhood": "Uptown"},
        allow_suggest_new=True,
    )

    assert isinstance(result, OptionSelectionResult)
    assert result.value is None
    assert result.is_new is False
    assert len(fake_client.messages.calls) == 0


# --- rewrite_query_for_target ---


def test_rewrite_query_for_target_with_schema_injects_description_and_hints():
    """rewrite_query_for_target with query_schema builds prompt with description and hints."""
    service = ClaudeService(api_key="test-key")
    fake_client = _FakeClient("Stone Arch Bridge Minneapolis MN")
    service._client = fake_client

    result = service.rewrite_query_for_target(
        "stone arch bridge in minneapolis",
        query_schema={
            "description": "Text query for Google Places searchText API",
            "hints": ["Include place name and location", "Prefer format: Place Name City Region"],
        },
    )

    assert result == "Stone Arch Bridge Minneapolis MN"
    assert len(fake_client.messages.calls) == 1
    call = fake_client.messages.calls[0]
    assert "Target API: Text query for Google Places searchText API" in call["system"]
    assert "Include place name and location" in call["system"]
    assert "Prefer format: Place Name City Region" in call["system"]
    assert "Rewrite: stone arch bridge in minneapolis" in call["messages"][0]["content"]


def test_rewrite_query_for_target_without_schema_delegates_to_rewrite_place_query():
    """rewrite_query_for_target without query_schema delegates to rewrite_place_query."""
    service = ClaudeService(api_key="test-key")
    fake_client = _FakeClient("Stone Arch Bridge Minneapolis MN")
    service._client = fake_client

    result = service.rewrite_query_for_target("stone arch bridge minneapolis", query_schema=None)

    assert result == "Stone Arch Bridge Minneapolis MN"
    assert len(fake_client.messages.calls) == 1
    call = fake_client.messages.calls[0]
    assert "Google Places" in call["system"]


def test_rewrite_query_for_target_empty_query_returns_empty():
    """rewrite_query_for_target returns empty string when input is empty."""
    service = ClaudeService(api_key="test-key")
    fake_client = _FakeClient("ignored")
    service._client = fake_client

    result = service.rewrite_query_for_target("", query_schema={"description": "Test"})

    assert result == ""
    assert len(fake_client.messages.calls) == 0


def test_optimize_input_llm_trace_recorded_for_rewrite_place_query():
    """After rewrite_place_query, get_last_optimize_input_llm_trace has system, user, assistant."""
    service = ClaudeService(api_key="test-key")
    fake_client = _FakeClient("Bridge Minneapolis MN")
    service._client = fake_client

    service.clear_last_optimize_input_trace()
    assert service.get_last_optimize_input_llm_trace() is None

    out = service.rewrite_place_query("stone arch bridge")
    assert out == "Bridge Minneapolis MN"
    trace = service.get_last_optimize_input_llm_trace()
    assert trace is not None
    assert trace["model"]
    assert "Google Places" in trace["system_prompt"]
    assert "stone arch bridge" in trace["user_message"]
    assert trace["assistant_text"] == "Bridge Minneapolis MN"


def test_optimize_input_llm_trace_recorded_for_rewrite_query_for_target_with_schema():
    """rewrite_query_for_target with schema records full trace."""
    service = ClaudeService(api_key="test-key")
    fake_client = _FakeClient("Optimized result")
    service._client = fake_client

    out = service.rewrite_query_for_target(
        "query here",
        query_schema={"description": "Some API", "hints": ["hint a"]},
        base_prompt=None,
    )
    assert out == "Optimized result"
    trace = service.get_last_optimize_input_llm_trace()
    assert trace is not None
    assert "Some API" in trace["system_prompt"]
    assert "hint a" in trace["system_prompt"]
    assert "query here" in trace["user_message"]
    assert trace["assistant_text"] == "Optimized result"


def test_clear_last_optimize_input_trace():
    service = ClaudeService(api_key="test-key")
    fake_client = _FakeClient("x")
    service._client = fake_client
    service.rewrite_place_query("a")
    assert service.get_last_optimize_input_llm_trace() is not None
    service.clear_last_optimize_input_trace()
    assert service.get_last_optimize_input_llm_trace() is None
