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


def test_vinoshipper_final_normalizer_matches_observed_915_export_shape():
    from catalog_scraper import WineOffer, finalize_vinoshipper_offers

    raw = [
        WineOffer("Better Together", "2021", 48, None, None, "USD", "https://vinoshipper.com/shop/915_lincoln/better_together_163766", "", "VinoShipper Product Feed", "High", varietal="Zinfandel", graph_category="Zinfandel", general_category="Red", region="Paso Robles", provider_id="4112"),
        WineOffer("Cabernet and Merlot Blend", "2018", 60, None, None, "USD", "https://vinoshipper.com/shop/915_lincoln/cabernet_and_merlot_blend_92163", "", "VinoShipper Product Feed", "High", varietal="Cabernet Sauvignon, Merlot", graph_category="Bordeaux Blend", general_category="Red", region="CA - San Luis Obispo County (Central Coast)", provider_id="4112"),
        WineOffer("Distinctive", "2022", 49, None, None, "USD", "https://vinoshipper.com/shop/915_lincoln/distinctive_163765", "", "VinoShipper Product Feed", "High", varietal="Cabernet Sauvignon", graph_category="Cabernet Sauvignon", general_category="Red", region="Paso Robles", provider_id="4112"),
        WineOffer("Distinctive", "2023", 56, None, None, "USD", "https://vinoshipper.com/shop/915_lincoln/distinctive_194910", "", "VinoShipper Product Feed", "Moderate", varietal="Distinvtive", graph_category="Other", general_category="Red", region="Paso Robles", provider_id="4112"),
        WineOffer("Le Rhone", "2021", 56, None, None, "USD", "https://vinoshipper.com/shop/915_lincoln/le_rhone_132861", "", "VinoShipper Product Feed", "High", varietal="Mourvèdre", graph_category="Rhône Blend", general_category="Red", region="Paso Robles", provider_id="4112"),
        WineOffer("Le Rhone", "2023", 62, None, None, "USD", "https://vinoshipper.com/shop/915_lincoln/le_rhone_181952", "", "VinoShipper Product Feed", "High", varietal="GSM", graph_category="Rhône Blend", general_category="Red", region="Paso Robles", provider_id="4112"),
        WineOffer("Pinot Noir", "2023", 58, None, None, "USD", "https://vinoshipper.com/shop/915_lincoln/pino_noir_167931", "", "VinoShipper Product Feed", "High", varietal="Pinot Noir", graph_category="Pinot Noir", general_category="Red", region="San Luis Obispo Coast", provider_id="4112"),
        WineOffer("Tannat", "2023", 56, None, None, "USD", "https://vinoshipper.com/shop/915_lincoln/tannat_194897", "", "VinoShipper Product Feed", "High", varietal="Tannat", graph_category="Tannat", general_category="Red", region="CA - Monterey County - San Antonio Valley", provider_id="4112"),
        WineOffer("Trois", "2021", 47, None, None, "USD", "https://vinoshipper.com/shop/915_lincoln/trois_136674", "", "VinoShipper Product Feed", "High", varietal="Malbec", graph_category="Malbec", general_category="Red", region="Paso Robles", provider_id="4112"),
    ]
    rows = finalize_vinoshipper_offers(raw, "4112")
    by_key = {(o.wine, o.vintage): o for o in rows}

    assert by_key[("Better Together", "2021")].alcohol_pct == 15.34
    assert "Zinfandel" in by_key[("Better Together", "2021")].varietal

    cab_merlot = by_key[("Cabernet and Merlot Blend", "2018")]
    assert cab_merlot.graph_category == "Bordeaux Blend"
    assert cab_merlot.region == "San Luis Obispo County"
    assert cab_merlot.alcohol_pct == 13.65

    d22 = by_key[("Distinctive", "2022")]
    assert d22.graph_category == "Red Blend"
    assert "50% Cabernet Sauvignon" in d22.varietal
    assert "50% Petite Sirah" in d22.varietal
    assert d22.alcohol_pct == 15.3

    d23 = by_key[("Distinctive", "2023")]
    assert d23.graph_category == "Red Blend"
    assert d23.varietal == ""
    assert d23.alcohol_pct == 15.4
    assert d23.confidence == "Moderate"

    rhone21 = by_key[("Le Rhone", "2021")]
    assert rhone21.graph_category == "Rhône Blend"
    assert "67% Mourvèdre" in rhone21.varietal
    assert "33% Grenache" in rhone21.varietal
    assert rhone21.alcohol_pct == 14.4

    rhone23 = by_key[("Le Rhone", "2023")]
    assert rhone23.graph_category == "Rhône Blend"
    assert "38% Grenache" in rhone23.varietal
    assert "32% Syrah" in rhone23.varietal
    assert "30% Mourvèdre" in rhone23.varietal
    assert rhone23.alcohol_pct == 15.1

    tannat = by_key[("Tannat", "2023")]
    assert tannat.region == "San Antonio Valley"
    assert tannat.alcohol_pct == 15.9

    trois = by_key[("Trois", "2021")]
    assert trois.graph_category == "Bordeaux Blend"
    assert "69% Malbec" in trois.varietal
    assert "17% Petit Verdot" in trois.varietal
    assert "14% Cabernet Sauvignon" in trois.varietal
    assert trois.alcohol_pct == 15.3


