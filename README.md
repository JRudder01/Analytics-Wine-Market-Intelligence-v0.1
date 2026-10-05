# Wine Market Intelligence v0.3.20 — VinoShipper Product Feed adapter

This focused patch adds a provider-aware catalog route for VinoShipper while preserving the existing generic catalog/product-page scanner.

## What changed

- Detects VinoShipper shop/catalog URLs.
- Prefers VinoShipper's documented public Product Feed endpoint when a producer ID is available.
- Attempts to recover the producer ID from the public shop shell / pasted URL.
- If auto-detection fails, exposes one optional numeric **VinoShipper producer ID** field rather than escalating to browser automation.
- Converts provider-feed product JSON into the same editable review table used by other catalog scans.
- Keeps generic JSON-LD, repeating-block, and selected-product-page fallbacks for non-VinoShipper sites.
- No VinoShipper API key or new Streamlit secret is required for the documented product-feed route.

## Files to replace

- `app.py`
- `catalog_scraper.py`

Optional test update:

- `tests/test_catalog_enrichment.py`
