# v0.3.13 update instructions

Upload/replace these files in the **root** of the existing GitHub repository:

- `app.py`
- `catalog_scraper.py` (new)
- `requirements.txt`

No database replacement, GitHub secret change, OpenAI key change, or Streamlit setting change is required for this patch.

After committing the files, allow Streamlit to redeploy. Open **Data Hub (Admin)** and use the new **Winery Catalog Scan (Experimental)** section.

For testing, paste one winery shop/catalog URL at a time. The tool will not automatically crawl the rest of the winery site or open each wine product page.
