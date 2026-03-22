-- Operator-configurable USD estimates for usage_records (read-time aggregation; not billing truth).
CREATE TABLE IF NOT EXISTS usage_rate_cards (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  provider text NOT NULL,
  usage_type text NOT NULL,
  -- LLM: match metadata.model; external: match metric_name (operation). Use '*' for default.
  rate_key text NOT NULL DEFAULT '*',
  usd_per_million_input_tokens numeric,
  usd_per_million_output_tokens numeric,
  usd_per_million_total_tokens numeric,
  usd_per_call numeric,
  effective_from timestamptz NOT NULL DEFAULT now(),
  notes text,
  UNIQUE (provider, usage_type, rate_key)
);

CREATE INDEX IF NOT EXISTS idx_usage_rate_cards_provider_type
  ON usage_rate_cards (provider, usage_type);

COMMENT ON TABLE usage_rate_cards IS
  'USD rate hints for admin cost estimates; sources should be documented in ops notes, not hardcoded guesses in app code long-term.';

-- Conservative placeholders — replace via admin SQL or future UI; see product docs for vendor list pricing.
INSERT INTO usage_rate_cards (provider, usage_type, rate_key, usd_per_million_input_tokens, usd_per_million_output_tokens, usd_per_million_total_tokens, usd_per_call, notes)
VALUES
  ('anthropic', 'llm_tokens', '*', 3.0, 15.0, 9.0, NULL, 'Fallback when model unknown; blended $/MTok for 50/50 prompt/completion. Matches Claude Sonnet 4 tier; see model-specific row.'),
  ('anthropic', 'llm_tokens', 'claude-sonnet-4-20250514', 3.0, 15.0, NULL, NULL, 'Claude Sonnet 4 (dated API id). Claude API 1P list: $3/MTok base input, $15/MTok output — https://www.claude.com/pricing'),
  ('google_places', 'external_api_call', 'search_places', NULL, NULL, NULL, 0.032, 'Places API (New) Text Search Pro — $32/1000 (USD list, first paid tier; 5k/mo free cap). Field masks can trigger Enterprise SKUs ($35–40/1000). Source: Google Maps Platform core services pricing list.'),
  ('google_places', 'external_api_call', 'get_place_details', NULL, NULL, NULL, 0.017, 'Places API (New) Place Details Pro — $17/1000 (first paid tier; 5k/mo free cap). Enterprise SKUs higher. Same pricing list.'),
  ('google_places', 'external_api_call', '*', NULL, NULL, NULL, 0.025, 'Fallback when operation unknown; ~midpoint of Text Search Pro + Place Details Pro list rates; prefer search_places / get_place_details rows.'),
  ('freepik', 'external_api_call', 'search_icons', NULL, NULL, NULL, 0.001, 'GET /v1/icons. Console (Icons): 25/day free vs 2500/day pay-per-use; 5 EUR vs 500 EUR/mo caps. USD/call placeholder — set from billing.'),
  ('freepik', 'external_api_call', '*', NULL, NULL, NULL, 0.001, 'Default Freepik external call; same placeholder as search_icons until billing-derived USD/call is set.'),
  ('notion', 'external_api_call', '*', NULL, NULL, NULL, 0.0, 'Notion API often within workspace quota; adjust when metering')
ON CONFLICT (provider, usage_type, rate_key) DO NOTHING;
