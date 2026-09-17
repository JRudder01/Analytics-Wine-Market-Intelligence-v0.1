from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data_loader import load_comps, load_public_context
from pricing_engine import analyze_wine


def run():
    comps = load_comps()
    context = load_public_context()
    assert len(comps) >= 120, len(comps)
    assert comps["winery"].nunique() >= 5

    target = {
        "winery": "Eberle",
        "wine": "Vineyard Selection Cabernet Sauvignon",
        "vintage": 2023,
        "graph_category": "Cabernet Sauvignon",
        "general_category": "Red",
        "region": "Paso Robles",
        "subregion": "",
        "product_tier": "Core",
        "critic_score": 91,
        "cases_produced": None,
        "estate": False,
        "single_vineyard": False,
        "analysis_mode": "Historical backtest",
        "channel": "DTC",
        "dtc_share": 1.0,
        "wholesale_net_pct": .5,
    }
    result = analyze_wine(comps, target, context)
    assert len(result["comps"]) >= 6
    assert all(result["comps"]["vintage"].isna() | (result["comps"]["vintage"] <= 2023))
    prices = [s["msrp"] for s in result["scenarios"]]
    assert prices[0] < prices[1] < prices[2], prices
    print("observations", len(comps))
    print("wineries", comps["winery"].nunique())
    print("Eberle backtest scenarios", prices)
    print("confidence", result["confidence_label"], result["confidence_score"])
    print(result["comps"][["winery", "wine", "vintage", "price", "product_tier", "comp_reason", "similarity_weight"]].head(10).to_string(index=False))


if __name__ == "__main__":
    run()
