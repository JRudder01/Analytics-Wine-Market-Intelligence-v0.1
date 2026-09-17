from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import math
import numpy as np
import pandas as pd


TIER_FACTOR = {
    "Value/Core": 0.95,
    "Core": 1.00,
    "Estate": 1.12,
    "Limited": 1.22,
    "Reserve": 1.35,
    "Flagship": 1.95,
}

TIER_ORDER = {
    "Value/Core": 0,
    "Core": 1,
    "Estate": 2,
    "Limited": 3,
    "Reserve": 4,
    "Flagship": 5,
}

CONFIDENCE_MAP = {"Low": 0.55, "Moderate": 0.75, "High": 0.95}


def _clean_text(v) -> str:
    if pd.isna(v):
        return ""
    return str(v).strip()


def _bool(v) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in {"1", "true", "yes", "y", "estate", "single vineyard"}


def weighted_quantile(values: np.ndarray, weights: np.ndarray, q: float) -> float:
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    mask = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    values, weights = values[mask], weights[mask]
    if len(values) == 0:
        return float("nan")
    order = np.argsort(values)
    values, weights = values[order], weights[order]
    cumulative = np.cumsum(weights)
    cutoff = q * cumulative[-1]
    return float(values[np.searchsorted(cumulative, cutoff, side="left")])


def _tier_similarity(target: str, comp: str) -> float:
    if not target or not comp:
        return 0.78
    if target == comp:
        return 1.0
    a = TIER_ORDER.get(target, 1)
    b = TIER_ORDER.get(comp, 1)
    d = abs(a - b)
    return {1: 0.70, 2: 0.48, 3: 0.34, 4: 0.25, 5: 0.20}.get(d, 0.20)


def _category_similarity(target_graph: str, comp_graph: str, target_general: str, comp_general: str) -> float:
    if target_graph and comp_graph and target_graph == comp_graph:
        return 1.0
    cab_bordeaux = {"Cabernet Sauvignon", "Bordeaux Blend"}
    if target_graph in cab_bordeaux and comp_graph in cab_bordeaux:
        return 0.68
    if target_general and comp_general and target_general == comp_general:
        return 0.35
    return 0.12


def _region_similarity(target_region: str, comp_region: str, target_subregion: str, comp_subregion: str) -> float:
    tr, cr = target_region.lower(), comp_region.lower()
    ts, cs = target_subregion.lower(), comp_subregion.lower()
    if ts and cs and ts == cs:
        return 1.10
    if tr and cr and tr == cr:
        return 1.0
    if not tr or not cr:
        return 0.70
    return 0.32


def _source_confidence(v) -> float:
    s = _clean_text(v).lower()
    if s == "high":
        return 1.0
    if s == "moderate":
        return 0.88
    if s == "low":
        return 0.70
    return 0.82


def normalize_comp_data(df: pd.DataFrame) -> pd.DataFrame:
    expected = [
        "winery", "wine", "vintage", "varietal", "graph_category", "general_category",
        "region", "subregion", "price", "price_type", "critic", "critic_score",
        "cases_produced", "alcohol_pct", "estate", "single_vineyard", "product_tier",
        "source_name", "source_url", "price_date", "data_confidence"
    ]
    out = df.copy()
    for c in expected:
        if c not in out.columns:
            out[c] = np.nan
    for c in ["vintage", "price", "critic_score", "cases_produced", "alcohol_pct"]:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    for c in ["winery", "wine", "varietal", "graph_category", "general_category", "region", "subregion",
              "price_type", "critic", "product_tier", "source_name", "source_url", "price_date", "data_confidence"]:
        out[c] = out[c].fillna("").astype(str).str.strip()
    out["estate"] = out["estate"].map(_bool)
    out["single_vineyard"] = out["single_vineyard"].map(_bool)
    out = out[(out["price"] > 0) & out["price"].notna()].copy()
    return out[expected]


