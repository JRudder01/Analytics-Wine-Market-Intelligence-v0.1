# v0.4.1 update instructions

Starting from v0.4.0:

1. Replace root `app.py`.
2. Replace root `catalog_scraper.py`.
3. Replace root `ai_catalog_extractor.py`.
4. Recommended: replace `tests/test_catalog_enrichment.py` and `tests/test_ai_catalog_extractor.py`.

No database migration, new API key, or new Python dependency is required.

After deployment, verify both the app header and `Catalog parser build` show `v0.4.1`.

## Recommended regression test

Re-run the same five J. Rickards wines with **AI fallback (recommended)**.

Expected changes from v0.4.0:

- Five Sisters should have consistent Estate status/tier when the product-local Estate wording is present.
- Twilight Late Harvest Viognier should show `Bottle mL = 375` and `Wine style = Late Harvest`.
- Twilight should remain reviewable/exportable but should be held out of the normal comp batch because its 375 mL price is not directly comparable to standard 750 mL pricing.
- The prior v0.4.0 fixes for quantity discounts, club-price ambiguity, Rosé navigation contamination, and complex blend extraction should remain intact.
