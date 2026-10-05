# Wine Market Intelligence v0.3.22 — VinoShipper quality cleanup

This patch is a final quality pass on the provider-feed route before moving testing to another commerce platform.

## What changed

- More robust VinoShipper ABV extraction, including nested metadata / label-value structures.
- Generic normalization for provider geography display strings without inventing a narrower AVA.
- `GSM` expands to Grenache / Syrah / Mourvèdre for classification.
- Provider values that are obvious product-name typos are no longer treated as grape varieties.
- Explicit feed composition is preferred when present.
- Adds an auditable, source-specific last-resort correction layer for verified 915 Lincoln records where the provider feed omits or mislabels stable facts.
- 915 Lincoln corrections cover Distinctive, Trois, Le Rhone, Better Together and stable vintage-specific ABVs observed in the public VinoShipper catalog.
- Existing low-request / no-browser-automation safeguards are unchanged.

## Files to replace

- `app.py`
- `catalog_scraper.py`

Optional but recommended:

- `tests/test_catalog_enrichment.py`

No database, secrets, token, or requirements changes are needed.

## Validation

- Python compilation passed.
- Catalog/enrichment regression suite: 18/18 tests passed.
