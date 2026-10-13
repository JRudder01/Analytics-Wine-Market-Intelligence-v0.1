import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_catalog_extractor import validate_ai_catalog_result


def _base_result():
    fields = [
        "wine", "vintage", "regular_price", "sale_price", "club_price", "varietal",
        "region", "subregion", "alcohol_pct", "cases_produced", "estate_status",
        "single_vineyard_status", "product_tier", "availability_status",
    ]
    return {
        "wine": "2023 Cabernet Sauvignon",
        "vintage": 2023,
        "regular_price": 50,
        "sale_price": None,
        "club_price": None,
        "currency": "USD",
        "varietal": "Cabernet Sauvignon",
        "graph_category": "Cabernet Sauvignon",
        "general_category": "Red",
        "region": "Paso Robles",
        "subregion": None,
        "alcohol_pct": 14.5,
        "cases_produced": 500,
        "estate_status": "Unknown",
        "single_vineyard_status": "Unknown",
        "product_tier": "Core",
        "availability_status": None,
        "overall_confidence": "High",
        "evidence": {k: None for k in fields},
        "warnings": [],
    }


def test_validator_drops_non_null_facts_without_evidence():
    row = _base_result()
    out = validate_ai_catalog_result(row)
    assert out["wine"] is None
    assert out["regular_price"] is None
    assert out["varietal"] is None
    assert out["region"] is None
    assert out["alcohol_pct"] is None
    assert out["graph_category"] == "Cabernet Sauvignon"  # derived classification can remain


def test_validator_keeps_evidenced_facts_and_bounds_numbers():
    row = _base_result()
    row["evidence"].update({
        "wine": "2023 Cabernet Sauvignon",
        "vintage": "Vintage 2023",
        "regular_price": "$50",
        "varietal": "Cabernet Sauvignon",
        "region": "Paso Robles",
        "alcohol_pct": "14.5% ABV",
        "cases_produced": "500 cases",
    })
    out = validate_ai_catalog_result(row)
    assert out["wine"] == "2023 Cabernet Sauvignon"
    assert out["vintage"] == 2023
    assert out["regular_price"] == 50.0
    assert out["alcohol_pct"] == 14.5
    assert out["cases_produced"] == 500

    row["alcohol_pct"] = 99
    row["vintage"] = 1800
    out = validate_ai_catalog_result(row)
    assert out["alcohol_pct"] is None
    assert out["vintage"] is None


def test_unknown_estate_and_single_vineyard_do_not_become_true():
    row = _base_result()
    row["evidence"].update({
        "wine": "Cabernet Sauvignon", "vintage": "2023", "regular_price": "$50",
        "varietal": "Cabernet Sauvignon", "region": "Paso Robles",
        "alcohol_pct": "14.5", "cases_produced": "500",
    })
    out = validate_ai_catalog_result(row)
    assert out["estate_status"] == "Unknown"
    assert out["single_vineyard_status"] == "Unknown"
