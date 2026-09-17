# Rudder Wine Market Intelligence v0.3.4 — Screenshot reset patch

This cumulative patch is intended for the repository already running the combined v0.3.2/v0.3.3 build.

## Replace
- `app.py` at the repository root

## Changes
- **Clear screenshots & reset intake** now clears both normal file uploads and clipboard-pasted screenshots.
- Clipboard state is remounted with a fresh Streamlit widget key so the previous pasted image cannot immediately reappear.
- The file uploader is also remounted, so previously uploaded screenshots disappear from the UI.
- Source URL / source-name override fields reset with the intake.
- After a successful **Approve & add comparable to this session**, screenshot intake automatically clears and is ready for the next wine.
- The staged comparable remains safely in the current session and is not lost by the reset.
- The next run displays the success message and reminds you that the observation is pending GitHub commit.

No changes to `vision_intake.py`, `pricing_engine.py`, `github_storage.py`, or the database are required.
