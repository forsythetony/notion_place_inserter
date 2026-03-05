"""Claude API service wrapper for poem generation."""

import anthropic


class ClaudeService:
    """Wraps the Anthropic API client for poem generation."""

    def __init__(self, api_key: str):
        self._client = anthropic.Anthropic(api_key=api_key)

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
        if not response.content:
            return ""
        text_parts = []
        for block in response.content:
            if hasattr(block, "text"):
                text_parts.append(block.text)
            elif isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(block.get("text", ""))
        return "".join(text_parts)