def test_vinoshipper_finalizer_runs_idempotently():
    from catalog_scraper import WineOffer, finalize_vinoshipper_offers
    offer = WineOffer(
        "Le Rhone", "2023", 62, None, None, "USD",
        "https://vinoshipper.com/shop/915_lincoln/le_rhone_181952", "", "VinoShipper Product Feed", "High",
        varietal="GSM", graph_category="Rhône Blend", general_category="Red", region="Paso Robles", provider_id="4112"
    )
    once = finalize_vinoshipper_offers([offer], "4112")
    twice = finalize_vinoshipper_offers(once, "4112")
    assert once[0].to_dict() == twice[0].to_dict()


def test_finalize_vinoshipper_offer_dicts_upgrades_stale_session_rows():
    from catalog_scraper import finalize_vinoshipper_offer_dicts

    stale = [{
        "wine": "Distinctive",
        "vintage": "2022",
        "regular_price": 49.0,
        "sale_price": None,
        "club_price": None,
        "currency": "USD",
        "product_url": "https://vinoshipper.com/shop/915_lincoln/distinctive_163765",
        "evidence": "",
        "extraction_method": "VinoShipper Product Feed",
        "confidence": "High",
        "varietal": "Cabernet Sauvignon",
        "graph_category": "Cabernet Sauvignon",
        "general_category": "Red",
        "region": "Paso Robles",
        "subregion": "",
        "alcohol_pct": None,
        "cases_produced": None,
        "estate": False,
        "single_vineyard": False,
        "product_tier": "Core",
        "availability_status": "Available",
    }]
    upgraded = finalize_vinoshipper_offer_dicts(stale, "4112")
    assert len(upgraded) == 1
    row = upgraded[0]
    assert row["varietal"] == "50% Cabernet Sauvignon, 50% Petite Sirah"
    assert row["graph_category"] == "Red Blend"
    assert row["alcohol_pct"] == 15.3
    assert row["provider_id"] == "4112"


def test_compact_markup_multiple_napa_subregions_stays_broad_only():
    """Collapsed template text like OakKnoll/NapaValley must still trigger conflict."""
    html = """
    <html><body>
      <h1>Blanc №9 — 2023</h1>
      <h4>NapaValley</h4>
      <p>A blend of Sémillon and Sauvignon Blanc from vineyards in NapaValley
      (OakKnoll District and Yountville).</p>
      <p>Alcohol 13%. Cases Produced 2400. $45. Buy</p>
    </body></html>
    """
    o = _extract_product_page_offers(html, "https://example.com/shop/blanc-2023-9")[0]
    assert o.region == "Napa Valley"
    assert o.subregion == ""
    assert o.confidence == "Moderate"


