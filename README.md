# Wine Market Intelligence v0.4.1 — Bottle/Style Safeguards

This is a focused follow-up to the v0.4.0 AI-assisted catalog collector.

## What changes

### 1. Bottle size is now a first-class extracted fact

The AI schema and universal catalog normalizer now carry `bottle_size_ml` when the page explicitly states a size such as 375 mL, 750 mL, or 1.5 L.

The collector does **not** assume 750 mL merely because a size is absent.

A reviewed non-750 mL row remains visible/exportable, but the normal comp-batch staging step holds it out instead of silently comparing its bottle price against ordinary 750 mL wines.

### 2. Special wine style is preserved

A new `wine_style` field can carry explicit styles such as:

- Late Harvest
- Dessert
- Fortified
- Sparkling
- Table (only when explicitly supported)

Late Harvest/Dessert and Fortified rows also receive the corresponding broad general category when appropriate so they do not behave like ordinary dry table wines.

### 3. Estate consistency is hardened

When product-local evidence explicitly supports an Estate designation and the AI correctly assigns `product_tier = Estate`, the final record can no longer remain contradictory with `estate = False`.

Weak site-wide winery branding still does not qualify as Estate evidence.

### 4. Modern-site-first authority remains unchanged

The source hierarchy is still:

1. documented provider feed/API
2. structured product data / JSON-LD
3. focused product-component extraction
4. AI-assisted interpretation for noisy/incomplete selected product pages
5. conservative deterministic fallback / human review

The AI receives only bounded evidence from the HTML already fetched by the scanner; it does not make another request to the winery site.

## Validation

The regression suite includes the previous A&D, VinoShipper, Eberle, modern JSON-LD, and J. Rickards cases plus new tests for bottle size, Late Harvest style, Estate consistency, and non-standard-size handling.
