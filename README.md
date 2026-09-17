# Rudder Analytics — Wine Market Intelligence v0.3.2

v0.3 adds **AI Screenshot Intake** to the v0.2 comparable-market/public-data architecture. A Rudder administrator can upload 1–4 screenshots of one wine product/shop page, have OpenAI vision extract only visibly supported facts, review/edit the proposed comp row, and add the approved observation to the current Data Hub session.

The customer-facing Pricing Analysis remains separate from this admin workflow.

## What changed from v0.2

- Added `vision_intake.py` for screenshot-to-structured-wine extraction.
- Added **Screenshot Intake** at the top of **Data Hub (Admin)**.
- Supports 1–4 PNG/JPG/JPEG/WebP screenshots for a single wine.
- Uses the OpenAI Responses API with image input + strict JSON Schema output.
- Default model: `gpt-5.6-terra`; Luna and Sol can be selected by an admin.
- AI extracts literal page facts; deterministic Rudder rules then infer:
  - market category;
  - general category;
  - price type;
  - product tier;
  - Estate status;
  - Single-vineyard status.
- Club/member prices are detected and shown to the reviewer but are not silently substituted for the ordinary public bottle price.
- Wine-competition scores/medals are kept separate from named editorial critic scores.
- Adds a duplicate check on winery + wine + vintage before approval.
- All proposed fields remain editable before approval.
- Approved rows are added only to the current session until the merged comp CSV is downloaded and committed to GitHub.
- Existing v0.2 workbook import, manual entry, public-data refresh, pricing model and GitHub Action remain intact.

## Architecture

```text
Admin-captured winery/retailer screenshots
              ↓
OpenAI vision structured extraction
              ↓
Rudder deterministic classification rules
              ↓
Human review + duplicate check
              ↓
Approved session comp
              ↓
Download merged wine_comps.csv
              ↓
GitHub / Data Hub seed
              ↓
Wine Market Intelligence pricing engine

Rudder historical workbook + manual comps ────────┘
BLS / TTB / USDA public context ──────────────────┘
```

## OpenAI setup

The screenshot tool requires an OpenAI API key. Keep the key in Streamlit Secrets; do **not** commit it to GitHub.

In Streamlit Community Cloud, open the app's settings/secrets and add:

```toml
OPENAI_API_KEY = "sk-..."
OPENAI_VISION_MODEL = "gpt-5.6-terra"
```

`OPENAI_VISION_MODEL` is optional. If omitted, the app defaults to `gpt-5.6-terra`.

Local development can instead use environment variables with the same names.

The Responses request uses `store=False` and only runs after an administrator explicitly clicks **Extract wine details with AI**.

## Screenshot Intake workflow

1. Open **Data Hub (Admin)**.
2. Upload 1–4 screenshots from one wine product page.
3. Paste the source URL for provenance (the app does not automatically visit it).
4. Choose the source type: Official winery site, Retailer / merchant, or Other public source.
5. Click **Extract wine details with AI**.
6. Review extraction warnings/evidence.
7. Edit the proposed comp fields as needed.
8. Review any same-wine/vintage duplicate warning.
9. Click **Approve & add comparable to this session**.
10. Use **Download merged comp database** and replace `data/wine_comps.csv` in GitHub to persist the additions.

### Extraction rules

The AI is instructed to use only facts visible in the supplied screenshots and return `null` for missing facts. Rudder does not ask it to guess case production, critic scores, appellation, or other absent data.

Rudder's deterministic rules then apply the database conventions established for the project:

- **Winery MSRP** only when the page explicitly labels MSRP/SRP/Suggested Retail/List Price.
- An unlabeled purchase price on an official winery shop page becomes **Winery retail**.
- A merchant price becomes **Observed retail**.
- Product tier uses explicit words first: Flagship/Icon/Benchmark → Flagship; Reserve → Reserve; Estate → Estate; Limited/Cellar Club → Limited; otherwise Core.
- `single_vineyard = TRUE` only when visible evidence clearly ties the finished wine to one named vineyard. Multiple vineyard sources force FALSE.
- Competition scores are shown as evidence but are not automatically placed in the editorial critic-score field.

## Repository structure

```text
.github/
    workflows/
        refresh-public-data.yml
.streamlit/
    config.toml
    secrets.example.toml
assets/
data/
scripts/
tests/
app.py
data_loader.py
pricing_engine.py
public_data.py
vision_intake.py
.gitignore
requirements.txt
README.md
SOURCES.md
run_local.bat
```

The new root-level file for v0.3 is:

`vision_intake.py`

`requirements.txt` also adds the official `openai` SDK and Pillow.

## Public-data refresh

The v0.2 public-data workflow is unchanged: BLS, TTB and USDA/NASS feeds are downloaded through their public/API endpoints and the GitHub Action refreshes them weekly. Screenshot Intake does not crawl or scrape commercial sites; it analyzes only screenshots that a Rudder administrator explicitly uploads.

## Persistence limitation

Streamlit Community Cloud has an ephemeral filesystem. For v0.3, clicking **Approve** changes the Data Hub session only. Persist the new rows by downloading the merged `wine_comps.csv` and committing it to GitHub.

A later Supabase/PostgreSQL phase can turn approval into a permanent database insert without the download/commit step.


## v0.3.1 additions

- Clipboard screenshot intake via a **Paste screenshot from clipboard** button (HTTPS/browser Clipboard API required).
- Up to four screenshots can be combined across file uploads and clipboard pastes.
- Clipboard screenshots can be previewed and cleared before extraction.
- Estate classification is stricter: component vineyard/source wording such as "from Eberle Estate" no longer marks the finished wine Estate. Estate now requires the wine name itself or clear whole-wine estate-grown/estate-bottled evidence.


## v0.3.2 additions

- Screenshot and manual intake now classifies existing records as **new**, **exact duplicate**, **price update**, **alternate price type**, or **corroborating source**.
- Exact duplicates are blocked from being added again.
- Price updates preserve the older observation for historical analysis and add the newer price as a new dated observation.
- Current-market pricing now uses only the **latest observation** for each wine/vintage/price-type/source identity, preventing old and new prices from both influencing the same current-market comp analysis.
- Alternate price types (for example Winery retail vs Wine club/member price) remain separate observations.
- The Data Hub now displays an explicit persistence reminder: session approvals are **not** written to GitHub automatically. Download the merged database and replace `data/wine_comps.csv` to persist changes.

### Persistence workflow

```text
Approve/add comparable
        ↓
Current Streamlit session only
        ↓
Download merged comp database
        ↓
Downloaded file is already named wine_comps.csv
        ↓
Replace data/wine_comps.csv in GitHub
        ↓
Streamlit redeploys with the persisted database
```

Automatic GitHub writes are intentionally not enabled in v0.3.2 because that would require repository-write credentials in the app. A later Supabase/PostgreSQL data layer is the preferred path for direct permanent inserts.

## v0.3.3 — batched GitHub database persistence

Approved screenshot/manual comp records are staged in the current Streamlit session. The Data Hub now provides a **Commit pending changes to GitHub database** button that saves the whole batch to `data/wine_comps.csv` in one GitHub commit.

Add these Streamlit Secrets (never commit the real token to GitHub):

```toml
GITHUB_TOKEN = "github_pat_..."
GITHUB_REPO = "JRudder01/Analytics-Wine-Market-Intelligence-v0.1"
GITHUB_BRANCH = "main"
GITHUB_COMPS_PATH = "data/wine_comps.csv"
```

Use a fine-grained GitHub personal access token limited to this repository with **Contents: Read and write**. The save process fetches the current file and SHA immediately before each commit and retries once if the file changed concurrently.
