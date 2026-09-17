from __future__ import annotations

from typing import Dict, List, Tuple
import math
import numpy as np
import pandas as pd

TIER_FACTOR = {
    "Value/Core": 0.94,
    "Core": 1.00,
    "Estate": 1.10,
    "Limited": 1.18,
    "Reserve": 1.30,
    "Flagship": 1.52,
}

TIER_ORDER = {
    "Value/Core": 0,
    "Core": 1,
    "Estate": 2,
    "Limited": 3,
    "Reserve": 4,
    "Flagship": 5,
}


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
        return 0.72
    if target == comp:
        return 1.0
    a = TIER_ORDER.get(target, 1)
    b = TIER_ORDER.get(comp, 1)
    d = abs(a - b)
    # v0.2: intentionally stronger penalty for adjacent tiers than v0.1.
    return {1: 0.52, 2: 0.26, 3: 0.14, 4: 0.08, 5: 0.05}.get(d, 0.05)


def _category_similarity(target_graph: str, comp_graph: str, target_general: str, comp_general: str) -> float:
    if target_graph and comp_graph and target_graph.casefold() == comp_graph.casefold():
        return 1.0
    cab_bordeaux = {"cabernet sauvignon", "bordeaux blend"}
    if target_graph.casefold() in cab_bordeaux and comp_graph.casefold() in cab_bordeaux:
        return 0.56
    if target_general and comp_general and target_general.casefold() == comp_general.casefold():
        return 0.20
    return 0.06


def _region_similarity(target_region: str, comp_region: str, target_subregion: str, comp_subregion: str) -> float:
    tr, cr = target_region.casefold(), comp_region.casefold()
    ts, cs = target_subregion.casefold(), comp_subregion.casefold()
    if ts and cs and ts == cs:
        return 1.12
    if tr and cr and tr == cr:
        return 1.0
    if not tr or not cr:
        return 0.62
    return 0.24


def _source_confidence(v) -> float:
    s = _clean_text(v).casefold()
    if s == "high":
        return 1.0
    if s == "moderate":
        return 0.87
    if s == "low":
        return 0.68
    return 0.80


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




def _observation_source_scope(row: pd.Series) -> str:
    price_type = _clean_text(row.get("price_type")).casefold()
    winery_direct = {"winery msrp", "winery retail", "wine club/member price", "historical listed price"}
    if price_type in winery_direct:
        return f"winery::{_clean_text(row.get('winery')).casefold()}"
    url = _clean_text(row.get("source_url")).casefold()
    if url:
        import re
        m = re.match(r"https?://([^/]+)", url)
        if m:
            return f"site::{m.group(1).removeprefix('www.')}"
    return f"source::{_clean_text(row.get('source_name')).casefold()}"


def latest_current_observations(df: pd.DataFrame) -> pd.DataFrame:
    """Keep the newest price observation per wine/vintage/type/source identity.

    Historical rows remain stored in wine_comps.csv, but current-market pricing should
    not count a winery's old and new price for the same vintage as separate comps.
    Third-party retail sources retain one latest observation per merchant/source.
    """
    if df is None or df.empty:
        return df.copy() if df is not None else pd.DataFrame()
    out = df.copy()
    out["_source_scope"] = out.apply(_observation_source_scope, axis=1)
    out["_parsed_price_date"] = pd.to_datetime(out.get("price_date", ""), errors="coerce")
    out["_row_order"] = np.arange(len(out))
    key = ["winery", "wine", "vintage", "price_type", "_source_scope"]
    out = out.sort_values(["_parsed_price_date", "_row_order"], ascending=[True, True], na_position="first")
    out = out.drop_duplicates(key, keep="last")
    return out.drop(columns=["_source_scope", "_parsed_price_date", "_row_order"], errors="ignore")


