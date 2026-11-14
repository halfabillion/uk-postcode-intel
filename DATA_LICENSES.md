# Data sources and licences

The MIT licence in [LICENSE](LICENSE) covers this repository's software (source code, tests, scripts and documentation). It does not cover the datasets the server queries, or the bundled Indices of Deprivation extract. Those remain under their publishers' terms.

The statements below are taken from the server's own attribution block in `src/uk_postcode_intel/full_report.py` and from the sources' public licence pages, as checked on 14 November 2026. Where a publisher specifies an attribution sentence, that wording is quoted. The [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) is abbreviated as OGL v3.0 below.

## 1. Postcode geography — ONS Postcode Directory via postcodes.io

Used by every tool for location lookup, and by `full_area_intelligence` to find neighbouring postcodes for house prices. National deprivation ranks for Wales, Scotland and Northern Ireland also come from ONSPD fields exposed by postcodes.io.

- API: <https://api.postcodes.io>
- Licences: <https://postcodes.io/docs/licences/>

postcodes.io states:

- Its source code is available under the MIT Licence.
- Great Britain postcode data may be used under the terms of the OS OpenData licence.
- Northern Ireland postcode data (postcodes beginning "BT") may be used under the terms of the ONSPD licence. Non-commercial use is free. Commercial use requires a licence from Land & Property Services Northern Ireland.

Required attributions, as published on that licences page:

- Contains Ordnance Survey data © Crown copyright and database right 2025.
- Contains Royal Mail data © Royal Mail copyright and database right 2025.
- Contains National Statistics data © Crown copyright and database right 2025.
- Contains NRS data © Crown copyright and database right 2025.

## 2. Census 2021 — Office for National Statistics via Nomis

Used by `full_area_intelligence` for neighbourhood, local-authority and national comparisons in England and Wales.

- API: <https://www.nomisweb.co.uk/api/v01/dataset>
- Copyright: <https://www.nomisweb.co.uk/home/copyright.asp>

Nomis states that ONS material may be used or re-used under the Open Government Licence and the UK Government Licensing Framework, commercially or privately, without a specific application for a licence, subject to those terms. Required source accreditation:

> Source: Office for National Statistics

Nomis also states that National Statistics products incorporate safeguards against identification, and that you must not use the products to obtain or derive information relating specifically to an identified person, household or business.

## 3. English Indices of Deprivation 2025 — MHCLG

Used by `full_area_intelligence` for England. A compact extract of LSOA 2021 IMD ranks, IMD deciles and seven domain deciles is bundled at `src/uk_postcode_intel/data/iod2025_lsoa.csv.gz`.

- Publisher: Ministry of Housing, Communities & Local Government
- Dataset: <https://www.gov.uk/government/statistics/english-indices-of-deprivation-2025>

The official research and technical reports for the Indices of Deprivation 2025 state that the information may be re-used (not including logos) free of charge in any format or medium under the terms of the Open Government Licence.

Contains public sector information licensed under the Open Government Licence v3.0. Source: Ministry of Housing, Communities & Local Government, English Indices of Deprivation 2025.

## 4. Street-level crime — data.police.uk

Used by `crime_summary`, `area_report` and `full_area_intelligence`. Coverage is England, Wales and Northern Ireland.

- Site: <https://data.police.uk/>

data.police.uk states: "All the data on this site is made available under the Open Government Licence v3.0."

## 5. Live flood alerts and river gauges — Environment Agency

Used by `flood_warnings`, `area_report` and `full_area_intelligence`. Coverage is England.

- API reference: <https://environment.data.gov.uk/flood-monitoring/doc/reference>

The Environment Agency states that these APIs are provided as open data under the Open Government Licence, with no requirement for registration. API responses cite OGL v3.0. Required attribution:

> this uses Environment Agency flood and river level data from the real-time data API (Beta)

## 6. Food hygiene ratings — Food Standards Agency

Used by `food_hygiene_nearby`, `area_report` and `full_area_intelligence`.

- API: <https://api.ratings.food.gov.uk/>
- Terms: <https://www.gov.uk/government/organisations/food-standards-agency/about/about-our-services>

The FSA states: "All content is available under the Open Government Licence v3.0, except where otherwise stated," and that use of food hygiene ratings information and services is subject to the terms of the Open Government Licence.

The FSA also states that ratings change as inspections are updated; that displaying or otherwise using an invalid or inaccurate rating may constitute a criminal offence; and that users should use the current rating or indicate the date when the information was updated. FHRS imagery and the FSA logo are not licensed by the OGL and are not included in this repository.

## 7. Residential sold prices — HM Land Registry Price Paid Data

Used by `house_prices`, `area_report` and `full_area_intelligence`. Coverage is England and Wales (residential sales lodged with HM Land Registry for registration).

- Linked data: <https://landregistry.data.gov.uk/>
- Licence notes: <https://www.gov.uk/government/statistical-data-sets/price-paid-data-downloads>

HM Land Registry requires this attribution statement:

> Contains HM Land Registry data © Crown copyright and database right 2021. This data is licensed under the Open Government Licence v3.0.

The same page states that Price Paid Data is released under the Open Government Licence, but that the OGL does not cover third-party rights HM Land Registry is not authorised to license. Price Paid Data contains address data processed against Ordnance Survey's AddressBase Premium product, which incorporates Royal Mail's PAF® database. Royal Mail and Ordnance Survey permit use of that address data for personal and/or non-commercial use, and to display for the purpose of providing residential property price information services. Other uses of the address data require permission from Royal Mail.
