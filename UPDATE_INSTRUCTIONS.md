# v0.3.17 update instructions

Replace these root-level files in GitHub:

- `app.py`
- `catalog_scraper.py`

Also replace/update the test file if you keep repository tests current:

- `tests/test_catalog_enrichment.py`

No changes are required to:

- `requirements.txt`
- Streamlit secrets
- `data/wine_comps.csv`
- GitHub token configuration

After Streamlit redeploys, repeat the same Ashes & Diamonds three-wine scan. Expected review behavior:

- `Blanc Nº9` — vintage 2023, varietal/blend includes Sémillon + Sauvignon Blanc, Napa Valley, subregion blank when both Oak Knoll District and Yountville are present, Single Vineyard False.
- `Cabernet Sauvignon Nº2` — vintage 2023, Napa Valley / Oak Knoll District, Single Vineyard False when described as coming from select vineyards.
- `Chardonnay Nº4` — vintage 2025, Single Vineyard False when sourced from select vineyards; Member exclusive remains availability status.
