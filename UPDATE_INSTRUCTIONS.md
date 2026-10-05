# v0.3.21 update instructions

1. Replace root `app.py`.
2. Replace root `catalog_scraper.py`.
3. Optionally replace `tests/test_catalog_enrichment.py`.
4. Commit to `main` and let Streamlit redeploy.

No changes are required to:

- `requirements.txt`
- `.streamlit/secrets.toml`
- GitHub token permissions
- `data/wine_comps.csv`

## Recommended repeat test

Use the same VinoShipper source:

`https://vinoshipper.com/shop/915_lincoln`

The app should continue to auto-detect producer `4112` and use the documented Product Feed. After scanning, review especially:

- vintage population
- `Better Together` varietal/category if provider metadata exposes Zinfandel
- `Cabernet and Merlot Blend` → Bordeaux Blend
- `Le Rhone` → Rhône Blend
- `Pino Noir` → Pinot Noir
- `Petite Verdot` → Petit Verdot
- explicit multi-grape compositions overriding a misleading single-varietal provider category

Rows still lacking a defensible vintage/category should be marked `Moderate` rather than `High` confidence.
