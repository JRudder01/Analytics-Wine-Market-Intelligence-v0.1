# Wine Market Intelligence v0.4.5 — Database Workflow UI Cleanup

This is a UI/workflow refinement of v0.4.4. Catalog extraction/parser behavior remains on parser build v0.4.2.

## Small patch install
Replace the root-level `app.py` with the v0.4.5 `app.py` from the patch ZIP, commit to GitHub, and allow Streamlit Cloud to redeploy.

No dependency, secret, database, catalog-parser, or AI-extraction changes are required.

## What changed
- Screenshot upload and clipboard paste are presented as two parallel intake methods.
- Source URL now includes a short provenance explanation.
- Removed the always-visible staging warning between Screenshot Intake and the database section.
- Comparable-database source coverage is collapsed by default.
- Workbook import and one-off manual comp entry are grouped under **Add observations** and collapsed until needed.
- Manual entry now says **Add comparable to pending batch** so the temporary-vs-permanent state is clearer.
- Pending observations get a dedicated **Pending changes** section.
- Pending batches can be previewed before saving, with a concise 50-row review view for large batches.
- The GitHub save control appears only when there are pending observations and uses clearer **Save ... to GitHub** wording.
- Database status is summarized in one compact line instead of multiple persistent metric cards/warnings.
- Existing persistence semantics are unchanged: staged rows remain temporary until the GitHub commit succeeds.

## Validation
- `app.py` compiles successfully.
- Full included test suite passes: **109/109** with importlib test isolation.
- Two stale historical catalog-scraper expectations in the handed-off full build were updated to the already-current canonical convention (vintage stored in `vintage`, not duplicated inside `wine`). No parser behavior was changed.
