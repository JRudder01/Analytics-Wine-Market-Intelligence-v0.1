# v0.3.20 update instructions

1. Replace root `app.py`.
2. Replace root `catalog_scraper.py`.
3. Optionally replace `tests/test_catalog_enrichment.py`.
4. Commit to `main` and let Streamlit redeploy.

No changes are required to:

- `requirements.txt`
- `.streamlit/secrets.toml`
- GitHub token permissions
- `data/wine_comps.csv`

## VinoShipper test

For `https://vinoshipper.com/shop/915_lincoln`:

- First try leaving **VinoShipper producer ID** blank.
- If the public shell exposes the ID, the Product Feed is used automatically.
- If not, enter `4112` for the 915 Lincoln test and scan again.

The product-feed call is a documented VinoShipper client/product-feed route; the patch does not add browser automation.
