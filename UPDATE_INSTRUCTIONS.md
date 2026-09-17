# Update instructions — v0.3.12

Replace these files in the repository root:

- `app.py`
- `pricing_engine.py`

Replace this database file:

- `data/wine_comps.csv`

No Streamlit secret or requirements changes are needed.

After GitHub/Streamlit redeploys, re-run the Eberle `Cotes du Robles Blanc` test. It should load as `White Blend`, red Rhône wines should no longer receive full same-category credit, and the price-landscape x-axis should show integer years only.
