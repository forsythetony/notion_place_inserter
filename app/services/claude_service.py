"""Claude API service wrapper for poem generation and place/property inference."""

import json
import re
from typing import NamedTuple

import anthropic
from loguru import logger


class OptionSelectionResult(NamedTuple):
    """Result of single-select with optional new value suggestion."""

    value: str | None
    is_new: bool


class ClaudeService:
    """Wraps the Anthropic API client for poem generation and place/property inference."""

    def __init__(self, api_key: str):
        self._client = anthropic.Anthropic(api_key=api_key)
        self._last_usage: dict | None = None

    def rewrite_place_query(self, raw_query: str) -> str:
        """
        Transform raw user query into a stronger Google Places search query.
        E.g. "stone arch bridge in minneapolis" -> "Stone Arch Bridge Minneapolis MN"
        """
        if not raw_query.strip():
            return raw_query
        response = self._client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=256,
            system="You are a search query optimizer. Rewrite the user's place search into a concise, effective Google Places text query. Return only the query string, no explanation.",
            messages=[{"role": "user", "content": f"Rewrite for Google Places search: {raw_query}"}],
        )
        return self._extract_text(response)

    def infer_property_value(
        self,
        prop_name: str,
        prop_type: str,
        options: list[str],
        research_snapshot: dict,
    ) -> str | None:
        """
        Use gathered research to infer a value for a Notion property.
        Returns a string (or None) suitable for formatting to Notion type.
        """
        snapshot_str = json.dumps(research_snapshot, default=str)[:8000]
        options_str = ", ".join(options) if options else "any value"
        prompt = f"""Given this research data about a place:
{snapshot_str}

Infer a value for the Notion property "{prop_name}" (type: {prop_type}).
Allowed options (if select/multi_select): {options_str}
Return only the value, nothing else. If you cannot infer, return empty string."""
        response = self._client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=256,
            system="You infer Notion property values from place research. Be concise.",
            messages=[{"role": "user", "content": prompt}],
        )
        result = self._extract_text(response)
        return result if result else None

    def choose_option_from_context(
        self,
        field_name: str,
        options: list[str],
        candidate_context: dict,
    ) -> str | None:
        """
        Choose one allowed option using provided context.
        Returns canonical option name or None when no valid match exists.
        """
        if not options:
            logger.bind(
                property_name=field_name,
                options=[],
                candidate_context=self._truncate_text(
                    json.dumps(candidate_context, default=str),
                    max_chars=2000,
                ),
            ).info("claude_option_selection_skipped_no_options")
            return None

        context_str = json.dumps(candidate_context, default=str)[:8000]
        options_str = self._truncate_text(
            json.dumps(options, default=str),
            max_chars=4000,
        )
        logger.info(
            "claude_option_selection_options | property_name={} options={}",
            field_name,
            options_str,
        )
        logger.bind(
            property_name=field_name,
            options=options,
            candidate_context=self._truncate_text(context_str, max_chars=2000),
        ).info("claude_option_selection_request")

        options_text = ", ".join(options)
        prompt = f"""Given this candidate context:
{context_str}

Select the best value for "{field_name}" from these allowed options:
{options_text}

Rules:
- Return exactly one option from the list when there is a clear match.
- If there is no clear match, return empty string.
- Return only the option text (or empty string), nothing else."""
        response = self._client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=128,
            system="You map structured place data to one allowed option. Do not invent options.",
            messages=[{"role": "user", "content": prompt}],
        )
        raw_value = self._extract_text(response).strip()
        logger.bind(
            property_name=field_name,
            options=options,
            claude_raw_value=raw_value,
        ).info("claude_option_selection_response")

        if not raw_value:
            logger.bind(property_name=field_name).info("claude_option_selection_no_match")
            return None

        for option in options:
            if option.lower() == raw_value.lower():
                logger.bind(
                    property_name=field_name,
                    selected_option=option,
                ).info("claude_option_selection_validated")
                return option

        logger.bind(
            property_name=field_name,
            options=options,
            claude_raw_value=raw_value,
        ).warning("claude_option_selection_rejected")
        return None

    def choose_option_with_suggest_from_context(
        self,
        field_name: str,
        options: list[str],
        candidate_context: dict,
        *,
        allow_suggest_new: bool = False,
    ) -> OptionSelectionResult:
        """
        Choose one option from allowed list or suggest a new value when no match exists.
        When allow_suggest_new=True and no option matches, may return one new value
        derived from context (e.g. neighborhood name). Returns (value, is_new) where
        is_new indicates the value was suggested rather than matched from options.
        """
        if not options:
            logger.bind(
                property_name=field_name,
                options=[],
                candidate_context=self._truncate_text(
                    json.dumps(candidate_context, default=str),
                    max_chars=2000,
                ),
            ).info("claude_option_suggest_skipped_no_options")
            return OptionSelectionResult(None, False)

        context_str = json.dumps(candidate_context, default=str)[:8000]
        options_text = ", ".join(options)
        logger.bind(
            property_name=field_name,
            options=options,
            candidate_context=self._truncate_text(context_str, max_chars=2000),
            allow_suggest_new=allow_suggest_new,
        ).info("claude_option_suggest_request")

        suggest_rule = ""
        if allow_suggest_new:
            suggest_rule = (
                "- If no option matches but the context clearly indicates a value "
                "(e.g. neighborhood name from address), you may return that value in Title Case. "
                "Only suggest when the evidence is strong. Do not invent values."
            )
        else:
            suggest_rule = "- Return ONLY a value from the allowed list. Do not invent options."

        prompt = f"""Given this candidate context:
{context_str}

Select the best value for "{field_name}" from these allowed options:
{options_text}

Rules:
- Return valid JSON object only: {{"value":"", "confidence":0.0, "source":""}}.
- "value" must be exactly one allowed option when there is a clear match.
- If there is no clear match, set "value" to empty string.
- "confidence" must be between 0 and 1.
- "source" should briefly describe what evidence was used.
{suggest_rule}
- Return JSON only, no markdown or extra text."""
        prompt_preview = self._truncate_text(prompt, max_chars=1200)
        logger.bind(
            property_name=field_name,
            options=options,
            claude_prompt_preview=prompt_preview,
        ).info("claude_option_suggest_prompt_preview")
        response = self._client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=128,
            system="You map structured place data to one option. Be precise.",
            messages=[{"role": "user", "content": prompt}],
        )
        raw_value = self._extract_text(response).strip()
        parsed = self._parse_option_with_suggest_response(raw_value)
        parsed_value = parsed.get("value", "")
        parsed_confidence = parsed.get("confidence")
        parsed_source = parsed.get("source", "")
        logger.bind(
            property_name=field_name,
            options=options,
            claude_raw_value=raw_value,
            parsed_value=parsed_value,
            parsed_confidence=parsed_confidence,
            parsed_source=parsed_source,
        ).info("claude_option_suggest_response")

        if not parsed_value:
            logger.bind(property_name=field_name).info("claude_option_suggest_no_match")
            return OptionSelectionResult(None, False)

        for option in options:
            if option.lower() == parsed_value.lower():
                logger.bind(
                    property_name=field_name,
                    selected_option=option,
                ).info("claude_option_suggest_validated")
                return OptionSelectionResult(option, False)

        if (
            allow_suggest_new
            and parsed_value.strip()
            and parsed_confidence is not None
            and parsed_confidence >= 0.7
        ):
            suggested = parsed_value.strip().title()
            logger.bind(
                property_name=field_name,
                suggested_value=suggested,
                parsed_confidence=parsed_confidence,
            ).info("claude_option_suggest_new_value")
            return OptionSelectionResult(suggested, True)

        logger.bind(
            property_name=field_name,
            options=options,
            claude_raw_value=parsed_value,
        ).warning("claude_option_suggest_rejected")
        return OptionSelectionResult(None, False)

    def choose_multi_select_from_context(
        self,
        field_name: str,
        options: list[str],
        candidate_context: dict,
        *,
        allow_suggest_new: bool = False,
    ) -> list[str]:
        """
        Choose zero or more allowed options using provided context.
        Returns a canonical list of option names (no duplicates, consistent casing).
        When allow_suggest_new=True, may include new values not in options if they
        make strong sense; otherwise restricts strictly to existing options.
        """
        if not options:
            logger.bind(
                property_name=field_name,
                options=[],
                candidate_context=self._truncate_text(
                    json.dumps(candidate_context, default=str),
                    max_chars=2000,
                ),
            ).info("claude_multi_select_skipped_no_options")
            return []

        context_str = json.dumps(candidate_context, default=str)[:8000]
        options_text = ", ".join(options)
        logger.info(
            "claude_multi_select_options | property_name={} options={} allow_suggest_new={}",
            field_name,
            options_text,
            allow_suggest_new,
        )
        logger.bind(
            property_name=field_name,
            options=options,
            candidate_context=self._truncate_text(context_str, max_chars=2000),
        ).info("claude_multi_select_request")

        suggest_rule = ""
        if allow_suggest_new:
            suggest_rule = (
                "- If the context strongly supports a tag not in the list and it would be "
                "meaningful (e.g. 'Landmark', 'History' for a historic bridge), you may add "
                "one or two such values. Use Title Case. Only suggest when confident."
            )
        else:
            suggest_rule = "- Return ONLY values from the allowed list. Do not invent options."

        prompt = f"""Given this candidate context:
{context_str}

Select all applicable values for "{field_name}" from these allowed options:
{options_text}

Rules:
- Return valid JSON only.
- Use this exact shape: {{"values": ["Tag One", "Tag Two"]}}.
- values must be an array of strings. Do not include duplicates.
- Match option names exactly (case-insensitive) when using allowed options.
{suggest_rule}
- If nothing applies, return {{"values": []}}.
- Return JSON only, no markdown or prose."""
        response = self._client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=256,
            system="You map structured place data to allowed multi-select options. Be concise.",
            messages=[{"role": "user", "content": prompt}],
        )
        raw_value = self._extract_text(response).strip()
        logger.bind(
            property_name=field_name,
            options=options,
            claude_raw_value=raw_value,
        ).info("claude_multi_select_response")

        canonical = self._canonicalize_multi_select(raw_value, options, allow_suggest_new)
        logger.bind(
            property_name=field_name,
            canonical_values=canonical,
        ).info("claude_multi_select_validated")
        return canonical

    def choose_best_relation_from_candidates(
        self,
        source_context: dict,
        candidates: list[dict],
        key_lookup: str = "title",
        *,
        prompt: str | None = None,
    ) -> str | None:
        """
        Choose the best matching page from a list of relation candidates.
        Uses source_context (e.g. Google Place data) to find the best match.
        Returns page ID of selected candidate, or None if no confident match.
        """
        if not candidates:
            logger.bind(key_lookup=key_lookup).info(
                "claude_relation_select_skipped_no_candidates"
            )
            return None

        context_str = json.dumps(source_context, default=str)[:8000]
        candidates_str = json.dumps(candidates, default=str)[:6000]
        extra = f"\n\nAdditional instructions: {prompt}" if prompt else ""

        system = (
            "You select the best matching relation from a list of candidates. "
            "Use address geography (city, state, region) and any display name or place metadata. "
            "Consider aliases: e.g. 'Twin Cities' matches Minneapolis/St. Paul metro; 'Minneapolis, MN' matches 'Twin Cities, MN' or 'Minneapolis'; city names match their metro/region. "
            "Return only the page ID of the best match, or empty string if no confident match."
        )
        user_prompt = f"""Given this source data (address, place name, or related fields):
{context_str}

And these relation candidates (each has "id" = page ID, "{key_lookup}" = lookup value):
{candidates_str}

Select the single best matching candidate. Use the "{key_lookup}" field and geography from the source (city, state, region). Match aliases (e.g. Twin Cities = Minneapolis metro, city = region).
- Return valid JSON only: {{"selected_id": "page-uuid"}} or {{"selected_id": ""}} if no match.
- Return empty string for selected_id when uncertain.
- Return JSON only, no markdown or prose.{extra}"""

        try:
            response = self._client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=128,
                system=system,
                messages=[{"role": "user", "content": user_prompt}],
            )
            raw = self._extract_text(response).strip()
            if not raw:
                return None
            if raw.startswith("{") and raw.endswith("}"):
                parsed = json.loads(raw)
                sel = parsed.get("selected_id", "")
                if isinstance(sel, str) and sel.strip():
                    # Validate it matches a candidate
                    for c in candidates:
                        if c.get("id") == sel:
                            return sel
            return None
        except Exception as exc:
            logger.warning(
                "claude_relation_select_exception | error={}", str(exc)
            )
            return None

    def _canonicalize_multi_select(
        self,
        raw_value: str,
        options: list[str],
        allow_suggest_new: bool,
    ) -> list[str]:
        """Parse raw output, match to canonical options, deduplicate, optionally keep new values."""
        if not raw_value.strip():
            return []

        options_lower = {o.lower(): o for o in options}
        seen_lower: set[str] = set()
        result: list[str] = []

        raw_stripped = raw_value.strip()
        if raw_stripped.startswith("{") and raw_stripped.endswith("}"):
            try:
                parsed = json.loads(raw_stripped)
                values = parsed.get("values", []) if isinstance(parsed, dict) else []
                parts = [str(p).strip() for p in values if str(p).strip()]
            except (json.JSONDecodeError, AttributeError, TypeError):
                parts = [p.strip() for p in raw_stripped.replace("\n", ",").split(",") if p.strip()]
        elif raw_stripped.startswith("[") and raw_stripped.endswith("]"):
            try:
                parsed = json.loads(raw_stripped)
                parts = [str(p).strip() for p in parsed if p] if isinstance(parsed, list) else []
            except json.JSONDecodeError:
                parts = [p.strip() for p in raw_stripped.replace("\n", ",").split(",") if p.strip()]
        else:
            parts = [p.strip() for p in raw_stripped.replace("\n", ",").split(",") if p.strip()]
        suggested_count = 0
        for part in parts:
            part_lower = part.lower()
            if part_lower in seen_lower:
                continue
            if part_lower in options_lower:
                seen_lower.add(part_lower)
                result.append(options_lower[part_lower])
            elif (
                allow_suggest_new
                and part.strip()
                and suggested_count < 2
                and self._is_valid_suggested_tag(part)
            ):
                seen_lower.add(part_lower)
                result.append(part.strip().title())
                suggested_count += 1
            else:
                logger.bind(
                    rejected_value=part,
                    options=options,
                ).debug("claude_multi_select_rejected_non_allowed")

        return result

    def _parse_option_with_suggest_response(self, raw_value: str) -> dict:
        """Parse option response that may be JSON object or plain text."""
        stripped = raw_value.strip()
        default = {"value": stripped, "confidence": None, "source": ""}
        if not stripped:
            return default
        if not (stripped.startswith("{") and stripped.endswith("}")):
            return default
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return default
        if not isinstance(parsed, dict):
            return default
        value = str(parsed.get("value", "")).strip()
        confidence_raw = parsed.get("confidence")
        confidence = None
        if isinstance(confidence_raw, (int, float)):
            confidence = float(confidence_raw)
        source = str(parsed.get("source", "")).strip()
        return {"value": value, "confidence": confidence, "source": source}

    def _is_valid_suggested_tag(self, value: str) -> bool:
        """Heuristic guardrail for new tags from model suggestions."""
        text = value.strip()
        if not text:
            return False
        if len(text) > 32:
            return False
        if re.search(r"[.!?;:()\[\]{}\"`]", text):
            return False
        words = [w for w in text.split() if w]
        if len(words) == 0 or len(words) > 3:
            return False
        lower = text.lower()
        banned_prefixes = (
            "i ",
            "i'm ",
            "and ",
            "none ",
            "looking ",
            "no ",
        )
        if lower.startswith(banned_prefixes):
            return False
        if not re.fullmatch(r"[A-Za-z0-9&' -]+", text):
            return False
        return any(c.isalpha() for c in text)

    def choose_emoji_for_place(self, candidate_context: dict) -> str | None:
        """
        Choose a single emoji that best represents the place from context.
        Open emoji mode: Claude may return any emoji. Returns None on failure
        or when output is not a valid short emoji-like string.
        """
        if not candidate_context:
            return None
        context_str = json.dumps(candidate_context, default=str)[:6000]
        prompt = f"""Given this place information:
{context_str}

Select a single emoji that best represents this place (e.g. landmark, restaurant, park, museum).
Return only the emoji character, nothing else. No explanation, no quotes."""
        try:
            response = self._client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=32,
                system="You select one emoji to represent a place. Return only the emoji.",
                messages=[{"role": "user", "content": prompt}],
            )
            raw = self._extract_text(response).strip()
            if not raw or len(raw) > 20:
                return None
            return raw
        except Exception:
            return None

    def choose_icon_search_term_for_place(self, candidate_context: dict) -> str | None:
        """
        Generate a short search term for Freepik icon search from place context.
        Returns a concise noun phrase (e.g. "bridge", "restaurant", "museum").
        Returns None on failure or when output is empty/too long.
        """
        if not candidate_context:
            return None
        context_str = json.dumps(candidate_context, default=str)[:6000]
        prompt = f"""Given this place information:
{context_str}

Generate a single short search term (1-3 words) to find an icon that represents this place on Freepik.
Examples: bridge, restaurant, museum, park, landmark, coffee shop, library.
Return only the search term, nothing else. No quotes, no punctuation, no explanation."""
        try:
            response = self._client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=32,
                system="You generate short icon search terms for places. Return only the term.",
                messages=[{"role": "user", "content": prompt}],
            )
            raw = self._extract_text(response).strip()
            if not raw or len(raw) > 50:
                return None
            # Strip common punctuation and normalize
            cleaned = "".join(c for c in raw if c.isalnum() or c.isspace()).strip()
            return cleaned if cleaned else None
        except Exception:
            return None

    def _extract_text(self, response) -> str:
        usage = getattr(response, "usage", None)
        if usage is not None:
            self._last_usage = {
                "input_tokens": getattr(usage, "input_tokens", 0) or 0,
                "output_tokens": getattr(usage, "output_tokens", 0) or 0,
            }
        else:
            self._last_usage = None
        if not response.content:
            return ""
        text_parts = []
        for block in response.content:
            if hasattr(block, "text"):
                text_parts.append(block.text)
            elif isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(block.get("text", ""))
        return "".join(text_parts)

    def _truncate_text(self, value: str, max_chars: int = 2000) -> str:
        """Return text trimmed for structured logs."""
        if len(value) <= max_chars:
            return value
        return value[:max_chars] + "...(truncated)"

    def write_poem(self, seed: str) -> str:
        """
        Generate a poem inspired by the given seed using Claude.
        Returns the poem text from the response.
        """
        response = self._client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system="You are a creative poet. Write a short, evocative poem inspired by the given seed or theme.",
            messages=[{"role": "user", "content": f"Write a poem inspired by: {seed}"}],
        )
        return self._extract_text(response)

    def polish_place_description(self, fact_pack: dict) -> str | None:
        """
        Rewrite structured place facts into a single polished, natural paragraph.
        Uses only the provided facts; does not invent information.
        Returns None on failure.
        """
        if not fact_pack or not any(
            str(v).strip() for k, v in fact_pack.items() if k != "rating" and v is not None
        ):
            return None
        snapshot_str = json.dumps(fact_pack, default=str)[:6000]
        prompt = f"""Given these facts about a place:
{snapshot_str}

Rewrite them into a single, natural paragraph (3–6 sentences) suitable for a travel/places database.
Rules:
- Use ONLY the facts provided. Do not invent names, dates, locations, or details.
- Write in a clear, engaging tone. Vary sentence structure.
- If editorial or generative summary text is provided, weave it in naturally.
- Include location/address, type/category, and notable details when available.
- Return only the paragraph text, no headings or bullet points."""
        response = self._client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=512,
            system="You rewrite structured place data into a single factual paragraph. Never invent facts.",
            messages=[{"role": "user", "content": prompt}],
        )
        result = self._extract_text(response).strip()
        return result if result else None

    def prompt_completion(
        self,
        prompt: str,
        value: str | dict | None,
        *,
        max_tokens: int = 1024,
    ) -> str:
        """
        Run a configurable prompt with an input value. Returns the model's text response.
        The prompt may include {{value}} or {{input}} placeholders; otherwise value is appended.
        If value is a dict, it is JSON-serialized for the prompt.
        """
        if value is None:
            value_str = ""
        elif isinstance(value, dict):
            value_str = json.dumps(value, default=str)[:8000]
        else:
            value_str = str(value)

        if "{{value}}" in prompt or "{{input}}" in prompt:
            user_content = (
                prompt.replace("{{value}}", value_str)
                .replace("{{input}}", value_str)
            )
        else:
            user_content = f"{prompt}\n\n{value_str}" if value_str else prompt

        response = self._client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=max_tokens,
            system="You follow instructions precisely. Return only the requested output.",
            messages=[{"role": "user", "content": user_content}],
        )
        result = self._extract_text(response).strip()
        return result

    def get_last_usage(self) -> dict | None:
        """Return last API usage from most recent call: {input_tokens, output_tokens}."""
        return self._last_usage
