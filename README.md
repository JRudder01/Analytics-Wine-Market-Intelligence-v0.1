# Wine Market Intelligence v0.3.16

Catalog enrichment + review/staging update.

This version keeps the existing user-initiated, selected-product-page scan but makes the product-page stage substantially more useful. Selected pages can now provide conservative metadata such as varietal/blend, market/general category, AVA/sub-AVA, ABV, cases produced, Estate/single-vineyard signals, product tier, availability status, and retail/sale/member pricing when those facts are present in the static page HTML or JSON-LD.

Nothing from the catalog scanner is written directly to the permanent database. The administrator reviews/edits rows, selects which ones to stage, then uses the existing **Commit pending changes to GitHub database** control.

The request design remains intentionally low-impact: no site-wide crawl, no JavaScript/browser automation, no CAPTCHA/access-control bypass, no automatic retry on rate limits, and no automatic loading of images/CSS/fonts/scripts.
