from __future__ import annotations

from pathlib import Path
import io
import pandas as pd

from pricing_engine import normalize_comp_data

ROOT = Path(__file__).resolve().parent
SEED_PATH = ROOT / "data" / "seed_wines.csv"
TEMPLATE_PATH = ROOT / "data" / "comp_import_template.csv"


def load_seed() -> pd.DataFrame:
    return normalize_comp_data(pd.read_csv(SEED_PATH))


def load_upload(uploaded_file) -> pd.DataFrame:
    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    elif name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(uploaded_file)
    else:
        raise ValueError("Please upload a CSV or Excel workbook.")
    return normalize_comp_data(df)


def merge_data(seed: pd.DataFrame, added: pd.DataFrame | None) -> pd.DataFrame:
    if added is None or added.empty:
        return seed.copy()
    combined = pd.concat([seed, added], ignore_index=True)
    # Prefer later rows (uploaded data) on exact duplicate product/vintage/price records.
    return combined.drop_duplicates(["winery", "wine", "vintage", "price", "price_type"], keep="last")
