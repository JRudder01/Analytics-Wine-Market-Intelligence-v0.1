# Data sources and provenance

## Rudder historical Paso pricing seed

Source file supplied by the user:

`Wine Prices_Paso - 2025-11-15.xlsx`

The build normalizes priced observations from the repeated winery sections in the `Data` worksheet. The workbook's `database` worksheet is not used as the main seed because it contains fewer records than the `Data` sheet.

## Bureau of Labor Statistics — Wine at Home CPI

BLS Public Data API:

https://api.bls.gov/publicAPI/v1/timeseries/data/CUUR0000SEFW03

BLS API documentation:

https://www.bls.gov/developers/api_signature.htm

Current bundled snapshot: August 2026 Wine at Home CPI, -1.1% year over year.

## TTB wine reports

Official Wine Reports page:

https://www.ttb.gov/regulated-commodities/beverage-alcohol/wine/wine-statistics

The TTB page publishes yearly and monthly wine data in CSV and JSON formats and refreshes historical periods when corrected data is posted.

## TTB wine producer permits

Official List of Permittees:

https://www.ttb.gov/public-information/foia/list-of-permittees

TTB states that the permit files are provided in CSV/JSON for machine readability and updates the listings weekly.

## USDA/NASS California Grape Crush

Official report archive:

https://www.nass.usda.gov/Statistics_by_State/California/Publications/Specialty_and_Other_Releases/Grapes/Crush/Reports/

The 2025 Final report is published in PDF, XLSX and CSV formats. The bundled model snapshot uses the official 2025 report summary: total California crush down 6.2% year over year and red wine varieties down 10.8%.

## Eberle public enrichment records

Two public-price records retained from v0.1 are included to preserve a broader Eberle Cabernet ladder:

- 2021 Reserve Cabernet Sauvignon
- 2024 Vineyard Selection Cabernet Sauvignon

These records are explicitly marked as public enrichment in the seed file.

## Paso visitor / tasting-fee workbook context

The supplied workbook includes monthly visitor and tasting-fee reference tables. They are displayed in the Data Hub but **not used by the pricing engine in v0.2**, because the workbook does not embed sufficient source provenance for those values.
