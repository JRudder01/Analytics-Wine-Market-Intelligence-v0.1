# Update instructions — v0.3.26

Replace these files in the repository root:

- `app.py`
- `catalog_scraper.py`

Recommended test update:

- `tests/test_catalog_enrichment.py`

No changes are required to:

- `requirements.txt`
- Streamlit secrets
- GitHub token/permissions
- `data/wine_comps.csv`

After Streamlit redeploys, confirm the Data Hub shows:

`Catalog parser build: v0.3.26`

Then click **Clear catalog scan** once and rerun the Eberle 5-product test. The review table should contain only those five selected product pages.
