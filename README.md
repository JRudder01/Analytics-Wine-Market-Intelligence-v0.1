# Wine Market Intelligence v0.4.2 — Explicit Rendered-Page Fallback

This build adds a deliberately isolated JavaScript-rendering fallback for modern storefronts whose static HTML/JSON-LD contains no dependable wine products.

## What changed

- Normal/provider/static scanning remains the default and unchanged in priority.
- When a static catalog scan finds **no product records and no product links**, the UI can show **Render this page once (JavaScript fallback)**.
- Rendering is **manual only**. It never activates silently.
- The browser opens only the exact URL supplied by the administrator. It does not click links, log in, solve CAPTCHAs, bypass 401/403/429 responses, or spoof browser fingerprints.
- Heavy visual resources (images, media, fonts, stylesheets) are blocked. JavaScript/XHR/fetch are allowed so client-side product grids can populate the DOM.
- A small scroll is used to trigger lazy-loaded product grids; no product link is opened automatically.
- Rendered HTML then flows through the same deterministic + AI + canonical normalization pipeline already used by v0.4.1.
- Optional selected-product rendering is also available, but only through an explicit checkbox and only after the normal static product-page extraction returns no dependable record.
- Rendered pages are cached in-process for 24 hours.

## Deployment dependency

This feature requires:

1. Append `playwright>=1.55,<2` to the repository's existing `requirements.txt`.
2. Add the included `packages.txt` at the repository root containing `chromium`.

No new API key is required. AI continues to use the existing `OPENAI_API_KEY`.

## Traffic implications

The normal path is still low-request. The rendered fallback is heavier and may create the exact page request plus supporting JavaScript/data requests. It is therefore intentionally manual and reserved for pages where the static path fails.
