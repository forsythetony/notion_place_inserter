-- Refresh Freepik rate card notes from Freepik Developer console (rate limits / EUR caps).
-- App usage: GET /v1/icons → usage_records metric search_icons. USD/call remains a placeholder.

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
    'freepik',
    'external_api_call',
    'search_icons',
    NULL,
    NULL,
    NULL,
    0.001,
    'GET /v1/icons. Console (Icons): 25/day free vs 2500/day pay-per-use; 5 EUR vs 500 EUR/mo caps. USD/call placeholder — set from billing.'
  ),
  (
    'freepik',
    'external_api_call',
    '*',
    NULL,
    NULL,
    NULL,
    0.001,
    'Default Freepik external call; same placeholder as search_icons until billing-derived USD/call is set.'
  )
ON CONFLICT (provider, usage_type, rate_key) DO UPDATE SET
  usd_per_million_input_tokens = EXCLUDED.usd_per_million_input_tokens,
  usd_per_million_output_tokens = EXCLUDED.usd_per_million_output_tokens,
  usd_per_million_total_tokens = EXCLUDED.usd_per_million_total_tokens,
  usd_per_call = EXCLUDED.usd_per_call,
  notes = EXCLUDED.notes;