def select_comps(df: pd.DataFrame, target: Dict, max_comps: int = 20) -> pd.DataFrame:
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
    analysis_mode = _clean_text(target.get("analysis_mode") or "Current market")

    # Current-market analysis uses only the latest observation for each comp/source
    # identity, while the underlying database retains older prices for history.
    if analysis_mode.casefold().startswith("current"):
        comps = latest_current_observations(comps)

    exact_target = (
        comps["winery"].str.casefold().eq(winery.casefold()) &
        comps["wine"].str.casefold().eq(wine.casefold()) &
        comps["vintage"].eq(vintage)
    )
    comps = comps.loc[~exact_target].copy()

    # Historical backtests cannot use later vintages. Current-market analysis can.
    if analysis_mode.casefold().startswith("historical") and np.isfinite(vintage):
        comps = comps[(comps["vintage"].isna()) | (comps["vintage"] <= vintage)].copy()

    if comps.empty:
        return comps

    def score(r):
        cat = _category_similarity(graph, r["graph_category"], general, r["general_category"])
        reg = _region_similarity(region, r["region"], subregion, r["subregion"])
        if np.isfinite(vintage) and np.isfinite(r["vintage"]):
            # Adjacent vintages matter more than in v0.1.
            vint = math.exp(-abs(vintage - r["vintage"]) / 3.5)
        else:
            vint = 0.67
        tier_s = _tier_similarity(tier, r["product_tier"])
        if np.isfinite(critic) and np.isfinite(r["critic_score"]):
            critic_s = math.exp(-abs(critic - r["critic_score"]) / 8.0)
        else:
            critic_s = 0.84
        same_producer = bool(winery) and r["winery"].casefold() == winery.casefold()
        same_label = same_producer and bool(wine) and r["wine"].casefold() == wine.casefold()
        same_tier = tier and r["product_tier"] == tier
        label_factor = 5.0 if same_label else (1.42 if same_producer and same_tier else 1.15 if same_producer else 1.0)
        source = _source_confidence(r["data_confidence"])
        return cat * reg * vint * tier_s * critic_s * label_factor * source

    comps["similarity_weight"] = comps.apply(score, axis=1)

    def reason(r):
        if winery and wine and r["winery"].casefold() == winery.casefold() and r["wine"].casefold() == wine.casefold():
            return "Same label / other vintage"
        if winery and r["winery"].casefold() == winery.casefold() and r["product_tier"] == tier:
            return "Same winery / same tier"
        if r["graph_category"].casefold() == graph.casefold() and r["product_tier"] == tier:
            return "Same category / same tier"
        if r["graph_category"].casefold() == graph.casefold():
            return "Same category / other tier"
        return "Adjacent category fallback"

    comps["comp_reason"] = comps.apply(reason, axis=1)

    # Stage selection: get high-quality exact-category/tier observations first, then fill only as needed.
    stages = [
        comps[comps["comp_reason"] == "Same label / other vintage"],
        comps[comps["comp_reason"] == "Same winery / same tier"],
        comps[comps["comp_reason"] == "Same category / same tier"],
        comps[comps["comp_reason"] == "Same category / other tier"],
        comps[comps["comp_reason"] == "Adjacent category fallback"],
    ]
    selected = []
    seen = set()
    for stage in stages:
        stage = stage.sort_values("similarity_weight", ascending=False)
        for idx, row in stage.iterrows():
            if idx in seen or row["similarity_weight"] < 0.025:
                continue
            selected.append(row)
            seen.add(idx)
            if len(selected) >= max_comps:
                break
        if len(selected) >= max_comps:
            break
    if not selected:
        return comps.iloc[0:0].copy()
    return pd.DataFrame(selected).sort_values("similarity_weight", ascending=False).reset_index(drop=True)


