# v0.3.28 update instructions

Replace these files in the repository root:

1. `app.py`
2. `catalog_scraper.py`

Recommended for the repository test suite:

3. `tests/test_catalog_enrichment.py`

Then let Streamlit redeploy (reboot once if needed) and confirm both UI indicators show `v0.3.28`.

For the J. Rickards regression test, clear the prior scan, rescan the All Wines catalog, and re-open the same five selected product pages. Expected behavior includes:

- Five Sisters Cabernet Sauvignon → Cabernet Sauvignon / Red; Estate=True; $49 regular; no sale/club price inferred from quantity/club boilerplate.
- G-S-M Red Blend → Rhône Blend / Red; quantity price is not a sale.
- Left Bank Cuvée → Bordeaux Blend / Red; quantity price is not a sale.
- Reserve Old Vine Zinfandel → Zinfandel / Red / Reserve.
- Twilight Late Harvest Viognier → Viognier / White.

Legacy/unstructured rows may show Moderate confidence by design.
