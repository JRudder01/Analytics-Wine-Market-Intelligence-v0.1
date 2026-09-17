from __future__ import annotations

from pathlib import Path
import io
import re
import numpy as np
import pandas as pd

from pricing_engine import normalize_comp_data

ROOT = Path(__file__).resolve().parent
COMP_PATH = ROOT / "data" / "wine_comps.csv"
CONTEXT_PATH = ROOT / "data" / "public_context.csv"
VISITOR_PATH = ROOT / "data" / "paso_monthly_visitors_reference.csv"
FEES_PATH = ROOT / "data" / "paso_tasting_fees_reference.csv"


def _read_flexible_csv(source) -> pd.DataFrame:
    return pd.read_csv(source, sep=None, engine="python")


def load_comps() -> pd.DataFrame:
    return normalize_comp_data(_read_flexible_csv(COMP_PATH))


def load_public_context() -> pd.DataFrame:
    if not CONTEXT_PATH.exists():
        return pd.DataFrame(columns=["metric", "value", "unit", "period", "source_name", "source_url", "captured_date", "confidence", "model_use"])
    return _read_flexible_csv(CONTEXT_PATH)


def load_reference_table(path: Path) -> pd.DataFrame:
    return _read_flexible_csv(path) if path.exists() else pd.DataFrame()


def load_upload(uploaded_file) -> pd.DataFrame:
    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        df = _read_flexible_csv(uploaded_file)
    elif name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(uploaded_file)
    else:
        raise ValueError("Please upload a CSV or Excel workbook.")
    return normalize_comp_data(df)


def _infer_tier(wine: str, price) -> str:
    name = str(wine or "").lower()
    try:
        p = float(price)
    except Exception:
        p = np.nan
    if "reserve" in name:
        return "Flagship" if np.isfinite(p) and p >= 120 else "Reserve"
    if "estate" in name:
        return "Estate"
    if "limited" in name or "cellar club" in name or "d block" in name:
        return "Limited"
    if np.isfinite(p) and p >= 120:
        return "Flagship"
    if np.isfinite(p) and p >= 80:
        return "Reserve"
    if np.isfinite(p) and p >= 65:
        return "Limited"
    if np.isfinite(p) and p >= 50:
        return "Estate"
    if np.isfinite(p) and p < 25:
        return "Value/Core"
    return "Core"


def load_rudder_pricing_workbook(uploaded_file) -> pd.DataFrame:
    """Normalize the supplied Rudder/Paso pricing workbook's repeated sections on the Data sheet."""
    raw = pd.read_excel(uploaded_file, sheet_name="Data", header=None, usecols="A:H")
    records = []
    for _, row in raw.iterrows():
        vals = row.tolist() + [None] * 8
        winery, wine, varietal, graph, general, vintage, price, price_change = vals[:8]
        if pd.isna(winery) or pd.isna(wine) or str(winery).strip() == "Winery" or str(wine).strip() == "Wine":
            continue
        price_num = pd.to_numeric(pd.Series([price]), errors="coerce").iloc[0]
        if pd.isna(price_num) or price_num <= 0:
            continue
        vintage_num = pd.to_numeric(pd.Series([vintage]), errors="coerce").iloc[0]
        records.append({
            "winery": str(winery).strip(),
            "wine": str(wine).strip(),
            "vintage": vintage_num,
            "varietal": "" if pd.isna(varietal) else str(varietal).strip(),
            "graph_category": "" if pd.isna(graph) else str(graph).strip(),
            "general_category": "" if pd.isna(general) else str(general).strip(),
            "region": "Paso Robles",
            "subregion": "",
            "price": price_num,
            "price_type": "Historical listed price",
            "critic": "",
            "critic_score": np.nan,
            "cases_produced": np.nan,
            "alcohol_pct": np.nan,
            "estate": "estate" in str(wine).lower(),
            "single_vineyard": False,
            "product_tier": _infer_tier(wine, price_num),
            "source_name": getattr(uploaded_file, "name", "Rudder pricing workbook"),
            "source_url": "",
            "price_date": "",
            "data_confidence": "Moderate",
        })
    return normalize_comp_data(pd.DataFrame(records))


def merge_data(seed: pd.DataFrame, added: pd.DataFrame | None) -> pd.DataFrame:
    if added is None or added.empty:
        return seed.copy()
    combined = pd.concat([seed, added], ignore_index=True)
    return combined.drop_duplicates(["winery", "wine", "vintage", "price", "price_type"], keep="last")
