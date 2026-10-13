# Wine Market Intelligence v0.4.0 — AI-Assisted Catalog Collector

This build changes the catalog collector from a progressively larger HTML-rule parser into a **modern-site-first deterministic collector with a conservative AI interpretation fallback**.

## What changes

The source hierarchy is now:

1. documented provider feed/API when available
2. structured product data / JSON-LD
3. focused product-component extraction
4. AI-assisted interpretation for legacy, noisy, incomplete, or otherwise ambiguous selected product pages
5. deterministic fallback / human review

AI is deliberately **not** the authority when the site already supplies reliable structured facts.

## AI request behavior

- AI runs only on product pages the administrator explicitly selects.
- In the default **AI fallback** mode, complete High-confidence JSON-LD records skip AI.
- AI receives bounded text/structured evidence from HTML the scanner has already downloaded. It does not make another request to the winery site.
- Every AI result uses a strict structured schema.
- Non-null facts are expected to include field-level supporting evidence.
- Deterministic sanity checks reject implausible vintages, ABV, prices, cases, and unsupported fields.
- Unknown facts are supposed to remain blank rather than be guessed.
- Human review remains required before staging and GitHub commit.

## Pricing safeguards

The AI instructions explicitly distinguish:

- ordinary public bottle price
- genuine sale/promotion price
- explicit numeric club/member price
- quantity/case discounts such as 12+ bottle pricing

Quantity discounts are not stored as sale or club prices.

## Modern sites stay preferred

Provider feeds and strong structured data retain higher authority than AI. If a modern JSON-LD product has a dependable name/price, AI cannot silently replace those facts during enrichment.

## Current limitation

This build interprets **HTML already available to the low-request collector**. It does not execute JavaScript or operate a browser. A site that exposes no useful product evidence until client-side JavaScript runs can still require the existing screenshot workflow or a future explicitly controlled browser-agent layer.
