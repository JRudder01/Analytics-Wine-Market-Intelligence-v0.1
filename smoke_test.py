from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data_loader import load_seed
from pricing_engine import analyze_wine

seed = load_seed()
target = {
    "winery": "Eberle",
    "wine": "Vineyard Selection Cabernet Sauvignon",
    "vintage": 2023,
    "varietal": "Cabernet Sauvignon",
    "graph_category": "Cabernet Sauvignon",
    "general_category": "Red",
    "region": "Paso Robles",
    "product_tier": "Core",
    "critic_score": 91,
    "cases_produced": 7092,
    "estate": False,
    "single_vineyard": False,
    "channel": "DTC",
}
result = analyze_wine(seed, target)
assert len(result["comps"]) >= 3
assert result["scenarios"][0]["msrp"] < result["scenarios"][1]["msrp"] < result["scenarios"][2]["msrp"]
print("Smoke test passed")
print(result["confidence_label"], result["confidence_score"])
print(result["scenarios"])
print(result["comps"][["winery", "wine", "vintage", "price", "similarity_weight"]].head(8).to_string(index=False))
