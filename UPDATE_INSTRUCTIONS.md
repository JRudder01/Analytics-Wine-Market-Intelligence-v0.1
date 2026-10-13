# v0.3.27 update instructions

Replace these files in the repository root:

- `app.py`
- `catalog_scraper.py`

Recommended for the repo test suite:

- `tests/test_catalog_enrichment.py`

No changes are required to requirements, Streamlit secrets, GitHub permissions, or `data/wine_comps.csv`.

After Streamlit redeploys, confirm both the app version and `Catalog parser build` show `v0.3.27`. Clear the prior Eberle scan and rerun the same five selected product pages.
