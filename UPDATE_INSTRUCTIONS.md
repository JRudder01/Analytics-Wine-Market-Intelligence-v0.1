# Rudder Wine Market Intelligence — Combined v0.3.2 + v0.3.3 Update

This package combines the changes from v0.3.2 and v0.3.3 so you can update the existing repo in one pass.

## Replace these root files
- `app.py`
- `data_loader.py`
- `pricing_engine.py`
- `vision_intake.py`
- `requirements.txt`
- `README.md`
- `SOURCES.md`

## Add this new root file
- `github_storage.py`

## Optional test updates
Replace/add these under `tests/`:
- `current_price_test.py`
- `vision_intake_test.py`
- `github_storage_test.py`

## Optional reference file
- `.streamlit/secrets.example.toml` is documentation only. Do **not** put real secrets in GitHub.

## What this combined update contains
- duplicate / price-update / alternate-price-type detection
- newest-observation logic for current-market pricing
- screenshot-intake estate rule refinement
- batch staging of approved wine comps
- `Commit pending changes to GitHub database` button
- conflict-safe GitHub write-back using the current file SHA

## Streamlit secrets required for GitHub write-back
Keep your existing OpenAI settings and add:

```toml
GITHUB_TOKEN = "your-fine-grained-token"
GITHUB_REPO = "JRudder01/Analytics-Wine-Market-Intelligence-v0.1"
GITHUB_BRANCH = "main"
GITHUB_COMPS_PATH = "data/wine_comps.csv"
```

The GitHub token should be limited to this repository with **Contents: Read and write** permission.

## Upload note
Extract this ZIP to a normal Windows folder first. Do not drag files directly from inside the compressed ZIP into GitHub's web uploader. If GitHub still errors, upload the root files one at a time.
