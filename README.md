# Rudder Wine Market Intelligence v0.3.13

This patch integrates the experimental low-request Winery Catalog Scan directly into the primary Rudder Wine Market Intelligence app.

It preserves the existing Pricing Analysis, screenshot/clipboard intake, GitHub batch persistence, identity normalization, category/color matching, and public-market context workflows from v0.3.12.

## New experimental catalog scan

In **Data Hub (Admin)**, paste one public winery shop/catalog URL and click **Scan this catalog page**.

The scanner:
- checks robots.txt first;
- fetches only the exact page the administrator pasted;
- does not automatically follow product links;
- does not execute JavaScript or separately fetch images/CSS/scripts;
- stops on 401/403/429 rather than bypassing or retrying;
- caps HTML at 2 MB;
- extracts factual product names and retail/sale/club prices from static HTML and JSON-LD;
- requires manual review;
- does not automatically write scan results to the permanent comp database.

The first scan of a domain may make two requests (robots.txt + the pasted page). robots.txt results are cached in-process for 24 hours.
