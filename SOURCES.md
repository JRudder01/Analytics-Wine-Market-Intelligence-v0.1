# Data sources and provenance

## Rudder historical Paso pricing seed

Source file supplied by the user:

`Wine Prices_Paso - 2025-11-15.xlsx`

The build normalizes priced observations from the repeated winery sections in the `Data` worksheet.

## AI Screenshot Intake

Screenshot extraction uses OpenAI's Responses API with administrator-uploaded image input and strict structured output. The app does not automatically visit the source URL during extraction.

Official OpenAI references:

- Responses API: https://developers.openai.com/api/reference/cli/resources/responses/methods/create
- Models: https://developers.openai.com/api/docs/models

The API key is supplied through Streamlit Secrets / environment variables and is not stored in the repository.

Source provenance for every approved wine observation should retain `source_name`, `source_url`, `price_date`, and `data_confidence`.

## Bureau of Labor Statistics — Wine at Home CPI

BLS Public Data API:

https://api.bls.gov/publicAPI/v1/timeseries/data/CUUR0000SEFW03

BLS API documentation:

https://www.bls.gov/developers/api_signature.htm

## TTB wine reports

Official Wine Reports page:

https://www.ttb.gov/regulated-commodities/beverage-alcohol/wine/wine-statistics

## TTB wine producer permits

Official List of Permittees:

https://www.ttb.gov/public-information/foia/list-of-permittees

## USDA/NASS California Grape Crush

Official report archive:

https://www.nass.usda.gov/Statistics_by_State/California/Publications/Specialty_and_Other_Releases/Grapes/Crush/Reports/

## Eberle public enrichment records

Two public-price records retained from v0.1 are included to preserve a broader Eberle Cabernet ladder. All new screenshot-derived records should be reviewed by a Rudder administrator before being added to the persisted comp file.

## Paso visitor / tasting-fee workbook context

The supplied workbook includes monthly visitor and tasting-fee reference tables. They are displayed in the Data Hub but are not used by the pricing engine until provenance is verified.
