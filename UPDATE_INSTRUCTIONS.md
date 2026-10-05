# v0.3.22 update instructions

1. Open the repository root on the `main` branch.
2. Replace `app.py`.
3. Replace `catalog_scraper.py`.
4. Optional: replace `tests/test_catalog_enrichment.py` so the repository contains the current regression tests.
5. Commit the files and allow Streamlit to redeploy.
6. Re-run the 915 Lincoln VinoShipper scan once as a regression check.
7. Export the reviewed table and verify Distinctive / Trois / Le Rhone plus ABV fields.
8. Then move testing to a winery on a different commerce platform.

No changes are required to `requirements.txt`, `.streamlit/secrets.toml`, GitHub token permissions, or `data/wine_comps.csv`.
