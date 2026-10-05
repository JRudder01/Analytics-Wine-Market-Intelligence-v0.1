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
    assert o.wine == "Cabernet Sauvignon Nº2 — 2023"
    assert o.vintage == "2023"
    assert o.regular_price == 70.0
    assert o.varietal == "Cabernet Sauvignon"
    assert o.graph_category == "Cabernet Sauvignon"
    assert o.general_category == "Red"
    assert o.region == "Napa Valley"
    assert o.subregion == "Oak Knoll District"
    assert o.alcohol_pct == 14.3
    assert o.cases_produced == 1278
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
    assert o.graph_category == "Pinot Noir"
    assert o.general_category == "Red"
    assert o.region == "San Luis Obispo Coast"
    assert o.single_vineyard is True
    assert o.cases_produced == 36
    assert o.product_tier == "Limited"