def select_comps(df: pd.DataFrame, target: Dict, max_comps: int = 16) -> pd.DataFrame:
    comps = normalize_comp_data(df)
    winery = _clean_text(target.get("winery"))
    wine = _clean_text(target.get("wine"))
    vintage = float(target.get("vintage") or np.nan)
    graph = _clean_text(target.get("graph_category") or target.get("varietal"))
    general = _clean_text(target.get("general_category") or "Red")
    region = _clean_text(target.get("region"))
    subregion = _clean_text(target.get("subregion"))
    tier = _clean_text(target.get("product_tier") or "Core")
    critic = target.get("critic_score")
    critic = float(critic) if critic not in (None, "") and not pd.isna(critic) else np.nan

    # Avoid price leakage from the exact target vintage.
    exact_target = (
        comps["winery"].str.casefold().eq(winery.casefold()) &
        comps["wine"].str.casefold().eq(wine.casefold()) &
        comps["vintage"].eq(vintage)
    )
    comps = comps.loc[~exact_target].copy()
    if comps.empty:
        return comps

    def score(r):
        cat = _category_similarity(graph, r["graph_category"], general, r["general_category"])
        reg = _region_similarity(region, r["region"], subregion, r["subregion"])
        if np.isfinite(vintage) and np.isfinite(r["vintage"]):
            vint = math.exp(-abs(vintage - r["vintage"]) / 5.0)
        else:
            vint = 0.72
        tier_s = _tier_similarity(tier, r["product_tier"])
        if np.isfinite(critic) and np.isfinite(r["critic_score"]):
            critic_s = math.exp(-abs(critic - r["critic_score"]) / 9.0)
        else:
            critic_s = 0.86
        same_producer = winery and r["winery"].casefold() == winery.casefold()
        same_label = same_producer and wine and r["wine"].casefold() == wine.casefold()
        label_factor = 3.0 if same_label else (1.12 if same_producer else 1.0)
        source = _source_confidence(r["data_confidence"])
        return cat * reg * vint * tier_s * critic_s * label_factor * source

    comps["similarity_weight"] = comps.apply(score, axis=1)
    # Prefer useful comps, but retain enough fallback observations for an early-stage model.
    comps = comps[comps["similarity_weight"] >= 0.06].copy()
    return comps.sort_values("similarity_weight", ascending=False).head(max_comps)


def _attribute_factor(target: Dict) -> Tuple[float, List[str]]:
    factor = 1.0
    drivers: List[str] = []

    tier = _clean_text(target.get("product_tier") or "Core")
    tf = TIER_FACTOR.get(tier, 1.0)
    factor *= tf
    if tf > 1.02:
        drivers.append(f"{tier} positioning raises the model relative to core-market comps.")
    elif tf < 0.98:
        drivers.append(f"{tier} positioning pulls the estimate toward the value end of the market.")

    critic = target.get("critic_score")
    if critic not in (None, "") and not pd.isna(critic):
        score = float(critic)
        adj = min(1.25, max(0.82, 1.0 + (score - 90.0) * 0.022))
        factor *= adj
        direction = "supports a premium" if score > 90 else "limits the premium"
        drivers.append(f"Critic score of {score:.0f} {direction} versus a 90-point reference.")

    estate = _bool(target.get("estate"))
    single = _bool(target.get("single_vineyard"))
    if estate:
        factor *= 1.035
        drivers.append("Estate designation adds a modest positioning premium.")
    if single:
        factor *= 1.08
        drivers.append("Single-vineyard designation adds scarcity/positioning support.")

    cases = target.get("cases_produced")
    if cases not in (None, "") and not pd.isna(cases):
        cases = float(cases)
        if cases < 300:
            factor *= 1.12
            drivers.append("Very limited production supports scarcity pricing.")
        elif cases < 750:
            factor *= 1.08
            drivers.append("Limited production supports a moderate scarcity premium.")
        elif cases < 1500:
            factor *= 1.05
            drivers.append("Relatively small production supports a modest scarcity premium.")
        elif cases > 20000:
            factor *= 0.92
            drivers.append("High production volume reduces the scarcity premium.")
        elif cases > 10000:
            factor *= 0.96
            drivers.append("Larger production volume modestly reduces scarcity support.")

    return factor, drivers


def _round_price(v: float) -> float:
    if v < 50:
        return float(round(v))
    if v < 100:
        return float(5 * round(v / 5))
    return float(5 * round(v / 5))


def _confidence(target: Dict, comps: pd.DataFrame) -> Tuple[str, int, List[str]]:
    score = 10
    notes = []
    n = len(comps)
    if n >= 10:
        score += 32
    elif n >= 6:
        score += 25
    elif n >= 3:
        score += 16
    else:
        score += 6
        notes.append("Few comparable observations are currently available.")

    if n:
        target_region = _clean_text(target.get("region")).casefold()
        exact_region = (comps["region"].str.casefold() == target_region).mean() if target_region else 0
        target_graph = _clean_text(target.get("graph_category") or target.get("varietal")).casefold()
        exact_cat = (comps["graph_category"].str.casefold() == target_graph).mean() if target_graph else 0
        score += int(15 * exact_region)
        score += int(15 * exact_cat)
        if exact_region < .5:
            notes.append("A meaningful share of comps come from outside the exact target region or lack region data.")
        if exact_cat < .5:
            notes.append("The model needed adjacent wine categories to expand the comparable set.")

    if target.get("previous_msrp") not in (None, ""):
        score += 10
    if target.get("critic_score") not in (None, ""):
        score += 5
    if target.get("cases_produced") not in (None, ""):
        score += 5
    if target.get("product_tier"):
        score += 4
    if _bool(target.get("estate")) or _bool(target.get("single_vineyard")):
        score += 4

    score = int(min(96, max(25, score)))
    label = "High" if score >= 75 else "Moderate" if score >= 55 else "Low"
    return label, score, notes