def test_santa_cruz_mountains_is_preserved_as_region():
    html = """
    <html><body>
      <h1>Mountain Cuvée №6 — 2023</h1>
      <h4>Bates Ranch</h4><h4>Santa Cruz Mountains</h4>
      <p>A blend of Cabernet Sauvignon and Cabernet Franc from Bates Ranch in the Santa Cruz Mountains.</p>
      <p>Alcohol 13.9%. Cases Produced 594. $105. Buy</p>
    </body></html>
    """
    o = _extract_product_page_offers(html, "https://example.com/shop/mountain-cuvee-2023")[0]
    assert o.region == "Santa Cruz Mountains"
    assert o.subregion == ""
    assert o.varietal == "Cabernet Sauvignon, Cabernet Franc"
    assert o.graph_category == "Bordeaux Blend"


def test_diamond_mountain_maps_to_napa_subregion_and_prose_varietal():
    html = """
    <html><body>
      <h1>Vineyard II №2 — 2023</h1>
      <h4>Diamond Mountain</h4>
      <p>Cabernet Sauvignon “Vineyard II” comes from a historic vineyard atop Diamond Mountain.
      This tiny sliver of Napa Valley produces powerful mountain wines.</p>
      <p>Alcohol 14.5. Cases Produced 173. $135. Buy</p>
    </body></html>
    """
    o = _extract_product_page_offers(html, "https://example.com/shop/vineyard-2-2023")[0]
    assert o.region == "Napa Valley"
    assert o.subregion == "Diamond Mountain"
    assert o.varietal == "Cabernet Sauvignon"
    assert o.graph_category == "Cabernet Sauvignon"


def test_universal_finalizer_applies_to_non_provider_serialized_rows():
    from catalog_scraper import finalize_catalog_offer_dicts
    rows = [{
        "wine": "Vineyard II №2",
        "vintage": "2023",
        "regular_price": 135.0,
        "sale_price": None,
        "club_price": None,
        "currency": "USD",
        "product_url": "https://example.com/shop/vineyard-2-2023",
        "evidence": "Cabernet Sauvignon from Diamond Mountain.",
        "extraction_method": "Selected product page",
        "confidence": "High",
        "varietal": "",
        "graph_category": "Cabernet Sauvignon",
        "general_category": "Red",
        "region": "Diamond Mountain",
        "subregion": "",
        "alcohol_pct": 14.5,
        "cases_produced": 173,
        "estate": False,
        "single_vineyard": True,
        "product_tier": "Limited",
        "availability_status": "Available",
    }]
    o = finalize_catalog_offer_dicts(rows)[0]
    assert o["varietal"] == "Cabernet Sauvignon"
    assert o["region"] == "Napa Valley"
    assert o["subregion"] == "Diamond Mountain"


def test_percent_composition_stops_at_next_metadata_field():
    html = """
    <html><body>
      <h1>2024 Côtes du Rôbles Rouge</h1>
      <div>Wine Specs</div>
      <div>Varietal</div><div>56% Grenache, 38% Syrah, 6% Mourvedre</div>
      <div>Appellation</div><div>Paso Robles, Adelaida District</div>
      <div>Alcohol</div><div>13.9%</div>
      <div>$40</div><div>Add to Cart</div>
    </body></html>
    """
    offers = _extract_product_page_offers(html, "https://example.com/product/rouge")
    assert len(offers) == 1
    o = offers[0]
    assert o.varietal == "56% Grenache, 38% Syrah, 6% Mourvèdre"
    assert "Appellation" not in o.varietal
    assert o.graph_category == "Rhône Blend"
    assert o.region == "Paso Robles"
    assert o.subregion == "Adelaida District"


def test_single_varietal_field_stops_at_appellation_label():
    html = """
    <html><body>
      <h1>2023 Vineyard Selection Cabernet</h1>
      <div>Varietal 100% Cabernet Sauvignon Appellation Paso Robles Alcohol 13.9%</div>
      <div>$30</div><div>Buy</div>
    </body></html>
    """
    offers = _extract_product_page_offers(html, "https://example.com/product/vbcab")
    assert len(offers) == 1
    assert offers[0].varietal == "Cabernet Sauvignon"
    assert offers[0].graph_category == "Cabernet Sauvignon"


