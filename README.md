# Wine Market Intelligence v0.3.21 — VinoShipper mapping quality patch

This focused patch keeps the v0.3.20 documented VinoShipper Product Feed adapter and improves how provider records are converted into Wine Market Intelligence comp rows.

## What changed

- Recovers vintage from nested VinoShipper product metadata, not just top-level fields or the visible product title.
- Searches nested provider metadata for varietal, appellation, ABV, case production, and description fields when the feed shape varies.
- Normalizes common varietal/label aliases such as `Pino Noir` → `Pinot Noir` and `Petite Verdot` → `Petit Verdot`.
- Recognizes explicit blend names such as `Cabernet and Merlot Blend` as multi-grape blends rather than blindly accepting one provider category.
- Recognizes Rhône-style naming such as `Le Rhone` as `Rhône Blend` when more specific composition is unavailable.
- Prefers explicit multi-grape composition in product descriptions/metadata over a single-varietal provider classification.
- Expands deterministic categories to include `Petit Verdot`, `Tannat`, `Malbec`, `Grenache Blanc`, and Albariño aliases.
- Caps a VinoShipper row at `Moderate` confidence when vintage is missing or the row still cannot be classified beyond `Other`.
- Preserves the existing low-request provider-feed workflow and all prior catalog safeguards.

## Files to replace

- `app.py`
- `catalog_scraper.py`

Optional test update:

- `tests/test_catalog_enrichment.py`

## Validation

- Python compilation passed for `app.py` and `catalog_scraper.py`.
- Catalog/enrichment regression suite: **14/14 passed**.
