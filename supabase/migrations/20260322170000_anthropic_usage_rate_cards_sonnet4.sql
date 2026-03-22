-- Align Anthropic LLM rate cards with Claude API (1P) list pricing for the default app model.
-- Claude Sonnet 4 (API id claude-sonnet-4-20250514): $3/MTok base input, $15/MTok output.
-- Source: https://www.claude.com/pricing

INSERT INTO usage_rate_cards (
  provider,
  usage_type,
  rate_key,
  usd_per_million_input_tokens,
  usd_per_million_output_tokens,
  usd_per_million_total_tokens,
  usd_per_call,
  notes
)
VALUES
  (
    'anthropic',
    'llm_tokens',
    '*',
    3.0,
    15.0,
    9.0,
    NULL,
    'Fallback when model unknown; blended $/MTok for 50/50 prompt/completion. Matches Claude Sonnet 4 tier; see model-specific row.'
  ),
  (
    'anthropic',
    'llm_tokens',
    'claude-sonnet-4-20250514',
    3.0,
    15.0,
    NULL,
    NULL,
    'Claude Sonnet 4 (dated API id). Claude API 1P list: $3/MTok base input, $15/MTok output — https://www.claude.com/pricing'
  )
ON CONFLICT (provider, usage_type, rate_key) DO UPDATE SET
  usd_per_million_input_tokens = EXCLUDED.usd_per_million_input_tokens,
  usd_per_million_output_tokens = EXCLUDED.usd_per_million_output_tokens,
  usd_per_million_total_tokens = EXCLUDED.usd_per_million_total_tokens,
  notes = EXCLUDED.notes;
