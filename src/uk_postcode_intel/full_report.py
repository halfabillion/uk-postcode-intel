"""Headline tool: one rich, structured area-intelligence report for a UK postcode.

Every source is fetched in parallel with its own timeout. A failing or out-of-coverage
source never breaks the report: it is reported under ``sources_status`` and the rest
of the report is still returned.
"""

from __future__ import annotations

import asyncio
import csv
import gzip
import statistics
import time
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx

from .tools import UA, _crime_g, _flood_g, _food_g, _geo, _get, _norm, _prices_pc

SOURCE_TIMEOUT = 15.0  # seconds per source
LR_TIMEOUT = httpx.Timeout(20.0)
HP_TIMEOUT = 25.0  # house prices: own postcode + neighbours in parallel
NOMIS = "https://www.nomisweb.co.uk/api/v01/dataset"
DATA_DIR = Path(__file__).parent / "data"

# Census 2021 topic tables on Nomis: (key, dataset id, dimension)
CENSUS_TABLES = {
    "population": ("NM_2021_1", "C2021_RESTYPE_3"),
    "age": ("NM_2020_1", "C2021_AGE_19"),
    "tenure": ("NM_2072_1", "C2021_TENURE_9"),
    "accommodation": ("NM_2062_1", "C2021_ACCTYPE_9"),
    "cars": ("NM_2063_1", "C2021_CARS_5"),
    "economic_activity": ("NM_2083_1", "C2021_EASTAT_20"),
    "qualifications": ("NM_2084_1", "C2021_HIQUAL_8"),
    "health": ("NM_2055_1", "C2021_HEALTH_6"),
}

NATION_CODES = {"England": "E92000001", "Wales": "W92000004"}

# Ranks published per nation; deciles are within that nation only.
NATION_INDEX = {
    "Wales": ("Welsh Index of Multiple Deprivation (as published in ONSPD)", 1909),
    "Scotland": ("Scottish Index of Multiple Deprivation (as published in ONSPD)", 6976),
    "Northern Ireland": ("NI Multiple Deprivation Measure (as published in ONSPD)", 890),
}

ATTRIBUTION = [
    {"data": "Postcode geography, admin areas, LSOA/MSOA, rural-urban class",
     "source": "ONS Postcode Directory via postcodes.io",
     "licence": "Open Government Licence v3.0; contains OS data © Crown copyright"},
    {"data": "Census 2021 demographics (LSOA, local authority, nation)",
     "source": "ONS Census 2021 via Nomis (nomisweb.co.uk)",
     "licence": "Open Government Licence v3.0; Source: Office for National Statistics"},
    {"data": "English Indices of Deprivation 2025 (IMD + 7 domains, by LSOA 2021)",
     "source": "Ministry of Housing, Communities & Local Government",
     "licence": "Open Government Licence v3.0"},
    {"data": "Street-level crime (latest published month, ~1 mile)",
     "source": "data.police.uk", "licence": "Open Government Licence v3.0"},
    {"data": "Live flood alerts/warnings and monitoring stations",
     "source": "Environment Agency real-time flood-monitoring API",
     "licence": "Open Government Licence v3.0; this uses Environment Agency flood and "
                "river level data from the real-time data API (Beta)"},
    {"data": "Food hygiene ratings", "source": "Food Standards Agency FHRS/FHIS API",
     "licence": "Open Government Licence v3.0"},
    {"data": "Residential sold prices",
     "source": "HM Land Registry Price Paid Data",
     "licence": "Open Government Licence v3.0; contains HM Land Registry data © Crown "
                "copyright and database right 2026"},
]


# --------------------------------------------------------------------------- helpers

async def _timed(name: str, coro, status: dict[str, Any], timeout: float | None = None):
    """Run one source with a timeout; record ok/error + latency; never raise."""
    timeout = SOURCE_TIMEOUT if timeout is None else timeout
    t0 = time.perf_counter()
    try:
        out = await asyncio.wait_for(coro, timeout)
        status[name] = {"ok": True, "ms": round((time.perf_counter() - t0) * 1000)}
        return out
    except Exception as e:  # noqa: BLE001
        msg = "timed out" if isinstance(e, asyncio.TimeoutError | TimeoutError) else (
            f"{type(e).__name__}: {e}")
        status[name] = {"ok": False, "ms": round((time.perf_counter() - t0) * 1000),
                        "error": msg[:200]}
        return None