def test_contradictory_template_availability_is_left_blank():
    html = """
    <html><body>
      <h1>2024 Reserve Chardonnay</h1>
      <p>Chardonnay. Paso Robles. Alcohol 13.8%.</p>
      <div>$48</div>
      <div>Sold Out</div><div>Back Ordered</div><div>Add to Cart</div>
    </body></html>
    """
    offers = _extract_product_page_offers(html, "https://example.com/product/chardonnay")
    assert len(offers) == 1
    assert offers[0].availability_status == ""


def test_member_exclusive_can_still_be_buyable_without_false_conflict():
    html = """
    <html><body>
      <h1>2025 Chardonnay</h1>
      <p>Member Exclusive. Chardonnay. Napa Valley. Alcohol 12.4%.</p>
      <div>$50</div><div>Add to Cart</div>
    </body></html>
    """
    offers = _extract_product_page_offers(html, "https://example.com/product/chardonnay")
    assert len(offers) == 1
    assert offers[0].availability_status == "Member exclusive"


def test_review_gate_excludes_merch_navigation_and_nonstandard_bottle_sizes():
    from catalog_scraper import WineOffer, finalize_catalog_offers

    def offer(name: str) -> WineOffer:
        return WineOffer(
            wine=name,
            vintage="2025",
            regular_price=20.0,
            sale_price=None,
            club_price=None,
            currency="USD",
            product_url="https://example.com/shop/item",
            evidence="",
            extraction_method="HTML card",
            confidence="Moderate",
        )

    finalized = finalize_catalog_offers([
        offer("Customize Your Own 2 Bottle Gift Set"),
        offer("Club Only"),
        offer("Winery Only"),
        offer("Full Boar White Blend 375 ML"),
        offer("Cabernet Sauvignon 1.5 L Magnum"),
        offer("Vintage of Valor"),  # proprietary wine name must survive
        offer("Cabernet Sauvignon"),
    ])
    names = {o.wine for o in finalized}
    assert names == {"Vintage of Valor", "Cabernet Sauvignon"}


def test_reserve_tier_requires_whole_word_not_preserve_prose():
    from catalog_scraper import _extract_product_metadata

    text = (
        "2024 Côtes du Rôbles Rouge. The élevage preserves freshness and vibrant fruit. "
        "56% Grenache, 38% Syrah, 6% Mourvèdre. Appellation Paso Robles."
    )
    meta = _extract_product_metadata("2024 Côtes du Rôbles Rouge", text)
    assert meta["product_tier"] == "Core"


def test_explicit_reserve_title_still_maps_to_reserve():
    from catalog_scraper import _extract_product_metadata

    text = "2024 Reserve Chardonnay. 100% Chardonnay. Appellation Paso Robles."
    meta = _extract_product_metadata("2024 Reserve Chardonnay", text)
    assert meta["product_tier"] == "Reserve"


def test_single_varietal_drops_100_percent_and_estate_qualifier():
    from catalog_scraper import _normalize_varietal_aliases

    assert _normalize_varietal_aliases("100% Estate Cabernet Sauvignon") == "Cabernet Sauvignon"
    assert _normalize_varietal_aliases("100% Chardonnay") == "Chardonnay"
    # Blend composition percentages remain meaningful and must be retained.
    assert _normalize_varietal_aliases("56% Grenache, 38% Syrah, 6% Mourvèdre") == (
        "56% Grenache, 38% Syrah, 6% Mourvèdre"
    )


def test_modern_jsonld_identity_beats_conflicting_navigation_text():
    html = '''
    <html><body>
      <nav>ALL WINES WHITE & ROSÉ WINES RED WINES</nav>
      <main>
        <h1>2023 Cabernet Sauvignon</h1>
        <script type="application/ld+json">{
          "@context":"https://schema.org", "@type":"Product",
          "name":"2023 Cabernet Sauvignon",
          "description":"Cabernet Sauvignon from Paso Robles.",
          "offers":{"@type":"Offer","price":"55.00","priceCurrency":"USD"}
        }</script>
        <div>$55.00</div>
      </main>
    </body></html>
    '''
    o = _extract_product_page_offers(html, "https://example.com/products/cabernet")[0]
    assert o.graph_category == "Cabernet Sauvignon"
    assert o.general_category == "Red"
    assert o.regular_price == 55.0
    assert o.confidence == "High"


