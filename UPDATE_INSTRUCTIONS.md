# Update instructions — v0.3.25

Replace these files in the repository root:

1. `app.py`
2. `catalog_scraper.py`

Recommended test update:

3. `tests/test_catalog_enrichment.py`

No changes are required to `requirements.txt`, Streamlit secrets, GitHub permissions, or `data/wine_comps.csv`.

After Streamlit redeploys, confirm the Data Hub shows:

`Catalog parser build: v0.3.25`

The new build automatically invalidates stale derived catalog scan rows from earlier parser builds. Re-run the A&D catalog scan and select the same regression products; no manual cache/session cleanup should be necessary beyond the normal scan workflow.
