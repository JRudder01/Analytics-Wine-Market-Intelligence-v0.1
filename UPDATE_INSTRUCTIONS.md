# v0.4.0 update instructions

Starting from the current v0.3.28 repository:

1. Replace root `app.py`.
2. Replace root `catalog_scraper.py`.
3. Add new root file `ai_catalog_extractor.py`.
4. Recommended: replace `tests/test_catalog_enrichment.py` and add `tests/test_ai_catalog_extractor.py`.

No database migration is required.

No new Python dependency is required beyond the existing app requirements; the build uses the same installed OpenAI SDK and `OPENAI_API_KEY` already used by Screenshot Intake.

Optional configuration:

- `OPENAI_CATALOG_MODEL` may be added to Streamlit Secrets/environment to use a catalog-specific model.
- If it is not set, the collector uses the same default model configured for the existing AI intake workflow.

After deployment, verify both the app header and `Catalog parser build` show `v0.4.0`.

## First recommended test

Re-run the same five J. Rickards product pages that exposed the legacy-page issues. Leave **Selected product-page interpretation** on `AI fallback (recommended)`.

Expected behavior:

- legacy/noisy J. Rickards pages should show an AI-assisted extraction method;
- the 12+ quantity price should not populate `sale_price`;
- generic club messaging should not create a numeric `club_price`;
- the page-wide `WHITE & ROSÉ WINES` navigation should not classify red wines as Rosé;
- an `AI extraction evidence` expander should appear under the review table;
- every result still remains editable and requires normal staging/commit approval.
