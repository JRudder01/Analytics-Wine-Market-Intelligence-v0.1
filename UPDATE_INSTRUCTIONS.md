# Rudder Wine Market Intelligence v0.3.8 — Estate reliability patch

Replace only the root-level `vision_intake.py` file in GitHub.

This patch:
- adds an explicit whole-wine Estate decision to the structured vision extraction;
- treats wording such as “crafted from sustainably grown Estate Chardonnay” as Estate = TRUE;
- keeps component-only estate wording from triggering Estate status;
- falls back to the visible source/brand name when the model leaves the winery field blank;
- keeps canonical direct-winery source names (for example, Eberle Winery -> Eberle).

No changes are required to `app.py`, `github_storage.py`, the database, requirements, or Streamlit secrets.
