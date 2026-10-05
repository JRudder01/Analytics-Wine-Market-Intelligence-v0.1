import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from catalog_scraper import _extract_product_page_offers


def test_ashes_diamonds_cabernet_metadata():
    html = """
    <html><body>
    <h1>Cabernet Sauvignon Nº2 — 2023</h1>
    <h4>Napa Valley</h4>
    <p>A Cabernet Sauvignon blend of select vineyards in Napa Valley (Oak Knoll District).</p>
    <div>Technical Data</div>
    <div>Alcohol</div><div>14.3</div>
    <div>Cases Produced</div><div>1278</div>
    <div>$70</div><a>Buy</a>
    </body></html>
    """
    offers = _extract_product_page_offers(html, "https://example.com/shop/cabernet-2023")
    assert len(offers) == 1
    o = offers[0]
    assert o.wine == "Cabernet Sauvignon Nº2"
    assert o.vintage == "2023"
    assert o.regular_price == 70.0
    assert o.varietal == "Cabernet Sauvignon"
    assert o.graph_category == "Cabernet Sauvignon"
    assert o.general_category == "Red"
    assert o.region == "Napa Valley"
    assert o.subregion == "Oak Knoll District"
    assert o.alcohol_pct == 14.3
    assert o.cases_produced == 1278
    assert o.single_vineyard is False
    assert o.product_tier == "Core"
    assert o.availability_status == "Available"


def test_limited_small_production_and_single_vineyard():
    html = """
    <html><body>
    <h1>Pinot Noir — 2024</h1>
    <p>San Luis Obispo Coast AVA. Single-vineyard Pinot Noir from La Montañita Vineyard.</p>
    <p>Only 36 cases produced. Alcohol 13.9%. $45</p>
    </body></html>
    """
    offers = _extract_product_page_offers(html, "https://example.com/shop/pinot-2024")
    o = offers[0]
    assert o.wine == "Pinot Noir"
    assert o.graph_category == "Pinot Noir"
    assert o.general_category == "Red"
    assert o.region == "San Luis Obispo Coast"
    assert o.single_vineyard is True
    assert o.cases_produced == 36
    assert o.product_tier == "Limited"


def test_blanc_prose_blend_and_multiple_subregions():
    html = """
    <html><body>
    <h1>Blanc Nº9 — 2023</h1>
    <p>Napa Valley. Blanc is a blend of Sémillon and Sauvignon Blanc from vineyards in
    Oak Knoll District and Yountville.</p>
    <p>Alcohol 13.0%. 2,400 cases produced. $45. Add to cart.</p>
    </body></html>
    """
    offers = _extract_product_page_offers(html, "https://example.com/shop/blanc-2023-9")
    o = offers[0]
    assert o.wine == "Blanc Nº9"
    assert o.vintage == "2023"
    assert o.varietal == "Sauvignon Blanc, Sémillon" or o.varietal == "Sémillon, Sauvignon Blanc"
    assert o.graph_category == "White Blend"
    assert o.general_category == "White"
    assert o.region == "Napa Valley"
    assert o.subregion == ""
    assert o.single_vineyard is False
    assert o.cases_produced == 2400
    assert o.alcohol_pct == 13.0


def test_plural_vineyard_language_overrides_generic_single_vineyard_phrase():
    html = """
    <html><body>
    <h1>Chardonnay Nº4 — 2025</h1>
    <p>Our single-vineyard program celebrates Napa Valley. This Chardonnay is sourced
    from select vineyards in Napa Valley.</p>
    <p>Alcohol 12.4%. 390 cases produced. Member exclusive. $50.</p>
    </body></html>
    """
    offers = _extract_product_page_offers(html, "https://example.com/shop/2025-chardonnay")
    o = offers[0]
    assert o.wine == "Chardonnay Nº4"
    assert o.single_vineyard is False
    assert o.availability_status == "Member exclusive"
