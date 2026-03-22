-- Align Google Places rate cards with Google Maps Platform core services pricing list (Places API New).
-- USD per request = (price per 1000 events) / 1000 for first paid tier after free caps.
-- Text Search Pro $32/1000; Place Details Pro $17/1000; see notes for Enterprise / field-mask caveats.

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
    'google_places',
    'external_api_call',
    'search_places',
    NULL,
    NULL,
    NULL,
    0.032,
    'Places API (New) Text Search Pro — $32/1000 (USD list, first paid tier; 5k/mo free cap). Field masks can trigger Enterprise SKUs ($35–40/1000). Source: Google Maps Platform core services pricing list.'
  ),
  (
    'google_places',
    'external_api_call',
    'get_place_details',
    NULL,
    NULL,
    NULL,
    0.017,
    'Places API (New) Place Details Pro — $17/1000 (first paid tier; 5k/mo free cap). Enterprise SKUs higher. Same pricing list.'
  ),
  (
    'google_places',
    'external_api_call',
    '*',
    NULL,
    NULL,
    NULL,
    0.025,
    'Fallback when operation unknown; ~midpoint of Text Search Pro + Place Details Pro list rates; prefer search_places / get_place_details rows.'
  )
ON CONFLICT (provider, usage_type, rate_key) DO UPDATE SET
  usd_per_million_input_tokens = EXCLUDED.usd_per_million_input_tokens,
  usd_per_million_output_tokens = EXCLUDED.usd_per_million_output_tokens,
  usd_per_million_total_tokens = EXCLUDED.usd_per_million_total_tokens,
  usd_per_call = EXCLUDED.usd_per_call,
  notes = EXCLUDED.notes;
