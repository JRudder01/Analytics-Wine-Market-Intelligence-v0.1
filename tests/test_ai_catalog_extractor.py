import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_catalog_extractor import validate_ai_catalog_result


def _base_result():
    fields = [
        "wine", "vintage", "regular_price", "sale_price", "club_price", "varietal",
        "region", "subregion", "alcohol_pct", "cases_produced", "bottle_size_ml",
        "wine_style", "estate_status", "single_vineyard_status", "product_tier", "availability_status",
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
        "bottle_size_ml": None,
        "wine_style": None,
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



def test_validator_keeps_explicit_bottle_size_and_late_harvest_style():
    row = _base_result()
    row.update({
        "wine": "Twilight Late Harvest Viognier",
        "vintage": 2018,
        "regular_price": 34,
        "varietal": "Viognier",
        "graph_category": "Viognier",
        "general_category": "Dessert",
        "bottle_size_ml": 375,
        "wine_style": "Late Harvest",
    })
    row["evidence"].update({
        "wine": "2018 Twilight Late Harvest Viognier",
        "vintage": "2018",
        "regular_price": "$34",
        "varietal": "Viognier",
        "bottle_size_ml": "375 mL",
        "wine_style": "Late Harvest Viognier",
    })
    out = validate_ai_catalog_result(row)
    assert out["bottle_size_ml"] == 375
    assert out["wine_style"] == "Late Harvest"


def test_estate_tier_with_explicit_estate_evidence_repairs_boolean_status():
    row = _base_result()
    row.update({
        "wine": "Five Sisters Cabernet Sauvignon",
        "product_tier": "Estate",
        "estate_status": "No",
    })
    row["evidence"].update({
        "wine": "Estate Five Sisters Blend Cabernet Sauvignon",
        "vintage": "2023",
        "regular_price": "$49",
        "varietal": "Cabernet Sauvignon",
        "product_tier": "Estate Five Sisters Blend",
    })
    out = validate_ai_catalog_result(row)
    assert out["product_tier"] == "Estate"
    assert out["estate_status"] == "Yes"
    assert "Estate" in out["evidence"]["estate_status"]


def test_ai_merge_preserves_bottle_size_style_and_estate_consistency():
    from catalog_scraper import WineOffer, merge_ai_product_result
    legacy = WineOffer(
        wine="2018 Twilight Late Harvest Viognier", vintage="2018", regular_price=34.0,
        sale_price=None, club_price=None, currency="USD",
        product_url="https://legacy.example.com/twilight", evidence="legacy page",
        extraction_method="Selected product page fallback", confidence="Moderate",
    )
    ai = {
        "wine": "Twilight Late Harvest Viognier", "vintage": 2018,
        "regular_price": 34.0, "sale_price": None, "club_price": None,
        "currency": "USD", "varietal": "Viognier", "graph_category": "Viognier",
        "general_category": "Dessert", "region": "Dry Creek Valley", "subregion": "Sea Rose Ranch",
        "alcohol_pct": None, "cases_produced": None, "bottle_size_ml": 375,
        "wine_style": "Late Harvest", "estate_status": "Unknown",
        "single_vineyard_status": "Unknown", "product_tier": "Core",
        "availability_status": None, "overall_confidence": "Moderate",
        "evidence": {
            "wine": "2018 Twilight Late Harvest Viognier", "vintage": "2018", "regular_price": "$34",
            "sale_price": None, "club_price": None, "varietal": "Viognier",
            "region": "Dry Creek Valley", "subregion": "Sea Rose Ranch", "alcohol_pct": None,
            "cases_produced": None, "bottle_size_ml": "375 mL", "wine_style": "Late Harvest",
            "estate_status": None, "single_vineyard_status": None, "product_tier": None,
            "availability_status": None,
        },
        "warnings": [],
    }
    out = merge_ai_product_result([legacy], ai, legacy.product_url)[0]
    assert out.bottle_size_ml == 375
    assert out.wine_style == "Late Harvest"
    assert out.general_category == "Dessert"
