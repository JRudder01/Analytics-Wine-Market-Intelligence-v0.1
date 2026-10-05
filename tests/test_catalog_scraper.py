from catalog_scraper import extract_catalog_offers


def test_jsonld_products():
    html = '''
    <html><head><script type="application/ld+json">
    {"@context":"https://schema.org","@type":"ItemList","itemListElement":[
      {"@type":"Product","name":"2024 Estate Chardonnay","url":"/wine/chard","offers":{"@type":"Offer","price":"35.00","priceCurrency":"USD"}},
      {"@type":"Product","name":"2025 Viognier","url":"/wine/viognier","offers":{"@type":"Offer","price":"42","priceCurrency":"USD"}}
    ]}
    </script></head><body></body></html>
    '''
    rows = extract_catalog_offers(html, "https://example.com/shop")
    assert len(rows) == 2
    assert rows[0].wine == "2024 Estate Chardonnay"
    assert rows[0].vintage == "2024"
    assert rows[0].regular_price == 35.0


def test_html_cards_and_club_price():
    html = '''
    <html><body>
      <div class="product-card"><a href="/product/cab">2023 Cabernet Sauvignon</a><span>Retail $30</span><span>Wine Society $24</span></div>
      <div class="product-card"><a href="/product/blanc">Côtes-du-Rôbles Blanc</a><span>$34.00</span></div>
    </body></html>
    '''
    rows = extract_catalog_offers(html, "https://example.com/shop")
    by_name = {r.wine: r for r in rows}
    assert by_name["2023 Cabernet Sauvignon"].regular_price == 30.0
    assert by_name["2023 Cabernet Sauvignon"].club_price == 24.0
    assert by_name["Côtes-du-Rôbles Blanc"].regular_price == 34.0
