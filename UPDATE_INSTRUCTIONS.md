# v0.3.23 update instructions

Replace these root-level GitHub files:

- `app.py`
- `catalog_scraper.py`

Optional but recommended for keeping the repository test suite current:

- `tests/test_catalog_enrichment.py`

No changes are required to:

- `requirements.txt`
- Streamlit secrets
- GitHub token permissions
- `data/wine_comps.csv`

After Streamlit redeploys, rerun 915 Lincoln once and export the review table. The status message for a VinoShipper feed now explicitly states that final provider normalization was applied before review.
