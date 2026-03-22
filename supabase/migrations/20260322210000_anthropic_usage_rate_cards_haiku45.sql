-- Claude Haiku 4.5 (API id claude-haiku-4-5-20251001): $1/MTok base input, $5/MTok output.
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
    'claude-haiku-4-5-20251001',
    1.0,
    5.0,
    NULL,
    NULL,
    'Claude Haiku 4.5 (dated API id). Used for step_template_ai_prompt / prompt_completion. Claude API 1P list: $1/MTok base input, $5/MTok output — https://www.claude.com/pricing'
  )
ON CONFLICT (provider, usage_type, rate_key) DO UPDATE SET
  usd_per_million_input_tokens = EXCLUDED.usd_per_million_input_tokens,
  usd_per_million_output_tokens = EXCLUDED.usd_per_million_output_tokens,
  usd_per_million_total_tokens = EXCLUDED.usd_per_million_total_tokens,
  notes = EXCLUDED.notes;
