# Rudder Wine Market Intelligence v0.3.11 — Single known-wine search

This patch streamlines the Pricing Analysis "Start from a known wine" workflow into **one autocomplete field**.

## Replace these root-level files

- `app.py`
- `requirements.txt`

## What changed

- Removed the separate **Search known wines** + **Known wine** controls.
- Added one **Known wine** autocomplete that both searches and selects.
- Search remains normalized for accents, capitalization, punctuation, spaces, and hyphens.
- Examples such as `cotes du rob blanc` can match `Côtes-du-Rôbles Blanc`.
- Winery, vintage, and wine terms can be mixed in the same search.
- Repeated identical visible wine labels are suppressed from the selector.
- Includes a deployment-safe fallback to Streamlit's built-in selector if the autocomplete component is unavailable.

After committing both files, let Streamlit rebuild so it installs `streamlit-searchbox`.