def analyze_wine(df: pd.DataFrame, target: Dict) -> Dict:
    comps = select_comps(df, target)
    if comps.empty:
        raise ValueError("No usable comparable wines were found. Add more comp data or broaden the target category.")

    vals = comps["price"].to_numpy(float)
    w = comps["similarity_weight"].to_numpy(float)
    q25 = weighted_quantile(vals, w, .25)
    med = weighted_quantile(vals, w, .50)
    q75 = weighted_quantile(vals, w, .75)
    mean = float(np.average(vals, weights=w))
    market_base = 0.70 * med + 0.30 * mean

    attr_factor, drivers = _attribute_factor(target)
    adjusted = market_base * attr_factor

    previous = target.get("previous_msrp")
    previous_vintage = target.get("previous_vintage")
    target_vintage = target.get("vintage")
    if previous not in (None, "") and not pd.isna(previous):
        years = 1
        if previous_vintage not in (None, "") and target_vintage not in (None, ""):
            try:
                years = max(1, int(float(target_vintage) - float(previous_vintage)))
            except Exception:
                years = 1
        anchor = float(previous) * (1.025 ** years)
        adjusted = 0.62 * adjusted + 0.38 * anchor
        drivers.append("Prior-vintage MSRP is used as a stabilizing brand-history anchor.")

    # Scenario range: use both market dispersion and strategic spacing.
    volume_raw = min(adjusted * 0.88, max(q25 * attr_factor, adjusted * 0.82))
    premium_raw = max(adjusted * 1.18, min(q75 * attr_factor, adjusted * 1.24))

    cogs = target.get("cogs")
    if cogs not in (None, "") and not pd.isna(cogs):
        cogs = float(cogs)
        # Protect against recommending DTC price below a basic 45% gross margin floor.
        floor = cogs / 0.55 if cogs > 0 else 0
        if volume_raw < floor:
            volume_raw = floor
            drivers.append("The lower strategy is constrained by the entered COGS to avoid an extremely weak DTC gross margin.")

    volume = _round_price(volume_raw)
    market = _round_price(max(adjusted, volume + 1))
    premium = _round_price(max(premium_raw, market + (5 if market >= 50 else 3)))
    if volume >= market:
        volume = _round_price(market * .91)
    if premium <= market:
        premium = _round_price(market * 1.12)

    label, conf_score, conf_notes = _confidence(target, comps)

    channel = _clean_text(target.get("channel") or "DTC").upper()
    dtc_share = float(target.get("dtc_share") or (1.0 if channel == "DTC" else 0.0 if channel == "WHOLESALE" else .60))
    dtc_share = min(1.0, max(0.0, dtc_share))
    wholesale_net_pct = float(target.get("wholesale_net_pct") or 0.50)

    def economics(msrp):
        realized = msrp * (dtc_share + (1 - dtc_share) * wholesale_net_pct)
        if cogs in (None, "") or pd.isna(cogs):
            margin = np.nan
        else:
            margin = (realized - float(cogs)) / realized if realized > 0 else np.nan
        return realized, margin

    scenarios = []
    for name, price, risk in [
        ("Volume / Lower-Risk", volume, "Lower"),
        ("Market-Aligned", market, "Moderate"),
        ("Premium / Higher-Risk", premium, "Higher"),
    ]:
        realized, margin = economics(price)
        scenarios.append({
            "strategy": name,
            "msrp": price,
            "demand_risk": risk,
            "estimated_net_revenue_per_bottle": realized,
            "gross_margin_pct": margin,
        })

    return {
        "market_base": market_base,
        "market_range_low": _round_price(q25 * attr_factor),
        "market_range_high": _round_price(q75 * attr_factor),
        "attribute_factor": attr_factor,
        "scenarios": scenarios,
        "confidence_label": label,
        "confidence_score": conf_score,
        "confidence_notes": conf_notes,
        "drivers": drivers,
        "comps": comps,
    }
