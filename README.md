# Wine Market Intelligence v0.3.26 — Catalog Quality Cleanup

This patch is a generic catalog-pipeline cleanup following the Eberle cross-platform test. It does **not** add an Eberle-specific parser.

## What changed

- **Selected-product isolation:** once the user explicitly scans product pages, the review table contains only those selected/enriched products (plus any earlier selected pages in the same session), not every catalog-level candidate.
- **Comparable-product gate:** obvious navigation/merchandise rows such as gift sets, `Club Only`, and `Winery Only` are excluded from review/staging.
- **Bottle-size protection:** non-standard bottle-size variants such as 375 mL/half bottles and magnums are excluded from the standard 750 mL comparable pipeline until bottle-size normalization is implemented.
- **Technical-field boundaries:** varietal/composition extraction stops before the next metadata label, preventing strings such as `Appellation Paso Robles` from being appended to a grape composition.
- **Conservative availability:** contradictory static HTML states (for example `Sold Out` + `Back Ordered` + `Add to Cart`) now return blank rather than a false availability status.
- **Universal cleanup:** the same candidate gate and field cleanup apply to all catalog adapters through the existing canonical finalizer.
- Catalog parser build label updated to **v0.3.26**.

## Validation

- Full catalog regression suite: **30/30 passing**.
- `app.py` and `catalog_scraper.py` compile successfully.
- Existing A&D and VinoShipper normalization paths remain covered by the regression suite.
