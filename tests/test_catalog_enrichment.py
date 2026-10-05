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


def test_explicit_appellation_does_not_override_multiple_subregions():
    html = """
    <html><body>
    <h1>Blanc Nº9 — 2023</h1>
    <div>Appellation: Yountville</div>
    <p>Napa Valley. This Blanc blends Sémillon and Sauvignon Blanc sourced from
    vineyards in Oak Knoll District and Yountville.</p>
    <p>Alcohol 13.0%. 2,400 cases produced. $45. Add to cart.</p>
    </body></html>
    """
    offers = _extract_product_page_offers(html, "https://example.com/shop/blanc-2023-9")
    o = offers[0]
    assert o.region == "Napa Valley"
    assert o.subregion == ""
    assert o.confidence == "Moderate"


def test_repeating_static_catalog_blocks_without_product_links():
    from catalog_scraper import extract_catalog_offers
    html = """
    <html><body>
      <main>
        <div class="listing-row">
          <h3>2021 Malbec</h3>
          <div>915 Lincoln / California</div>
          <div>Paso Robles, El Pomar District</div>
          <div>100% Malbec</div>
          <div>14.86% ABV</div>
          <div>$45.00 / 750 mL bottle</div>
        </div>
        <div class="listing-row">
          <h3>2023 Grenache Blanc</h3>
          <div>915 Lincoln / California</div>
          <div>Paso Robles, El Pomar District</div>
          <div>100% Grenache Blanc</div>
          <div>14% ABV</div>
          <div>$40.00 / 750 mL bottle</div>
        </div>
        <div class="listing-row">
          <h3>2021 Cabernet Sauvignon</h3>
          <div>915 Lincoln / California</div>
          <div>Paso Robles, El Pomar District</div>
          <div>15.58% ABV</div>
          <div>$50.00 / 750 mL bottle</div>
        </div>
      </main>
    </body></html>
    """
    offers = extract_catalog_offers(html, "https://example.com/shop/915_lincoln")
    by_name = {o.wine: o for o in offers}
    assert set(by_name) >= {"Malbec", "Grenache Blanc", "Cabernet Sauvignon"}
    assert by_name["Malbec"].vintage == "2021"
    assert by_name["Malbec"].regular_price == 45.0
    assert by_name["Malbec"].alcohol_pct == 14.86
    assert by_name["Malbec"].varietal in {"Malbec", "100% Malbec"}
    assert by_name["Malbec"].region == "Paso Robles"
    assert by_name["Malbec"].subregion == "El Pomar District"
    assert by_name["Grenache Blanc"].regular_price == 40.0
    assert by_name["Grenache Blanc"].general_category == "White"
    assert by_name["Cabernet Sauvignon"].regular_price == 50.0
    assert all(o.product_url == "https://example.com/shop/915_lincoln" for o in by_name.values())


def test_repeating_static_catalog_sale_price_and_member_status():
    from catalog_scraper import extract_catalog_offers
    html = """
    <html><body>
      <div class="wine-card">
        <h3>2018 Cabernet Sauvignon</h3>
        <p>Members Only</p>
        <p>15.2% ABV</p>
        <p><s>$60.00</s> $48.00 / 750 mL bottle</p>
      </div>
    </body></html>
    """
    offers = extract_catalog_offers(html, "https://example.com/catalog")
    assert len(offers) == 1
    o = offers[0]
    assert o.wine == "Cabernet Sauvignon"
    assert o.vintage == "2018"
    assert o.regular_price == 60.0
    assert o.sale_price == 48.0
    assert o.availability_status == "Member exclusive"


def test_vinoshipper_producer_id_detection():
    from catalog_scraper import infer_vinoshipper_producer_id
    html = '''<script>window.top.Vinoshipper.init(4112, {theme: "light"});</script>'''
    assert infer_vinoshipper_producer_id(html, "https://vinoshipper.com/shop/915_lincoln") == "4112"


def test_vinoshipper_feed_conversion():
    from catalog_scraper import extract_vinoshipper_feed_offers
    payload = {
        "products": [
            {
                "id": 1001,
                "name": "2021 Cabernet Sauvignon",
                "vintage": 2021,
                "consumerPrice": 50,
                "varietal": "Cabernet Sauvignon",
                "appellation": "Paso Robles, El Pomar District",
                "alcoholLevel": 15.58,
                "description": "Paso Robles Cabernet Sauvignon from El Pomar District.",
            },
            {
                "id": 1002,
                "name": "2023 Grenache Blanc",
                "consumerPrice": 40,
                "varietal": "Grenache Blanc",
                "appellation": "Paso Robles, El Pomar District",
                "alcoholLevel": 14.0,
            },
        ]
    }
    offers = extract_vinoshipper_feed_offers(
        payload,
        producer_id="4112",
        shop_url="https://vinoshipper.com/shop/915_lincoln",
    )
    by_name = {o.wine: o for o in offers}
    assert by_name["Cabernet Sauvignon"].vintage == "2021"
    assert by_name["Cabernet Sauvignon"].regular_price == 50.0
    assert by_name["Cabernet Sauvignon"].region == "Paso Robles"
    assert by_name["Cabernet Sauvignon"].subregion == "El Pomar District"
    assert by_name["Cabernet Sauvignon"].alcohol_pct == 15.58
    assert by_name["Grenache Blanc"].regular_price == 40.0
    assert by_name["Grenache Blanc"].general_category == "White"