def _skip(name: str, reason: str, status: dict[str, Any]) -> None:
    status[name] = {"ok": False, "skipped": True, "error": reason}


@lru_cache(maxsize=1)
def _iod2025() -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    with gzip.open(DATA_DIR / "iod2025_lsoa.csv.gz", "rt", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            code = row.pop("lsoa21")
            out[code] = {k: int(v) for k, v in row.items()}
    return out


def deprivation(g: dict[str, Any]) -> dict[str, Any]:
    """IMD for the postcode's LSOA. England: IoD2025 bundled lookup (LSOA 2021).
    Wales/Scotland/NI: national rank from ONSPD, decile derived from the rank."""
    country = g.get("country")
    lsoa = (g.get("codes") or {}).get("lsoa21") or (g.get("codes") or {}).get("lsoa")
    if country == "England" and lsoa:
        rec = _iod2025().get(lsoa)
        if rec:
            names = {"income": "Income", "employment": "Employment",
                     "education": "Education, skills & training",
                     "health": "Health & disability", "crime": "Crime",
                     "barriers": "Barriers to housing & services",
                     "living_env": "Living environment"}
            return {
                "index": "English Indices of Deprivation 2025 (MHCLG)",
                "lsoa": lsoa, "lsoa_name": g.get("lsoa21") or g.get("lsoa"),
                "imd_rank": rec["imd_rank"], "out_of": 33755,
                "imd_decile": rec["imd_decile"],
                "domain_deciles": {names[k]: rec[k] for k in names},
                "note": "Decile 1 = most deprived 10% of neighbourhoods in England, "
                        "10 = least deprived.",
            }
    rank = g.get("index_of_multiple_deprivation")
    if country in NATION_INDEX and isinstance(rank, int):
        label, n = NATION_INDEX[country]
        return {
            "index": label, "lsoa": lsoa, "imd_rank": rank, "out_of": n,
            "imd_decile": min(10, int((rank - 1) * 10 / n) + 1),
            "note": f"Decile derived from the published rank among {n} small areas in "
                    f"{country}; 1 = most deprived. Not comparable across nations.",
        }
    return {"index": None, "note": "No deprivation index found for this postcode."}


def _pick(rows: dict[str, float], *names: str) -> float | None:
    vals = [rows[n] for n in names if n in rows]
    return round(sum(vals), 1) if vals else None


def _shape_census(raw: dict[str, dict[str, dict[str, float]]], geos: dict[str, str],
                  counts: dict[str, dict[str, float]]) -> dict[str, Any]:
    """raw[table][geo_code][category] = percent. counts[table][geo] = total count."""
    def per_geo(fn):
        return {label: fn(code) for label, code in geos.items()}

    def t(table):
        return raw.get(table, {})

    def age(code):
        r = t("age").get(code, {})
        if not r:
            return None
        bands = {
            "0-15": ["Aged 4 years and under", "Aged 5 to 9 years", "Aged 10 to 14 years"],
            "15-24": ["Aged 15 to 19 years", "Aged 20 to 24 years"],
            "25-44": ["Aged 25 to 29 years", "Aged 30 to 34 years", "Aged 35 to 39 years",
                      "Aged 40 to 44 years"],
            "45-64": ["Aged 45 to 49 years", "Aged 50 to 54 years", "Aged 55 to 59 years",
                      "Aged 60 to 64 years"],
            "65+": ["Aged 65 to 69 years", "Aged 70 to 74 years", "Aged 75 to 79 years",
                    "Aged 80 to 84 years", "Aged 85 years and over"],
        }
        return {k: _pick(r, *v) for k, v in bands.items()}

    def tenure(code):
        r = t("tenure").get(code, {})
        return r and {"owned_outright": r.get("Owned: Owns outright"),
                      "owned_mortgage": r.get("Owned: Owns with a mortgage or loan"),
                      "shared_ownership": r.get("Shared ownership"),
                      "social_rented": r.get("Social rented"),
                      "private_rented": r.get("Private rented"),
                      "owner_occupied_total": r.get("Owned")} or None

    def accom(code):
        r = t("accommodation").get(code, {})
        return r and {"detached": r.get("Detached"), "semi_detached": r.get("Semi-detached"),
                      "terraced": r.get("Terraced"),
                      "flats": _pick(r, *[k for k in r if k.startswith(("In a purpose",
                                                                       "Part of"))]),
                      "other": _pick(r, *[k for k in r if k.startswith(("In a commercial",
                                                                       "A caravan"))])} or None

    def cars(code):
        r = t("cars").get(code, {})
        return r and {"no_car": r.get("No cars or vans in household"),
                      "one_car": r.get("1 car or van in household"),
                      "two_plus_cars": _pick(r, "2 cars or vans in household",
                                             "3 or more cars or vans in household")} or None

    def econ(code):
        r = t("economic_activity").get(code, {})
        if not r:
            return None
        return {
            "in_employment": _pick(
                r, "Economically active (excluding full-time students):In employment",
                "Economically active and a full-time student:In employment"),
            "unemployed": _pick(
                r, "Economically active (excluding full-time students): Unemployed",
                "Economically active and a full-time student: Unemployed"),
            "retired": r.get("Economically inactive: Retired"),
            "students_inactive": r.get("Economically inactive: Student"),
            "long_term_sick_or_disabled": r.get("Economically inactive: Long-term sick or "
                                                "disabled"),
        }

    def quals(code):
        r = t("qualifications").get(code, {})
        return r and {"degree_level_or_above": r.get("Level 4 qualifications or above"),
                      "no_qualifications": r.get("No qualifications")} or None

    def health(code):
        r = t("health").get(code, {})
        return r and {"good_or_very_good": _pick(r, "Very good health", "Good health"),
                      "bad_or_very_bad": _pick(r, "Bad health", "Very bad health")} or None

    pop = counts.get("population", {})
    hh = counts.get("tenure", {})
    return {
        "census": "ONS Census 2021 (England & Wales)",
        "units": "percent of residents (age, economic activity, qualifications, health; "
                 "16+ for the latter two) or of households (tenure, accommodation, cars)",
        "areas": dict(geos.items()),
        "usual_residents": per_geo(lambda c: pop.get(c)),
        "households": per_geo(lambda c: hh.get(c)),
        "age_bands_pct": per_geo(age),
        "tenure_pct": per_geo(tenure),
        "accommodation_pct": per_geo(accom),
        "cars_pct": per_geo(cars),
        "economic_activity_pct": per_geo(econ),
        "qualifications_pct": per_geo(quals),
        "health_pct": per_geo(health),
    }


async def census(c: httpx.AsyncClient, g: dict[str, Any]) -> dict[str, Any]:
    """Census 2021 key stats for the LSOA, compared with the local authority and nation."""
    codes = g.get("codes") or {}
    lsoa = codes.get("lsoa21") or codes.get("lsoa")
    geos = {"neighbourhood_lsoa": lsoa}
    if codes.get("admin_district"):
        geos["local_authority"] = codes["admin_district"]
    geos["nation"] = NATION_CODES[g["country"]]
    geo_param = ",".join(geos.values())

    async def table(key, ds, dim):
        txt = await c.get(f"{NOMIS}/{ds}.data.csv", timeout=httpx.Timeout(12.0), params={
            "geography": geo_param, "measures": "20100,20301",
            "select": f"geography_code,{dim}_name,measures_name,obs_value"})
        txt.raise_for_status()
        pct: dict[str, dict[str, float]] = {}
        total: dict[str, float] = {}
        for row in csv.DictReader(txt.text.splitlines()):
            gc, cat = row["GEOGRAPHY_CODE"], row[f"{dim}_NAME"]
            v = float(row["OBS_VALUE"]) if row["OBS_VALUE"] not in ("", None) else None
            if row["MEASURES_NAME"] == "Percent":
                pct.setdefault(gc, {})[cat] = v
            elif cat.startswith("Total") and v is not None:
                total[gc] = int(v)
        return key, pct, total

    res = await asyncio.gather(*(table(k, ds, dim) for k, (ds, dim) in CENSUS_TABLES.items()),
                               return_exceptions=True)
    raw, counts, failed = {}, {}, []
    for k, r in zip(CENSUS_TABLES, res, strict=True):
        if isinstance(r, BaseException):
            failed.append(k)
            continue
        raw[k], counts[k] = r[1], r[2]
    if not raw:
        raise RuntimeError("all Census tables failed")
    # drop comparison areas Nomis does not know (e.g. renamed councils)
    geos = {lab: code for lab, code in geos.items()
            if any(code in raw[t] for t in raw)}
    out = _shape_census(raw, geos, counts)
    if failed:
        out["tables_unavailable"] = failed
    return out


async def nearby_prices(c: httpx.AsyncClient, g: dict[str, Any], own: dict[str, Any] | None,
                        n: int = 6) -> dict[str, Any] | None:
    """Land Registry sales in the closest neighbouring postcodes (within ~400 m)."""
    near = await _get(c, f"https://api.postcodes.io/postcodes/{g['postcode'].replace(' ', '')}"
                         "/nearest", params={"limit": n + 1, "radius": 400})
    pcs = [r["postcode"] for r in (near.get("result") or []) if r["postcode"] != g["postcode"]]
    pcs = pcs[:n]
    if not pcs:
        return None
    res = await asyncio.gather(*(_prices_pc(c, pc, 10, LR_TIMEOUT) for pc in pcs),
                               return_exceptions=True)
    sales = []
    for pc, r in zip(pcs, res, strict=True):
        if isinstance(r, dict):
            for s in r.get("sales", []):
                sales.append({**s, "postcode": pc})
    sales.sort(key=lambda s: s.get("date") or "", reverse=True)
    if own:
        sales = [s for s in sales if s["postcode"] != own.get("postcode")]
    return {"postcodes_searched": pcs, "sales_found": len(sales), "sales": sales}


def _price_stats(sales: list[dict[str, Any]]) -> dict[str, Any]:
    cutoff = (date.today() - timedelta(days=round(5 * 365.25))).isoformat()
    recent = [s["price_gbp"] for s in sales
              if isinstance(s.get("price_gbp"), int | float) and (s.get("date") or "") >= cutoff]
    allp = [s["price_gbp"] for s in sales if isinstance(s.get("price_gbp"), int | float)]
    by_type: dict[str, list[float]] = {}
    for s in sales:
        if (s.get("date") or "") >= cutoff and isinstance(s.get("price_gbp"), int | float):
            by_type.setdefault(s.get("type") or "unknown", []).append(s["price_gbp"])
    return {
        "sales_last_5y": len(recent),
        "median_last_5y_gbp": round(statistics.median(recent)) if recent else None,
        "median_all_gbp": round(statistics.median(allp)) if allp else None,
        "median_by_type_last_5y_gbp": {k: round(statistics.median(v))
                                       for k, v in sorted(by_type.items())},
        "latest_sale": sales[0] if sales else None,
    }


async def house_price_block(c: httpx.AsyncClient, g: dict[str, Any]) -> dict[str, Any]:
    own_t = asyncio.create_task(_prices_pc(c, g["postcode"], 200, LR_TIMEOUT))
    near_t = asyncio.create_task(nearby_prices(c, g, None))
    own, near = await asyncio.gather(own_t, near_t, return_exceptions=True)
    own = own if isinstance(own, dict) else None
    near = near if isinstance(near, dict) else None
    if own is None and near is None:
        raise RuntimeError("Land Registry unavailable")
    own_sales = own["sales"] if own else []
    near_sales = near["sales"] if near else []
    combined = sorted(own_sales + near_sales, key=lambda s: s.get("date") or "", reverse=True)
    return {
        "at_postcode": {**_price_stats(own_sales), "sales_found": len(own_sales),
                        "recent_sales": own_sales[:8]},
        "immediate_area": {"postcodes": [g["postcode"]] + (near or {}).get(
                               "postcodes_searched", []),
                           **_price_stats(combined), "sales_found": len(combined),
                           "recent_sales": combined[:8]},
        "coverage": "England & Wales; residential sales registered with HM Land Registry",
    }


def _fmt_gbp(v: Any) -> str:
    return f"£{v:,.0f}" if isinstance(v, int | float) else "n/a"


def build_summary(r: dict[str, Any]) -> list[str]:
    out: list[str] = []
    loc = r.get("location") or {}
    if loc:
        parts = [loc.get("admin_ward"), loc.get("admin_district"), loc.get("country")]
        rural = loc.get("rural_urban_2021")
        out.append(f"{loc.get('postcode')} is in {', '.join(p for p in parts if p)}"
                   + (f"; rural-urban class: {rural}." if rural else "."))
    dep = r.get("deprivation") or {}
    if dep.get("imd_decile"):
        d = dep["imd_decile"]
        word = ("among the most deprived" if d <= 2 else "more deprived than average" if d <= 4
                else "around average" if d <= 6 else "less deprived than average" if d <= 8
                else "among the least deprived")
        out.append(f"Deprivation: decile {d}/10 ({word}) on the {dep['index']}.")
    dem = r.get("demographics") or {}
    if dem:
        res = (dem.get("usual_residents") or {}).get("neighbourhood_lsoa")
        ten = (dem.get("tenure_pct") or {}).get("neighbourhood_lsoa") or {}
        ten_n = (dem.get("tenure_pct") or {}).get("nation") or {}
        q = (dem.get("qualifications_pct") or {}).get("neighbourhood_lsoa") or {}
        age = (dem.get("age_bands_pct") or {}).get("neighbourhood_lsoa") or {}
        bits = []
        if res:
            bits.append(f"{res:,} residents in the neighbourhood (LSOA)")
        if ten.get("owner_occupied_total") is not None:
            bits.append(f"{ten['owner_occupied_total']}% owner-occupied vs "
                        f"{ten_n.get('owner_occupied_total')}% nationally, "
                        f"{ten.get('private_rented')}% private rented")
        if q.get("degree_level_or_above") is not None:
            bits.append(f"{q['degree_level_or_above']}% degree-level qualified")
        if age.get("65+") is not None:
            bits.append(f"{age['65+']}% aged 65+")
        if bits:
            out.append("Census 2021: " + "; ".join(bits) + ".")
    cr = r.get("crime") or {}
    if cr.get("total_crimes") == 0:
        out.append("Crime: no street-level crimes are published for this location in the "
                   "latest month — this usually means the police force does not currently "
                   "publish to data.police.uk (e.g. Greater Manchester Police), not that the "
                   "area is crime-free.")
    elif cr.get("total_crimes") is not None:
        top = ", ".join(list((cr.get("by_category") or {}).keys())[:3]).replace("-", " ")
        out.append(f"Crime: {cr['total_crimes']} street-level crimes within ~1 mile in "
                   f"{cr.get('month')}; most common: {top or 'n/a'}.")
    fl = r.get("flood") or {}
    if fl.get("active_count") is not None:
        out.append("Flooding: no active Environment Agency alerts or warnings within "
                   f"{fl.get('radius_km'):g} km right now." if fl["active_count"] == 0 else
                   f"Flooding: {fl['active_count']} active Environment Agency alert(s)/"
                   f"warning(s) within {fl.get('radius_km'):g} km — check details.")
    hp = r.get("house_prices") or {}
    area = hp.get("immediate_area") or {}
    if area.get("sales_found"):
        n5 = area.get("sales_last_5y") or 0
        out.append(f"House prices: median {_fmt_gbp(area.get('median_last_5y_gbp'))} over "
                   f"{n5} sale{'s' if n5 != 1 else ''} in the last 5 years across this and "
                   f"neighbouring postcodes (median at this postcode: "
                   f"{_fmt_gbp((hp.get('at_postcode') or {}).get('median_last_5y_gbp'))}).")
    fd = r.get("food_hygiene") or {}
    if fd.get("establishments_found"):
        share = fd.get("share_rated_4_or_5_pct")
        n = fd["establishments_found"]
        out.append(f"Food hygiene: {'200+' if n >= 200 else n} food businesses within "
                   f"{fd.get('radius_miles')} miles"
                   + (f"; {share}% rated 4 or 5." if share is not None else "."))
    missing = [k for k, v in (r.get("sources_status") or {}).items() if not v.get("ok")]
    if missing:
        out.append("Not included: " + ", ".join(missing) + " (see sources_status).")
    return out


# --------------------------------------------------------------------------- tool

async def full_area_intelligence(postcode: str) -> dict[str, Any]:
    """HEADLINE TOOL — the complete UK area-intelligence report for one postcode in a
    single call. Use this first for property due diligence, relocation, lettings,
    insurance pre-screening, site selection or lead enrichment.

    Returns one structured JSON report with:
      • summary — plain-English key findings
      • location — coordinates, ward, council, constituency, region, LSOA/MSOA, rural-urban
      • deprivation — Index of Multiple Deprivation decile (England: IoD 2025 incl. income,
        employment, education, health, crime, housing and living-environment domains)
      • demographics — Census 2021 for the neighbourhood vs the council and the nation:
        population, households, age bands, tenure, housing type, cars, employment,
        qualifications, health (England & Wales)
      • crime — latest month of street crime within ~1 mile by category, hotspots, outcomes
      • flood — live Environment Agency flood alerts/warnings and nearby gauges (England)
      • house_prices — HM Land Registry sold prices at the postcode AND the immediate area
        (neighbouring postcodes): 5-year median, median by property type, recent sales
      • food_hygiene — nearest FSA-rated food businesses and rating spread
      • sources_status and data_sources — per-source status and licence attribution

    Sources are fetched in parallel; if one is unavailable or out of coverage the rest
    of the report is still returned. All data is official UK open data (OGL v3.0).

    Args:
        postcode: Any UK postcode, e.g. "SW1A 1AA" or "m11ae".
    """
    _norm(postcode)  # validate early with a clear message
    status: dict[str, Any] = {}
    async with httpx.AsyncClient(headers=UA, follow_redirects=True) as c:
        g = await _geo(c, postcode)
        status["postcode_lookup"] = {"ok": True}
        country = g.get("country")
        tasks: dict[str, Any] = {}
        if country in ("England", "Wales", "Northern Ireland"):
            tasks["crime"] = _timed("crime", _crime_g(c, g), status)
        else:
            _skip("crime", f"data.police.uk does not cover {country}", status)
        if country == "England":
            tasks["flood"] = _timed("flood", _flood_g(c, g, 5.0), status)
        else:
            _skip("flood", f"Environment Agency live warnings cover England only, not "
                           f"{country}", status)
        tasks["food_hygiene"] = _timed("food_hygiene", _food_g(c, g, 0.5, 10), status)
        if country in ("England", "Wales"):
            tasks["house_prices"] = _timed("house_prices", house_price_block(c, g), status,
                                           timeout=HP_TIMEOUT)
            tasks["demographics"] = _timed("demographics", census(c, g), status)
        else:
            _skip("house_prices", f"HM Land Registry covers England & Wales, not {country}",
                  status)
            _skip("demographics", f"Census 2021 (ONS) covers England & Wales; {country} "
                                  "is not included", status)
        results = dict(zip(tasks, await asyncio.gather(*tasks.values()), strict=True))

    try:
        dep = deprivation(g)
        status["deprivation"] = {"ok": dep.get("index") is not None}
    except Exception as e:  # noqa: BLE001
        dep = None
        status["deprivation"] = {"ok": False, "error": f"{type(e).__name__}: {e}"[:200]}

    crime = results.get("crime")
    if crime and crime.get("total_crimes") == 0:
        crime["note"] = ("No crimes published for this point in the latest month. Some forces "
                         "(notably Greater Manchester Police) do not currently publish "
                         "street-level data, so zero does not mean crime-free.")

    food = results.get("food_hygiene")
    if food:
        dist = food.get("rating_distribution") or {}
        numeric = {k: v for k, v in dist.items() if k.isdigit()}
        n = sum(numeric.values())
        if n:
            food["share_rated_4_or_5_pct"] = round(
                100 * (numeric.get("4", 0) + numeric.get("5", 0)) / n, 1)

    location = {
        "postcode": g.get("postcode"), "latitude": g.get("latitude"),
        "longitude": g.get("longitude"), "country": country, "region": g.get("region"),
        "admin_district": g.get("admin_district"), "admin_county": g.get("admin_county"),
        "admin_ward": g.get("admin_ward"), "parish": g.get("parish"),
        "parliamentary_constituency": g.get("parliamentary_constituency_2024")
        or g.get("parliamentary_constituency"),
        "police_force_area": g.get("pfa"), "built_up_area": g.get("bua"),
        "lsoa_2021": g.get("lsoa21") or g.get("lsoa"),
        "msoa_2021": g.get("msoa21") or g.get("msoa"),
        "rural_urban_2021": g.get("ruc21") or g.get("rural_urban"),
        "national_park": g.get("national_park"),
        "codes": {k: (g.get("codes") or {}).get(k) for k in
                  ("admin_district", "admin_ward", "lsoa21", "msoa21", "oa21",
                   "parliamentary_constituency_2024")},
    }
    report: dict[str, Any] = {
        "report": "UK Postcode Intel — Full Area Intelligence",
        "postcode": g.get("postcode"),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "summary": [],
        "location": location,
        "deprivation": dep,
        "demographics": results.get("demographics"),
        "crime": results.get("crime"),
        "flood": results.get("flood"),
        "house_prices": results.get("house_prices"),
        "food_hygiene": food,
        "sources_status": status,
        "data_sources": ATTRIBUTION,
    }
    report["summary"] = build_summary(report)
    return report
