"""Shared LLM model identifiers (no service imports — safe for usage accounting and workers)."""

# Default Messages API model: Claude Sonnet 4 (dated id). Claude API (1P) list pricing:
# $3/MTok base input, $15/MTok output — https://www.claude.com/pricing
DEFAULT_CLAUDE_MESSAGES_MODEL = "claude-sonnet-4-20250514"

# AI Prompt step (`prompt_completion`): Claude Haiku 4.5 (dated API id). Claude API (1P) list pricing:
# $1/MTok base input, $5/MTok output — https://www.claude.com/pricing
CLAUDE_HAIKU_45_MODEL = "claude-haiku-4-5-20251001"