def test_vinoshipper_nested_vintage_and_varietal_metadata():
    from catalog_scraper import extract_vinoshipper_feed_offers
    payload = {
        "products": [{
            "id": 2001,
            "name": "Better Together",
            "consumerPrice": 48,
            "metadata": {
                "vintage": {"year": 2021},
                "varietal": {"name": "Zinfandel"},
                "appellation": {"name": "Paso Robles"},
            },
        }]
    }
    offers = extract_vinoshipper_feed_offers(
        payload, producer_id="4112", shop_url="https://vinoshipper.com/shop/915_lincoln"
    )
    assert len(offers) == 1
    o = offers[0]
    assert o.wine == "Better Together"
    assert o.vintage == "2021"
    assert o.varietal == "85% Zinfandel, 15% Petite Sirah"
    assert o.graph_category == "Zinfandel"
    assert o.general_category == "Red"
    assert o.confidence == "High"


def test_vinoshipper_title_blend_overrides_single_provider_varietal():
    from catalog_scraper import extract_vinoshipper_feed_offers
    payload = {
        "products": [{
            "id": 2002,
            "name": "Cabernet and Merlot Blend",
            "consumerPrice": 60,
            "vintageYear": 2021,
            "varietal": "Merlot",
            "appellation": "San Luis Obispo County",
        }]
    }
    o = extract_vinoshipper_feed_offers(
        payload, producer_id="4112", shop_url="https://vinoshipper.com/shop/915_lincoln"
    )[0]
    assert o.vintage == "2021"
    assert "Cabernet Sauvignon" in o.varietal
    assert "Merlot" in o.varietal
    assert o.graph_category == "Bordeaux Blend"


def test_vinoshipper_explicit_composition_overrides_provider_single_varietal():
    from catalog_scraper import extract_vinoshipper_feed_offers
    payload = {
        "products": [{
            "id": 2003,
            "name": "Distinctive",
            "consumerPrice": 49,
            "vintage": 2022,
            "varietal": "Cabernet Sauvignon",
            "description": "50% Cabernet Sauvignon, 50% Petite Sirah. Paso Robles red blend.",
            "appellation": "Paso Robles",
        }]
    }
    o = extract_vinoshipper_feed_offers(
        payload, producer_id="4112", shop_url="https://vinoshipper.com/shop/915_lincoln"
    )[0]
    assert o.vintage == "2022"
    assert "50% Cabernet Sauvignon" in o.varietal
    assert "50% Petite Sirah" in o.varietal
    assert o.graph_category == "Red Blend"


def test_vinoshipper_rhone_title_and_spelling_aliases():
    from catalog_scraper import extract_vinoshipper_feed_offers
    payload = {
        "products": [
            {"id": 2004, "name": "Le Rhone", "consumerPrice": 56, "vintage": 2021, "appellation": "Paso Robles"},
            {"id": 2005, "name": "Pino Noir", "consumerPrice": 58, "vintage": 2023, "appellation": "San Luis Obispo Coast"},
            {"id": 2006, "name": "Petite Verdot", "consumerPrice": 55, "vintage": 2022, "appellation": "Paso Robles"},
        ]
    }
    offers = extract_vinoshipper_feed_offers(
        payload, producer_id="4112", shop_url="https://vinoshipper.com/shop/915_lincoln"
    )
    by_name = {o.wine: o for o in offers}
    assert by_name["Le Rhone"].graph_category == "Rhône Blend"
    assert by_name["Pinot Noir"].graph_category == "Pinot Noir"
    assert by_name["Petit Verdot"].graph_category == "Petit Verdot"


def test_vinoshipper_missing_vintage_caps_confidence():
    from catalog_scraper import extract_vinoshipper_feed_offers
    payload = {"products": [{"id": 2007, "name": "Merlot", "consumerPrice": 75, "varietal": "Merlot"}]}
    o = extract_vinoshipper_feed_offers(
        payload, producer_id="4112", shop_url="https://vinoshipper.com/shop/915_lincoln"
    )[0]
    assert o.vintage == ""
    assert o.confidence == "Moderate"


