# Wine Market Intelligence v0.3.15 update

Replace these two root-level files in the GitHub repository:

- `app.py`
- `catalog_scraper.py`

No requirements, secrets, or database changes are required.

## What changed

- Catalog pages are still fetched only after the administrator pastes a URL and clicks **Scan this catalog page**.
- The already-downloaded catalog HTML is now inspected for likely same-site wine product links without opening them.
- Discovered product pages are shown in a review table with checkboxes.
- Only pages explicitly selected by the administrator are fetched when **Scan selected product pages** is clicked.
- Maximum 12 selected product pages per batch.
- Selected product pages are fetched sequentially with a short delay between requests.
- Existing robots.txt, HTTP 401/403/429, page-size, redirect, and private-network safeguards remain in place.
- Product-page parsing adds a conservative fallback for pages where the catalog exposes names but not prices.
- User-facing copy now treats **Rudder Analytics** as the company brand and **Wine Market Intelligence** as the tool; phrases such as “Rudder stops…” were removed.
- The company name remains in the browser/page title (`Rudder Analytics | Wine Market Intelligence`).
