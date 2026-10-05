# Wine Market Intelligence v0.3.19 — repeating catalog blocks

This patch extends the experimental catalog scan with a generic parser for static repeating wine product blocks.

Extraction order is now:

1. JSON-LD Product data
2. Repeating static HTML product blocks
3. Existing linked HTML-card parser
4. Optional user-selected product-page follow-up when the catalog itself is insufficient

This lets compatible storefront/catalog pages yield multiple visible wine/price records from the **single catalog request** already made, without opening individual product pages.