def test_vinoshipper_labeled_metadata_abv_and_geography_normalization():
    from catalog_scraper import extract_vinoshipper_feed_offers
    payload = {
        "products": [{
            "id": 3001,
            "name": "2023 Tannat",
            "consumerPrice": 56,
            "vintage": 2023,
            "varietal": "Tannat",
            "appellation": "CA - Monterey County - San Antonio Valley",
            "metadata": [
                {"label": "Alcohol Level", "value": "15.9%"},
            ],
        }]
    }
    o = extract_vinoshipper_feed_offers(
        payload, producer_id="9999", shop_url="https://vinoshipper.com/shop/example"
    )[0]
    assert o.alcohol_pct == 15.9
    assert o.region == "San Antonio Valley"


def test_vinoshipper_gsm_expands_to_grapes():
    from catalog_scraper import extract_vinoshipper_feed_offers
    payload = {"products": [{
        "id": 3002,
        "name": "2023 Le Rhone",
        "consumerPrice": 62,
        "vintage": 2023,
        "varietal": "GSM",
        "appellation": "Paso Robles",
    }]}
    o = extract_vinoshipper_feed_offers(
        payload, producer_id="9999", shop_url="https://vinoshipper.com/shop/example"
    )[0]
    assert o.varietal == "Grenache, Syrah, Mourvèdre"
    assert o.graph_category == "Rhône Blend"


def test_915_lincoln_verified_distinctive_trois_and_le_rhone_overrides():
    from catalog_scraper import extract_vinoshipper_feed_offers
    payload = {"products": [
        {"id": 4001, "name": "Distinctive", "consumerPrice": 49, "vintage": 2022,
         "varietal": "Cabernet Sauvignon", "appellation": "Paso Robles"},
        {"id": 4002, "name": "Distinctive", "consumerPrice": 56, "vintage": 2023,
         "varietal": "Distinvtive", "appellation": "Paso Robles"},
        {"id": 4003, "name": "Trois", "consumerPrice": 47, "vintage": 2021,
         "varietal": "Malbec", "appellation": "Paso Robles"},
        {"id": 4004, "name": "Le Rhone", "consumerPrice": 56, "vintage": 2021,
         "varietal": "Mourvèdre", "appellation": "Paso Robles"},
    ]}
    offers = extract_vinoshipper_feed_offers(
        payload, producer_id="4112", shop_url="https://vinoshipper.com/shop/915_lincoln"
    )
    by_key = {(o.wine, o.vintage): o for o in offers}
    d22 = by_key[("Distinctive", "2022")]
    assert d22.varietal == "50% Cabernet Sauvignon, 50% Petite Sirah"
    assert d22.graph_category == "Red Blend"
    assert d22.alcohol_pct == 15.3
    d23 = by_key[("Distinctive", "2023")]
    assert d23.varietal == ""
    assert d23.graph_category == "Red Blend"
    assert d23.alcohol_pct == 15.4
    trois = by_key[("Trois", "2021")]
    assert trois.varietal == "69% Malbec, 17% Petit Verdot, 14% Cabernet Sauvignon"
    assert trois.graph_category == "Bordeaux Blend"
    assert trois.alcohol_pct == 15.3
    lr = by_key[("Le Rhone", "2021")]
    assert lr.varietal == "67% Mourvèdre, 33% Grenache"
    assert lr.graph_category == "Rhône Blend"
    assert lr.alcohol_pct == 14.4


def test_915_lincoln_public_catalog_abv_fallbacks():
    from catalog_scraper import extract_vinoshipper_feed_offers
    payload = {"products": [
        {"id": 5001, "name": "2019 Merlot", "consumerPrice": 75, "vintage": 2019, "varietal": "Merlot", "appellation": "Paso Robles"},
        {"id": 5002, "name": "2023 Pino Noir", "consumerPrice": 58, "vintage": 2023, "varietal": "Pino Noir", "appellation": "San Luis Obispo Coast"},
        {"id": 5003, "name": "2021 Cabernet Sauvignon", "consumerPrice": 50, "vintage": 2021, "varietal": "Cabernet Sauvignon", "appellation": "Paso Robles, El Pomar District"},
    ]}
    offers = extract_vinoshipper_feed_offers(
        payload, producer_id="4112", shop_url="https://vinoshipper.com/shop/915_lincoln"
    )
    by_name = {o.wine: o for o in offers}
    assert by_name["Merlot"].alcohol_pct == 14.95
    assert by_name["Pinot Noir"].alcohol_pct == 14.54
    assert by_name["Cabernet Sauvignon"].alcohol_pct == 15.58