def test_legacy_navigation_cannot_turn_gsm_into_rose_and_quantity_tier_is_not_sale():
    html = '''
    <html><body>
      <div class="site-menu">ALL WINES WHITE & ROSÉ WINES RED WINES</div>
      <div class="product-detail">
        <h1>2022 G-S-M Red Blend</h1>
        <div>Price: $40.00</div>
        <div>Description</div>
        <p>Grenache, Syrah, and Mourvèdre create this classic Rhône-style red blend.</p>
        <div>Price Details Qty Unit Price 1 - 11 $40.00 12 + $36.00</div>
      </div>
      <footer>Club Members save even more.</footer>
    </body></html>
    '''
    o = _extract_product_page_offers(html, "https://legacy.example.com/2022-g-s-m-red-blend-p311.aspx")[0]
    assert o.graph_category == "Rhône Blend"
    assert o.general_category == "Red"
    assert o.varietal == "Grenache, Syrah, Mourvèdre"
    assert o.regular_price == 40.0
    assert o.sale_price is None
    assert o.club_price is None
    assert o.confidence == "Moderate"


def test_quantity_discount_is_not_sale_but_explicit_sale_still_is():
    from catalog_scraper import _classify_prices
    regular, sale, club = _classify_prices("Price: $49.00 Qty Unit Price 1 - 11 $49.00 12 + $44.10")
    assert regular == 49.0
    assert sale is None
    assert club is None

    regular, sale, club = _classify_prices("Regular Price: $60.00 Sale Price: $48.00")
    assert regular == 60.0
    assert sale == 48.0
    assert club is None


def test_generic_club_message_does_not_create_club_price_but_explicit_club_price_does():
    from catalog_scraper import _classify_prices
    regular, sale, club = _classify_prices("Club member? Log in for exclusive pricing and offers. Price: $49.00")
    assert regular == 49.0
    assert sale is None
    assert club is None

    regular, sale, club = _classify_prices("Retail Price: $49.00 Club Price: $39.20")
    assert regular == 49.0
    assert club == 39.2


def test_five_sisters_product_local_estate_and_cabernet_identity():
    html = '''
    <html><body>
      <div>WHITE & ROSÉ WINES</div>
      <div class="product-detail">
        <h1>2023 Five Sisters Cabernet Sauvignon</h1>
        <div>Price: $49.00</div>
        <p>Grapes for our Estate Five Sisters Blend Cabernet Sauvignon were cool fermented.
        The wine is a blend of 85% Cabernet Sauvignon, 7% Malbec, 5% Merlot,
        2% Cabernet Franc, and 1% Petit Verdot.</p>
        <div>Price Details Qty Unit Price 1 - 11 $49.00 12 + $44.10</div>
      </div>
    </body></html>
    '''
    o = _extract_product_page_offers(html, "https://legacy.example.com/five-sisters.aspx")[0]
    assert o.graph_category == "Cabernet Sauvignon"
    assert o.general_category == "Red"
    assert o.estate is True
    assert o.sale_price is None
    assert o.club_price is None


def test_left_bank_complex_bordeaux_composition_remains_bordeaux_blend():
    html = '''
    <html><body><div class="product-detail">
      <h1>2023 Left Bank Cuvée</h1>
      <div>Price: $43.00</div>
      <p>31% Cabernet Sauvignon, 26% Petit Verdot, 24% Malbec, 11% Merlot, 8% Cabernet Franc.</p>
      <div>Price Details 1 - 11 $43.00 12 + $38.70</div>
    </div></body></html>
    '''
    o = _extract_product_page_offers(html, "https://legacy.example.com/left-bank.aspx")[0]
    assert o.graph_category == "Bordeaux Blend"
    assert o.general_category == "Red"
    assert o.sale_price is None
    assert "31% Cabernet Sauvignon" in o.varietal


