# Rudder Analytics — Wine Market Intelligence v0.1

First working prototype of the standalone Rudder Analytics wine pricing / market-positioning tool.

## What this build does

- Loads a starter Paso Robles Cabernet/Bordeaux comp dataset.
- Includes Eberle as a first validation producer.
- Lets a user enter or load a wine and add optional critic score, production, tier, estate/single-vineyard status, COGS, channel mix, and prior MSRP.
- Returns three positions: **Volume / Lower-Risk**, **Market-Aligned**, and **Premium / Higher-Risk**.
- Shows a comparable-supported range, model confidence, closest comps, price landscape, pricing drivers, and approximate blended per-bottle economics.
- Accepts additional CSV/XLSX comp data during the Streamlit session.
- Exports the recommendation to CSV.

## Important v0.1 limitation

This is intentionally a market-positioning prototype, not yet a demand forecast. It does **not** estimate cases sold from price until winery-specific sales history is available. Prototype adjustment coefficients should be calibrated as the comp database grows.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Streamlit Community Cloud

Upload the contents of this folder to a GitHub repository, create a Streamlit app from the repo, and set the main file to `app.py`. No secrets are required for v0.1.

## Starter data

`data/seed_wines.csv` contains:

1. Cabernet Sauvignon and Bordeaux-blend observations extracted from the supplied `Wine Pricing.accdb` database.
2. Publicly verified Eberle price/product observations used for early validation.

The app excludes an exact target wine/vintage from its own comparable set to reduce price leakage during backtesting.

## Add comps

Use `data/comp_import_template.csv` as the schema. The Comparable Database page accepts CSV or Excel files for session-only expansion.

## Suggested next build

1. Convert the full Access wine table into the normalized schema.
2. Add persistent PostgreSQL/Supabase storage.
3. Add scheduled winery-tech-sheet and permitted public-source enrichment.
4. Add CDFA grape-price and NOAA vintage-weather features.
5. Expand Paso Cabernet sample size, then add Napa Cabernet.
6. Add sales-history upload and price-elasticity / gross-profit optimization.
