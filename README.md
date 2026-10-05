# Wine Market Intelligence v0.3.25 — Universal Catalog Normalization

This patch consolidates catalog normalization so every extraction route uses the same final canonical pass before review/staging.

## Main changes
- All catalog sources now flow through one final normalizer: VinoShipper, JSON-LD, static/repeating HTML, and explicitly selected product pages.
- Parser-build changes invalidate stale derived catalog session state so old rows cannot survive a deployment and appear current.
- Geography matching tolerates collapsed page-template text such as `NapaValley` and `OakKnoll District`.
- Multiple narrower AVAs/districts retain only the broad region and reduce confidence rather than selecting one arbitrarily.
- Added Santa Cruz Mountains and Diamond Mountain geography handling.
- Known nested AVAs/districts are normalized into region/subregion consistently.
- Proprietary/vineyard wine names can recover a single unambiguous varietal from opening product-page prose.
- Catalog parser build label updated to v0.3.25.

## Regression coverage
25 catalog/enrichment tests pass, including the prior VinoShipper suite plus A&D regressions for Blanc №9, Mountain Cuvée №6, and Vineyard II №2.
