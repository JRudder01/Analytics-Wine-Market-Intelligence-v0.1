# Wine Market Intelligence v0.3.16 update

Replace these two root-level files in the GitHub repository:

- `app.py`
- `catalog_scraper.py`

No requirements, Streamlit secrets, or database replacement is required.

## What changed

- Selected product pages now extract richer factual metadata when visible in static HTML/JSON-LD:
  - varietal/blend
  - market category and broad color/style
  - AVA / sub-AVA
  - ABV
  - cases produced
  - Estate indicator
  - single-vineyard indicator
  - product tier
  - availability status
  - regular/sale/member pricing
- Catalog results now use an editable review table rather than only a basic price export.
- Reviewed rows can be selected and added directly to the normal **pending comp batch**.
- The existing GitHub batch-commit button remains the only permanent-save step.
- Exact duplicate rows are skipped during staging.
- A small internal **Source status** control was added: Testing / permission pending, Approved for low-frequency scan, or Do not scan.
- `Do not scan` disables network scan buttons for that source in the current session.
- The page fetcher now has a 24-hour in-process HTML cache. Repeated requests for the exact same URL can use the cached page without another page request.
- When a stale cached page has an ETag or Last-Modified value, the next request is conditional so an unchanged page can return HTTP 304 rather than retransmitting the page.
- Existing robots.txt, low request volume, HTTP 401/403/429, page-size, redirect, and private-network safeguards remain in place.

## Important limitation

Metadata extraction is deliberately conservative. If a fact is not confidently present in the static HTML/JSON-LD, leave it blank and correct it during review rather than inferring aggressively.
