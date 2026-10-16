# Wine Market Intelligence v0.4.4 — UI Streamlining

This is a UI-only refinement of v0.4.3. Catalog extraction/parser behavior remains on parser build v0.4.2.

## Small patch install
Replace the root-level `app.py` with the v0.4.4 `app.py` from the patch ZIP, commit to GitHub, and allow Streamlit Cloud to redeploy.

No dependency, secret, database, or parser-file changes are required.

## What changed
- Catalog scan safeguards and less-common settings are consolidated under one optional expander.
- Detailed request behavior is nested under a secondary technical-details expander.
- The default catalog status line no longer exposes the AI model name.
- `Clear catalog scan` only appears after scan state exists.
- Screenshot Intake now follows a simple 3-step flow: Add screenshots → Identify source → Extract & review.
- Screenshot Source type, source-name override, and Vision model moved under optional settings.
- Clipboard screenshot previews are collapsed by default.
- Existing request safeguards, AI behavior, extraction logic, and persistence behavior are unchanged.

## Validation
- `app.py` compiles successfully.
- 55 focused AI/catalog-enrichment tests pass.
- Two older catalog-scraper tests in the handed-off repository still assert the pre-canonicalization convention that keeps the vintage inside `wine`; those are historical expectations and were not changed by this UI-only patch.
