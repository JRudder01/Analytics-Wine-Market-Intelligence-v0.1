from __future__ import annotations

from pathlib import Path
from datetime import date
import io
import json
import re
import requests
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
RAW = DATA / "raw"
CONTEXT_PATH = DATA / "public_context.csv"
RAW.mkdir(parents=True, exist_ok=True)

BLS_WINE_CPI_SERIES = "CUUR0000SEFW03"  # CPI-U, US city average, Wine at home, unadjusted
BLS_URL = f"https://api.bls.gov/publicAPI/v1/timeseries/data/{BLS_WINE_CPI_SERIES}"
TTB_WINE_YEARLY_URL = "https://www.ttb.gov/system/files/2024-08/Wine_yearly_data_csv.csv"
TTB_WINE_MONTHLY_URL = "https://www.ttb.gov/system/files/2024-08/Wine_monthly_data_csv.csv"
TTB_WINE_PERMIT_URL = "https://www.ttb.gov/system/files/2025-04/FRL_Wine_Producer_and_Blender_Permit_List.csv"
USDA_2025_GRAPE_CRUSH_URL = "https://www.nass.usda.gov/Statistics_by_State/California/Publications/Specialty_and_Other_Releases/Grapes/Crush/Final/2025/2025_final_gcbtb08.csv"


def _read_context() -> pd.DataFrame:
    if CONTEXT_PATH.exists():
        return pd.read_csv(CONTEXT_PATH)
    return pd.DataFrame(columns=["metric", "value", "unit", "period", "source_name", "source_url", "captured_date", "confidence", "model_use"])


def _upsert_context(rows: list[dict]) -> pd.DataFrame:
    current = _read_context()
    new = pd.DataFrame(rows)
    if not current.empty:
        current = current[~current["metric"].astype(str).isin(new["metric"].astype(str))]
    out = pd.concat([current, new], ignore_index=True)
    out.to_csv(CONTEXT_PATH, index=False)
    return out


def refresh_bls_wine_cpi(timeout: int = 25) -> dict:
    r = requests.get(BLS_URL, timeout=timeout)
    r.raise_for_status()
    payload = r.json()
    series = payload.get("Results", {}).get("series", [])
    if not series:
        raise RuntimeError("BLS returned no Wine at Home series data.")
    points = []
    for item in series[0].get("data", []):
        period = item.get("period", "")
        if not re.fullmatch(r"M(0[1-9]|1[0-2])", period):
            continue
        points.append({
            "year": int(item["year"]),
            "month": int(period[1:]),
            "value": float(item["value"]),
        })
    points.sort(key=lambda x: (x["year"], x["month"]))
    if len(points) < 13:
        raise RuntimeError("BLS returned too few monthly observations to calculate YoY change.")
    latest = points[-1]
    prior = next((p for p in reversed(points[:-1]) if p["year"] == latest["year"] - 1 and p["month"] == latest["month"]), None)
    if prior is None:
        raise RuntimeError("Could not locate the year-prior BLS Wine at Home observation.")
    yoy = 100.0 * (latest["value"] / prior["value"] - 1.0)
    period = f"{latest['year']}-{latest['month']:02d}"
    _upsert_context([{
        "metric": "wine_cpi_yoy_pct",
        "value": round(yoy, 3),
        "unit": "percent",
        "period": period,
        "source_name": "U.S. Bureau of Labor Statistics",
        "source_url": BLS_URL,
        "captured_date": date.today().isoformat(),
        "confidence": "High",
        "model_use": "Light-touch national wine price pressure",
    }])
    pd.DataFrame(points).to_csv(RAW / "bls_wine_at_home.csv", index=False)
    return {"source": "BLS Wine at Home CPI", "status": "ok", "period": period, "value": yoy, "rows": len(points)}