def test_ai_auto_policy_skips_complete_high_jsonld_but_uses_legacy():
    from catalog_scraper import WineOffer, should_use_ai_for_product_page
    structured = WineOffer(
        wine="Cabernet Sauvignon", vintage="2023", regular_price=50.0,
        sale_price=None, club_price=None, currency="USD",
        product_url="https://example.com/cab", evidence="JSON-LD Product",
        extraction_method="JSON-LD", confidence="High",
        varietal="Cabernet Sauvignon", graph_category="Cabernet Sauvignon",
        general_category="Red", region="Paso Robles", alcohol_pct=14.5,
    )
    assert should_use_ai_for_product_page([structured], "auto") is False

    legacy = WineOffer(
        wine="Cabernet Sauvignon", vintage="2023", regular_price=50.0,
        sale_price=45.0, club_price=50.0, currency="USD",
        product_url="https://legacy.example.com/cab", evidence="legacy text",
        extraction_method="Selected product page fallback", confidence="Moderate",
    )
    assert should_use_ai_for_product_page([legacy], "auto") is True
    assert should_use_ai_for_product_page([legacy], "off") is False
    assert should_use_ai_for_product_page([structured], "always") is True


def test_ai_merge_clears_legacy_quantity_discount_and_navigation_contamination():
    from catalog_scraper import WineOffer, merge_ai_product_result
    legacy = WineOffer(
        wine="2022 G-S-M Red Blend", vintage="2022", regular_price=40.0,
        sale_price=36.0, club_price=40.0, currency="USD",
        product_url="https://legacy.example.com/gsm", evidence="WHITE & ROSÉ WINES ...",
        extraction_method="Selected product page fallback", confidence="Moderate",
        varietal="", graph_category="Rosé", general_category="Rosé",
    )
    ai = {
        "wine": "G-S-M Red Blend", "vintage": 2022,
        "regular_price": 40.0, "sale_price": None, "club_price": None,
        "currency": "USD", "varietal": "Grenache, Syrah, Mourvèdre",
        "graph_category": "Rhône Blend", "general_category": "Red",
        "region": None, "subregion": None, "alcohol_pct": None,
        "cases_produced": None, "estate_status": "Unknown",
        "single_vineyard_status": "Unknown", "product_tier": "Core",
        "availability_status": None, "overall_confidence": "Moderate",
        "evidence": {
            "wine": "2022 G-S-M Red Blend", "vintage": "2022",
            "regular_price": "$40.00", "sale_price": None, "club_price": None,
            "varietal": "Grenache, Syrah, and Mourvèdre", "region": None,
            "subregion": None, "alcohol_pct": None, "cases_produced": None,
            "estate_status": None, "single_vineyard_status": None,
            "product_tier": None, "availability_status": None,
        },
        "warnings": ["12+ bottle price is a quantity discount, not a sale."],
    }
    out = merge_ai_product_result([legacy], ai, legacy.product_url)[0]
    assert out.regular_price == 40.0
    assert out.sale_price is None
    assert out.club_price is None
    assert out.graph_category == "Rhône Blend"
    assert out.general_category == "Red"
    assert out.varietal == "Grenache, Syrah, Mourvèdre"
    assert "AI" in out.extraction_method


def test_ai_merge_preserves_high_structured_price_identity():
    from catalog_scraper import WineOffer, merge_ai_product_result
    structured = WineOffer(
        wine="Cabernet Sauvignon", vintage="2023", regular_price=70.0,
        sale_price=None, club_price=None, currency="USD",
        product_url="https://modern.example.com/cab", evidence="JSON-LD Product",
        extraction_method="JSON-LD", confidence="High",
        varietal="Cabernet Sauvignon", graph_category="Cabernet Sauvignon",
        general_category="Red", region="Napa Valley",
    )
    ai = {
        "wine": "Cabernet", "vintage": 2023,
        "regular_price": 65.0, "sale_price": None, "club_price": None,
        "currency": "USD", "varietal": "Cabernet Sauvignon",
        "graph_category": "Cabernet Sauvignon", "general_category": "Red",
        "region": "Napa Valley", "subregion": "Oak Knoll District",
        "alcohol_pct": 14.3, "cases_produced": 1278,
        "estate_status": "Unknown", "single_vineyard_status": "Unknown",
        "product_tier": "Core", "availability_status": "Available",
        "overall_confidence": "High",
        "evidence": {
            "wine": "Cabernet", "vintage": "2023", "regular_price": "$65",
            "sale_price": None, "club_price": None,
            "varietal": "Cabernet Sauvignon", "region": "Napa Valley",
            "subregion": "Oak Knoll District", "alcohol_pct": "14.3%",
            "cases_produced": "1,278 cases", "estate_status": None,
            "single_vineyard_status": None, "product_tier": None,
            "availability_status": "Add to cart",
        },
        "warnings": [],
    }
    out = merge_ai_product_result([structured], ai, structured.product_url)[0]
    assert out.wine == "Cabernet Sauvignon"
    assert out.regular_price == 70.0
    assert out.subregion == "Oak Knoll District"
    assert out.alcohol_pct == 14.3
    assert out.extraction_method == "JSON-LD + AI enrichment"