def _attribute_factor(target: Dict) -> Tuple[float, List[str], List[str]]:
    factor = 1.0
    upward: List[str] = []
    downward: List[str] = []

    tier = _clean_text(target.get("product_tier") or "Core")
    tf = TIER_FACTOR.get(tier, 1.0)
    factor *= tf
    if tf > 1.02:
        upward.append(f"{tier} positioning supports a premium versus a core-tier reference.")
    elif tf < 0.98:
        downward.append(f"{tier} positioning keeps the recommendation toward the value end of the market.")

    critic = target.get("critic_score")
    if critic not in (None, "") and not pd.isna(critic):
        score = float(critic)
        adj = min(1.20, max(0.86, 1.0 + (score - 90.0) * 0.018))
        factor *= adj
        if score > 90:
            upward.append(f"Critic score of {score:.0f} supports additional pricing power.")
        elif score < 90:
            downward.append(f"Critic score of {score:.0f} limits the quality premium versus a 90-point reference.")

    estate = _bool(target.get("estate"))
    single = _bool(target.get("single_vineyard"))
    if estate:
        factor *= 1.025
        upward.append("Estate designation provides modest positioning support.")
    if single:
        factor *= 1.06
        upward.append("Single-vineyard designation provides scarcity/positioning support.")

    cases = target.get("cases_produced")
    if cases not in (None, "") and not pd.isna(cases):
        cases = float(cases)
        if cases < 300:
            factor *= 1.09
            upward.append("Very limited production supports scarcity pricing.")
        elif cases < 750:
            factor *= 1.06
            upward.append("Limited production supports a moderate scarcity premium.")
        elif cases < 1500:
            factor *= 1.035
            upward.append("Relatively small production supports a modest scarcity premium.")
        elif cases > 20000:
            factor *= 0.93
            downward.append("High production volume reduces scarcity support.")
        elif cases > 10000:
            factor *= 0.97
            downward.append("Larger production volume modestly reduces scarcity support.")

    return factor, upward, downward


def _market_context_factor(context: pd.DataFrame | None, general_category: str) -> Tuple[float, List[str]]:
    """Use public context lightly; cap the total effect to +/-4%."""
    if context is None or context.empty:
        return 1.0, []
    values = {}
    for _, r in context.iterrows():
        try:
            values[str(r.get("metric", ""))] = float(r.get("value"))
        except Exception:
            pass
    adjustment_pct = 0.0
    notes: List[str] = []

    cpi = values.get("wine_cpi_yoy_pct")
    if cpi is not None:
        cpi_effect = 0.20 * cpi
        adjustment_pct += cpi_effect
        notes.append(f"National wine-at-home CPI ({cpi:+.1f}% YoY) contributes a {cpi_effect:+.2f}% light-touch market adjustment.")

    if general_category.casefold() == "red":
        crush = values.get("ca_red_wine_grape_crush_yoy_pct")
        if crush is not None:
            supply_effect = -0.10 * crush
            adjustment_pct += supply_effect
            notes.append(f"California red-wine grape crush ({crush:+.1f}% YoY) contributes a {supply_effect:+.2f}% light-touch supply adjustment.")

    adjustment_pct = min(4.0, max(-4.0, adjustment_pct))
    return 1.0 + adjustment_pct / 100.0, notes


def _round_price(v: float) -> float:
    if v < 50:
        return float(round(v))
    return float(5 * round(v / 5))


def _confidence(target: Dict, comps: pd.DataFrame, context: pd.DataFrame | None) -> Tuple[str, int, Dict[str, str], List[str]]:
    n = len(comps)
    notes: List[str] = []

    if n >= 15:
        coverage_score, coverage_label = 30, "Strong"
    elif n >= 10:
        coverage_score, coverage_label = 26, "Strong"
    elif n >= 6:
        coverage_score, coverage_label = 20, "Moderate"
    elif n >= 3:
        coverage_score, coverage_label = 13, "Limited"
    else:
        coverage_score, coverage_label = 6, "Weak"
        notes.append("Few comparable observations are available.")

    target_graph = _clean_text(target.get("graph_category") or target.get("varietal")).casefold()
    exact_cat = (comps["graph_category"].str.casefold() == target_graph).mean() if n and target_graph else 0
    cat_score = int(22 * exact_cat)
    cat_label = "Strong" if exact_cat >= .75 else "Moderate" if exact_cat >= .45 else "Limited"

    target_tier = _clean_text(target.get("product_tier") or "Core")
    exact_tier = (comps["product_tier"] == target_tier).mean() if n else 0
    tier_score = int(18 * exact_tier)
    tier_label = "Strong" if exact_tier >= .65 else "Moderate" if exact_tier >= .35 else "Limited"

    same_label_n = int((comps["comp_reason"] == "Same label / other vintage").sum()) if n and "comp_reason" in comps else 0
    history_score = min(12, same_label_n * 5)
    history_label = "Strong" if same_label_n >= 2 else "Moderate" if same_label_n == 1 else "Limited"

    enrichment_count = 0
    for field in ["critic_score", "cases_produced", "previous_msrp"]:
        if target.get(field) not in (None, "") and not pd.isna(target.get(field)):
            enrichment_count += 1
    enrichment_score = min(10, enrichment_count * 3 + (2 if _bool(target.get("estate")) or _bool(target.get("single_vineyard")) else 0))
    enrichment_label = "Strong" if enrichment_score >= 8 else "Moderate" if enrichment_score >= 4 else "Limited"

    context_score = 6 if context is not None and not context.empty else 0
    context_label = "Available" if context_score else "Not loaded"

    score = min(96, 10 + coverage_score + cat_score + tier_score + history_score + enrichment_score + context_score)
    label = "High" if score >= 80 else "Moderate" if score >= 58 else "Low"
    breakdown = {
        "Comparable coverage": coverage_label,
        "Category match": cat_label,
        "Tier match": tier_label,
        "Same-label history": history_label,
        "Wine-specific enrichment": enrichment_label,
        "Public market context": context_label,
    }
    if exact_cat < .5:
        notes.append("The comparable set required a meaningful number of adjacent-category observations.")
    if exact_tier < .35:
        notes.append("Product-tier coverage is still thin for this target.")
    return label, int(score), breakdown, notes


