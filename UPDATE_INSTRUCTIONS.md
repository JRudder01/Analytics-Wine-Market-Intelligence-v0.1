# Update instructions — v0.3.24

Replace these files in the repository root:
- `app.py`
- `catalog_scraper.py`

Recommended test update:
- `tests/test_catalog_enrichment.py`

No changes are required to:
- `requirements.txt`
- Streamlit secrets
- GitHub token permissions
- `data/wine_comps.csv`

After Streamlit redeploys, confirm the catalog scanner visibly says:
`Catalog parser build: v0.3.24`

Then either click **Clear catalog scan** once or simply rescan 915 Lincoln. v0.3.24 also upgrades stale VinoShipper session rows automatically, so the old serialized rows should no longer survive into the review/export table unchanged.