def test_ai_page_evidence_prefers_product_component_over_navigation():
    from catalog_scraper import build_ai_page_evidence
    html = '''
    <html><body>
      <nav>WHITE & ROSÉ WINES RED WINES CLUB GIFTS</nav>
      <div class="product-detail">
        <h1>2023 Five Sisters Cabernet Sauvignon</h1>
        <div>Price: $49.00</div>
        <p>Estate Five Sisters Blend. 85% Cabernet Sauvignon, 7% Malbec.</p>
      </div>
      <footer>WHITE & ROSÉ WINES</footer>
    </body></html>
    '''
    evidence = build_ai_page_evidence(html, "https://legacy.example.com/five-sisters")
    assert evidence["text_scope"] == "product-container"
    assert "Five Sisters Cabernet Sauvignon" in evidence["product_local_text"]
    assert "WHITE & ROSÉ WINES" not in evidence["product_local_text"]


def test_selected_page_ai_path_uses_fake_extractor_without_extra_site_logic(monkeypatch):
    import catalog_scraper as cs

    html = '''<html><body><div class="product-detail"><h1>2023 Left Bank Cuvée</h1>
    <div>Price: $43.00</div><p>31% Cabernet Sauvignon, 26% Petit Verdot, 24% Malbec,
    11% Merlot, 8% Cabernet Franc.</p><div>1 - 11 $43.00 12 + $38.70</div></div></body></html>'''

    fetch = cs.CatalogFetch(
        requested_url="https://legacy.example.com/left-bank", final_url="https://legacy.example.com/left-bank",
        status_code=200, content_type="text/html", html=html, bytes_read=len(html), robots_status="robots.txt allows this URL"
    )
    monkeypatch.setattr(cs, "validate_public_url", lambda url: url)
    monkeypatch.setattr(cs, "fetch_catalog_page", lambda url: fetch)

    calls = []
    def fake_ai(evidence_payload, **kwargs):
        calls.append(evidence_payload)
        return {
            "wine": "Left Bank Cuvée", "vintage": 2023, "regular_price": 43.0,
            "sale_price": None, "club_price": None, "currency": "USD",
            "varietal": "31% Cabernet Sauvignon, 26% Petit Verdot, 24% Malbec, 11% Merlot, 8% Cabernet Franc",
            "graph_category": "Bordeaux Blend", "general_category": "Red",
            "region": None, "subregion": None, "alcohol_pct": None, "cases_produced": None,
            "estate_status": "Unknown", "single_vineyard_status": "Unknown",
            "product_tier": "Core", "availability_status": None,
            "overall_confidence": "Moderate",
            "evidence": {k: None for k in [
                "wine", "vintage", "regular_price", "sale_price", "club_price", "varietal",
                "region", "subregion", "alcohol_pct", "cases_produced", "estate_status",
                "single_vineyard_status", "product_tier", "availability_status"
            ]},
            "warnings": [],
        }

    offers, failures, fetched_count = cs.scan_selected_product_pages(
        ["https://legacy.example.com/left-bank"], delay_seconds=0,
        ai_mode="always", producer_hint="J. Rickards Winery", ai_extractor=fake_ai,
    )
    assert fetched_count == 1
    assert len(calls) == 1
    assert len(offers) == 1
    assert offers[0].graph_category == "Bordeaux Blend"
    assert offers[0].sale_price is None
    assert not failures
