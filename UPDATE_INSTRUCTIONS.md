# Rudder Wine Market Intelligence v0.3.6 — Combined UI/Data Intake Patch

This patch combines the two pending refinements:

1. **v0.3.5 deterministic general-category mapping**
   - Muscat Canelli and other common aromatic/white varieties map to `White` rather than occasionally falling through to `Red`.
   - Existing Estate, duplicate, price-update and source-handling rules remain intact.

2. **Immediate post-GitHub-commit reset**
   - After a successful batch commit, the local `uploaded_comps` queue is cleared immediately.
   - Screenshot intake state is reset.
   - Streamlit's data cache is cleared.
   - The app reruns immediately, so **Pending observations** redraws as `0` rather than continuing to show the pre-commit count.
   - A success flash confirms that the batch is permanently stored and the local pending queue was cleared.

## Install
Replace these two root-level files in GitHub:

- `app.py`
- `vision_intake.py`

Commit both to `main`. No changes are required to `github_storage.py`, `pricing_engine.py`, `requirements.txt`, Streamlit Secrets, or `data/wine_comps.csv`.

## Expected behavior after a batch commit
After clicking **Commit pending changes to GitHub database** and receiving a successful GitHub response, the app will rerun and the pending count should immediately display `0`. The GitHub commit link is optional and is no longer required for the save to take effect.
