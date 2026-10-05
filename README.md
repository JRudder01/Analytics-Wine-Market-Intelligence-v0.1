# Rudder Wine Market Intelligence v0.3.17 — Catalog Quality Patch

This patch refines the experimental winery catalog/product-page intake after the Ashes & Diamonds review.

## Changes

- Narrative blend extraction now recognizes prose such as `blend of Sémillon and Sauvignon Blanc`.
- Multiple-vineyard language (`select vineyards`, `multiple vineyards`, sourcing from vineyards, etc.) overrides generic single-vineyard wording so the row is not falsely marked Single Vineyard.
- If more than one distinct narrower AVA/district is present, the broad region is retained and `subregion` is left blank rather than arbitrarily choosing one.
- Product names are canonicalized so an embedded vintage is removed from the wine name when the vintage already has its own field (for example `Blanc Nº9 — 2023` becomes `Blanc Nº9` + vintage `2023`).
- Existing low-request scan safeguards, pricing extraction, caching, robots handling, and human review remain unchanged.

## Validation

The included tests cover:

- Ashes & Diamonds-style Cabernet from select vineyards (Single Vineyard = False)
- true explicit single-vineyard wine remains True
- Blanc narrative blend extraction and multi-subregion handling
- plural vineyard wording overrides generic site-wide single-vineyard language
