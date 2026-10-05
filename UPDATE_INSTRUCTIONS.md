# v0.3.14 Neutral User-Agent patch

Replace these two root-level files in GitHub:

- `app.py`
- `catalog_scraper.py`

The catalog scanner now sends the neutral User-Agent:

`WineCatalogResearch/0.1 (user-initiated single-page request)`

It does not include Rudder Analytics, but it also does not impersonate Chrome or another human browser. All existing single-page, robots.txt, no-retry, and access-control safeguards remain unchanged.
