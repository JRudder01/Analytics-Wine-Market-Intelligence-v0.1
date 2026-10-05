# v0.3.19 update instructions

Replace these root-level files in GitHub:

- `app.py`
- `catalog_scraper.py`

Optional but recommended so the repo tests match the deployed build:

- `tests/test_catalog_enrichment.py`

No changes are required to `requirements.txt`, Streamlit secrets, the GitHub token, or `data/wine_comps.csv`.

## What changed

The catalog scanner now has a generic **repeating static product-block** parser between JSON-LD parsing and product-link follow-up discovery. This is intended for storefronts/marketplaces that publish complete wine rows/cards in the catalog HTML but do not expose them through the anchor/card pattern the earlier parser expected.

The parser looks for repeated wine-like blocks containing a product title/vintage plus price, and enriches them from whatever facts are already visible in that same block (ABV, varietal/blend, region/subregion, etc.). It does not make additional requests to do this.

This is deliberately platform-agnostic rather than a hard-coded 915 Lincoln or VinoShipper parser.
