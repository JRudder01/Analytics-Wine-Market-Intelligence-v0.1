# Rudder Analytics — Wine Market Intelligence v0.2

This build folds the expanded Paso Robles pricing workbook and the public-data layer into the main Wine Market Intelligence repository. The data layer remains logically separate, but for the MVP it lives inside the same repo under `data/` and the **Data Hub (Admin)** workspace. A separate database service is not required yet.

## What changed from v0.1

- Replaced the small starter comp set with **122 usable pricing observations**: 120 priced records normalized from `Wine Prices_Paso - 2025-11-15.xlsx`, plus two Eberle public enrichment records retained from v0.1.
- Coverage now includes Détente, Eberle, Vina Robles, Peachy Canyon, and Austin Hope.
- Added stronger product-tier matching so Reserve/Flagship wines have less influence on Core-tier recommendations.
- Added a staged comparable hierarchy: same label / prior vintages → same winery & tier → same category & tier → broader fallback.
- Added **Historical backtest** mode that excludes later vintages.
- Added explainable confidence components rather than only one unexplained score.
- Renamed strategies to **Volume-Oriented / Market-Aligned / Premium Positioning** until winery-specific demand elasticity is available.
- Added public market context with a small capped effect (±4%).
- Added an internal **Data Hub (Admin)** page for workbook imports, manual comp additions, downloads, and public-data refresh status.
- Added government/open-data connectors for BLS, TTB, and USDA/NASS.
- Added a weekly GitHub Action to refresh public data and commit the refreshed cache back to the repository.

## Architecture

```text
Rudder workbook + manual researched comps
                  \
                   -> data/wine_comps.csv -> pricing engine -> customer result
                  /
BLS / TTB / USDA public data
        -> data/public_context.csv + data/raw/
```

For this stage, keeping the data in the same GitHub repository is simpler than running a second app and database. The split is still clean in code: pricing logic reads normalized data; Data Hub handles ingestion and refreshes.

Move the shared data layer to Supabase/PostgreSQL when one or more of these become true:

1. multiple Rudder staff need to edit records concurrently;
2. customers need persistent uploads/history;
3. scheduled collectors are writing many records per day;
4. the comp database grows beyond what is comfortable in versioned CSV files.

## Deploy to Streamlit

Upload the contents of this folder to the existing Wine Market Intelligence GitHub repository (or a new v0.2 branch while testing). The repository root should contain:

```text
.streamlit/
.github/
assets/
data/
scripts/
tests/
app.py
data_loader.py
pricing_engine.py
public_data.py
requirements.txt
README.md
SOURCES.md
```

Streamlit Community Cloud settings:

- Branch: `main` (or your test branch)
- Main file: `app.py`

## Public data refresh

The Data Hub includes a **Refresh public data now** button. On Streamlit Community Cloud, files written by that button are temporary because the app filesystem is ephemeral.

The persistent path is the included GitHub Actions workflow:

`.github/workflows/refresh-public-data.yml`

It runs weekly and can also be triggered manually from GitHub Actions. It currently:

- refreshes BLS Wine at Home CPI;
- downloads TTB wine yearly/monthly data;
- downloads TTB wine producer permits;
- downloads the official 2025 final California Grape Crush CSV;
- commits refreshed files back to the repo if they changed.

No retailer/winery scraping is required for these public feeds.

## Public-context model use

v0.2 intentionally limits the public context effect. Public market data should fine-tune a comparable-based estimate, not overpower actual bottle-market comps.

Current active context inputs:

- Wine at Home CPI year-over-year change (BLS)
- California red-wine grape crush year-over-year change (USDA/NASS snapshot)

The combined adjustment is capped at ±4%.

TTB raw data is collected now for later feature engineering and validation; it does not yet directly alter MSRP. NOAA vintage climate is the next planned connector and will require a free NOAA token plus validated station/AVA mapping.

## Important modeling limitation

The current tool recommends **market position**, not expected case sales. Do not interpret the three price strategies as quantified sell-through probabilities. Winery-specific historical sales/pricing data is required before building a true demand-elasticity forecast.
