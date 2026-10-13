# Update to v0.4.2

Upload/replace these repository root files:

- `app.py`
- `catalog_scraper.py`
- `ai_catalog_extractor.py` (unchanged logic from v0.4.1, included for a complete patch set)
- `packages.txt` **new**

Dependency step:

- Open your existing `requirements.txt` and append this one line if it is not already present:

  `playwright>=1.55,<2`

The included `requirements_additions.txt` contains that exact line for copy/paste. Do **not** replace your existing requirements.txt with requirements_additions.txt.

Recommended test files:

- `tests/test_catalog_enrichment.py`
- `tests/test_ai_catalog_extractor.py`

Then let Streamlit rebuild/reboot. Confirm both the app header and **Catalog parser build** show `v0.4.2`.

For Sanger Wines, run the normal static scan first. If it again returns no products/links, click **Render this page once (JavaScript fallback)**. The browser fallback should not run before that explicit click.