def _download_csv(url: str, target: Path, timeout: int = 35) -> pd.DataFrame:
    r = requests.get(url, timeout=timeout, headers={"User-Agent": "RudderAnalytics-WineDataHub/0.2"})
    r.raise_for_status()
    target.write_bytes(r.content)
    try:
        return pd.read_csv(io.BytesIO(r.content), low_memory=False)
    except Exception:
        return pd.read_csv(io.BytesIO(r.content), sep=None, engine="python", low_memory=False)


def refresh_ttb_open_data(timeout: int = 35) -> list[dict]:
    results = []
    for label, url, fn in [
        ("TTB Wine Yearly", TTB_WINE_YEARLY_URL, "ttb_wine_yearly.csv"),
        ("TTB Wine Monthly", TTB_WINE_MONTHLY_URL, "ttb_wine_monthly.csv"),
        ("TTB Wine Producer Permits", TTB_WINE_PERMIT_URL, "ttb_wine_producers.csv"),
    ]:
        try:
            df = _download_csv(url, RAW / fn, timeout=timeout)
            results.append({"source": label, "status": "ok", "rows": len(df), "url": url})
            if label.endswith("Permits"):
                _derive_permit_counts(df, url)
        except Exception as exc:
            results.append({"source": label, "status": "error", "message": str(exc), "url": url})
    return results


def _derive_permit_counts(df: pd.DataFrame, source_url: str) -> None:
    cols = {str(c).strip().casefold(): c for c in df.columns}
    state_col = next((v for k, v in cols.items() if k in {"state", "premise state", "state code"} or k.endswith(" state")), None)
    county_col = next((v for k, v in cols.items() if "county" in k), None)
    if state_col is None:
        return
    states = df[state_col].astype(str).str.upper().str.strip()
    ca = df[states.isin(["CA", "CALIFORNIA"])].copy()
    rows = [{
        "metric": "ttb_ca_wine_producer_permit_count",
        "value": int(len(ca)),
        "unit": "count",
        "period": date.today().isoformat(),
        "source_name": "TTB List of Permittees",
        "source_url": source_url,
        "captured_date": date.today().isoformat(),
        "confidence": "High",
        "model_use": "Informational producer-market context",
    }]
    if county_col is not None:
        county = ca[county_col].astype(str).str.casefold().str.strip()
        for metric, needle in [("ttb_slo_wine_producer_permit_count", "san luis obispo"), ("ttb_napa_wine_producer_permit_count", "napa")]:
            rows.append({
                "metric": metric,
                "value": int(county.str.contains(needle, regex=False, na=False).sum()),
                "unit": "count",
                "period": date.today().isoformat(),
                "source_name": "TTB List of Permittees",
                "source_url": source_url,
                "captured_date": date.today().isoformat(),
                "confidence": "Moderate",
                "model_use": "Informational regional producer-market context",
            })
    _upsert_context(rows)


def refresh_usda_grape_crush(timeout: int = 35) -> dict:
    """Download the current official 2025 final CSV.

    v0.2 retains the official raw file and uses the verified summary metrics already
    in public_context.csv. A generalized table parser is intentionally deferred
    until multiple annual schemas are regression-tested.
    """
    df = _download_csv(USDA_2025_GRAPE_CRUSH_URL, RAW / "usda_ca_grape_crush_2025.csv", timeout=timeout)
    return {"source": "USDA/NASS 2025 Final Grape Crush", "status": "ok", "rows": len(df), "url": USDA_2025_GRAPE_CRUSH_URL}


def refresh_all_public_data() -> list[dict]:
    results = []
    try:
        results.append(refresh_bls_wine_cpi())
    except Exception as exc:
        results.append({"source": "BLS Wine at Home CPI", "status": "error", "message": str(exc), "url": BLS_URL})
    results.extend(refresh_ttb_open_data())
    try:
        results.append(refresh_usda_grape_crush())
    except Exception as exc:
        results.append({"source": "USDA/NASS Grape Crush", "status": "error", "message": str(exc), "url": USDA_2025_GRAPE_CRUSH_URL})
    return results