def analyze_wine(df: pd.DataFrame, target: Dict, context: pd.DataFrame | None = None) -> Dict:
    comps = select_comps(df, target)
    if comps.empty:
        raise ValueError("No usable comparable wines were found. Add more comp data or broaden the target category.")

    vals = comps["price"].to_numpy(float)
    w = comps["similarity_weight"].to_numpy(float)
    q25 = weighted_quantile(vals, w, .25)
    med = weighted_quantile(vals, w, .50)
    q75 = weighted_quantile(vals, w, .75)
    mean = float(np.average(vals, weights=w))
    market_base = 0.74 * med + 0.26 * mean

    attr_factor, upward, downward = _attribute_factor(target)
    context_factor, context_notes = _market_context_factor(context, _clean_text(target.get("general_category") or "Red"))
    adjusted = market_base * attr_factor * context_factor

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
        anchor = float(previous) * (1.02 ** years)
        adjusted = 0.66 * adjusted + 0.34 * anchor
        upward.append("Prior-vintage MSRP is used as a stabilizing brand-history anchor rather than allowing comps alone to reset the label's position.")

    volume_raw = min(adjusted * 0.90, max(q25 * attr_factor * context_factor, adjusted * 0.84))
    premium_raw = max(adjusted * 1.16, min(q75 * attr_factor * context_factor, adjusted * 1.22))

    cogs = target.get("cogs")
    if cogs not in (None, "") and not pd.isna(cogs):
        cogs = float(cogs)
        floor = cogs / 0.55 if cogs > 0 else 0
        if volume_raw < floor:
            volume_raw = floor
            downward.append("The volume-oriented strategy is constrained by entered COGS to avoid an extremely weak DTC gross margin.")

    volume = _round_price(volume_raw)
    market = _round_price(max(adjusted, volume + 1))
    premium = _round_price(max(premium_raw, market + (5 if market >= 50 else 3)))
    if volume >= market:
        volume = _round_price(market * .92)
    if premium <= market:
        premium = _round_price(market * 1.12)

    label, conf_score, conf_breakdown, conf_notes = _confidence(target, comps, context)

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
    for name, price, positioning in [
        ("Volume-Oriented", volume, "More accessible positioning / greater sell-through emphasis"),
        ("Market-Aligned", market, "Central comparable-market position"),
        ("Premium Positioning", premium, "Higher-end positioning / requires stronger market support"),
    ]:
        realized, margin = economics(price)
        scenarios.append({
            "strategy": name,
            "msrp": price,
            "positioning": positioning,
            "estimated_net_revenue_per_bottle": realized,
            "gross_margin_pct": margin,
        })

    return {
        "market_base": market_base,
        "market_range_low": _round_price(q25 * attr_factor * context_factor),
        "market_range_high": _round_price(q75 * attr_factor * context_factor),
        "attribute_factor": attr_factor,
        "context_factor": context_factor,
        "context_notes": context_notes,
        "scenarios": scenarios,
        "confidence_label": label,
        "confidence_score": conf_score,
        "confidence_breakdown": conf_breakdown,
        "confidence_notes": conf_notes,
        "upward_drivers": upward,
        "downward_drivers": downward,
        "comps": comps,
    }
