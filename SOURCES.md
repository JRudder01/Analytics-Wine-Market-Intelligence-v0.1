# Data provenance — v0.1

## User-supplied seed data

The starter Paso Robles Cabernet/Bordeaux records were extracted from the supplied `Wine Pricing.accdb` database. The v0.1 normalized seed retains the winery, wine, vintage, price, and broad market category needed for the first prototype.

## Public Eberle validation records

Captured 2026-09-17 from Eberle Winery's public shop pages:

- 2023 Vineyard Selection Cabernet Sauvignon — $30 winery retail, 100% Cabernet Sauvignon, Paso Robles, 13.9% ABV, Wine Enthusiast 91.
  - https://shop.eberlewinery.com/SHOP.AMS?LEVEL=BOT&PART=VBCAB23
- 2023 Estate Cabernet Sauvignon — $60 winery retail, 100% Estate Cabernet Sauvignon, Paso Robles, 14.5% ABV.
  - https://shop.eberlewinery.com/SHOP.AMS?LEVEL=BOT&PART=CABERNET23
- 2021 Reserve Cabernet Sauvignon — $125 winery retail, 100% Estate Cabernet Sauvignon, Paso Robles, 14.5% ABV.
  - https://shop.eberlewinery.com/SHOP.AMS?LEVEL=BOT&PART=CABRES21
- 2024 Vineyard Selection Cabernet Sauvignon — $32 winery retail as listed in the Eberle shop category page.
  - https://shop.eberlewinery.com/SHOP.AMS?CATCODE=CLUB&LEVEL=MID

## Commercialization note

Public visibility does not automatically grant permission for automated commercial extraction or redistribution. Before a production crawler is enabled for any source, its current terms, robots policy, API availability, and licensing should be reviewed. The first build therefore uses a curated seed rather than live scraping at customer-analysis time.
