"""UK postcode intelligence tools built on official open government data."""

import asyncio
import re
from collections import Counter
from datetime import datetime
from typing import Any

import httpx

UA = {"User-Agent": "uk-postcode-intel/1.0 (+https://mcpize.com)"}
TIMEOUT = httpx.Timeout(40.0)


def _norm(postcode: str) -> str:
    pc = re.sub(r"\s+", "", postcode or "").upper()
    if not re.fullmatch(r"[A-Z]{1,2}[0-9][A-Z0-9]?[0-9][A-Z]{2}", pc):
        raise ValueError(f"'{postcode}' is not a valid UK postcode")
    return pc[:-3] + " " + pc[-3:]


async def _get(client: httpx.AsyncClient, url: str, **kw) -> Any:
    kw.setdefault("timeout", TIMEOUT)
    r = await client.get(url, **kw)
    r.raise_for_status()
    return r.json()


async def _geo(client: httpx.AsyncClient, postcode: str) -> dict[str, Any]:
    pc = _norm(postcode)
    d = (await _get(client, f"https://api.postcodes.io/postcodes/{pc.replace(' ', '')}"))["result"]
    return d


async def postcode_lookup(postcode: str) -> dict[str, Any]:
    """Look up a UK postcode: coordinates, local authority, ward, constituency, region,
    LSOA/MSOA codes and country (source: ONS via postcodes.io).

    Args:
        postcode: Any UK postcode, e.g. "SW1A 1AA".
    """
    async with httpx.AsyncClient(headers=UA) as c:
        d = await _geo(c, postcode)
    keys = ["postcode", "latitude", "longitude", "country", "region", "admin_district",
            "admin_ward", "parish", "parliamentary_constituency", "lsoa", "msoa",
            "admin_county", "rural_urban" ]
    out = {k: d.get(k) for k in keys if k in d}
    out["codes"] = d.get("codes")
    return out


async def crime_summary(postcode: str) -> dict[str, Any]:
    """Street-level crime near a postcode (about 1 mile radius) for the latest month
    published by data.police.uk, counted by category, with top streets.
    England, Wales and Northern Ireland only.

    Args:
        postcode: UK postcode.
    """
    async with httpx.AsyncClient(headers=UA) as c:
        g = await _geo(c, postcode)
        return await _crime_g(c, g)


async def _crime_g(c: httpx.AsyncClient, g: dict[str, Any]) -> dict[str, Any]:
    rows = await _get(c, "https://data.police.uk/api/crimes-street/all-crime",
                      params={"lat": g["latitude"], "lng": g["longitude"]})
    cats = Counter(r["category"] for r in rows)
    streets = Counter((r.get("location") or {}).get("street", {}).get("name", "?") for r in rows)
    outcomes = Counter(((r.get("outcome_status") or {}).get("category")) or "No outcome recorded"
                       for r in rows)
    return {
        "postcode": g["postcode"],
        "month": rows[0]["month"] if rows else None,
        "total_crimes": len(rows),
        "by_category": dict(cats.most_common()),
        "top_locations": dict(streets.most_common(5)),
        "outcomes": dict(outcomes.most_common(6)),
        "radius": "approx. 1 mile",
        "source": "data.police.uk (Open Government Licence)",
    }


async def flood_warnings(postcode: str, radius_km: float = 5.0) -> dict[str, Any]:
    """Live Environment Agency flood alerts/warnings and nearby monitoring stations
    for a postcode in England.

    Args:
        postcode: UK postcode (England coverage).
        radius_km: Search radius in km (default 5, max 50).
    """
    async with httpx.AsyncClient(headers=UA) as c:
        g = await _geo(c, postcode)
        return await _flood_g(c, g, radius_km)


async def _flood_g(c: httpx.AsyncClient, g: dict[str, Any],
                   radius_km: float = 5.0) -> dict[str, Any]:
    radius_km = max(1.0, min(float(radius_km), 50.0))
    base = "https://environment.data.gov.uk/flood-monitoring"
    p = {"lat": g["latitude"], "long": g["longitude"], "dist": radius_km}
    floods, stations = await asyncio.gather(
        _get(c, f"{base}/id/floods", params=p),
        _get(c, f"{base}/id/stations", params={**p, "_limit": 10}),
    )
    sev = {1: "Severe flood warning", 2: "Flood warning", 3: "Flood alert", 4: "No longer in force"}
    return {
        "postcode": g["postcode"],
        "radius_km": radius_km,
        "active_count": len(floods.get("items", [])),
        "active": [{
            "area": f.get("description"),
            "severity": sev.get(f.get("severityLevel"), f.get("severity")),
            "message": (f.get("message") or "")[:400],
            "raised": f.get("timeRaised"),
        } for f in floods.get("items", [])],
        "nearby_stations": [{
            "label": s.get("label"), "river": s.get("riverName"), "town": s.get("town"),
        } for s in stations.get("items", [])[:10]],
        "source": "Environment Agency real-time flood-monitoring API (OGL)",
    }


async def food_hygiene_nearby(postcode: str, radius_miles: float = 0.5,
                              limit: int = 15) -> dict[str, Any]:
    """Food hygiene ratings (FSA) of food businesses nearest a postcode, plus the
    rating distribution. Useful for restaurant, cafe and takeaway checks.

    Args:
        postcode: UK postcode.
        radius_miles: Radius in miles (default 0.5, max 5).
        limit: Number of establishments to list (default 15, max 50).
    """
    async with httpx.AsyncClient(headers=UA) as c:
        g = await _geo(c, postcode)
        return await _food_g(c, g, radius_miles, limit)


FSA_HEADERS = {"x-api-version": "2", "accept": "application/json"}


async def _food_g(c: httpx.AsyncClient, g: dict[str, Any], radius_miles: float = 0.5,
                  limit: int = 15) -> dict[str, Any]:
    radius_miles = max(0.1, min(float(radius_miles), 5.0))
    limit = max(1, min(int(limit), 50))
    d = await _get(c, "https://api.ratings.food.gov.uk/Establishments", headers=FSA_HEADERS,
                   params={"latitude": g["latitude"], "longitude": g["longitude"],
                           "maxDistanceLimit": radius_miles, "sortOptionKey": "distance",
                           "pageSize": 200})
    est = d.get("establishments", [])
    dist = Counter(str(e.get("RatingValue")) for e in est)
    return {
        "postcode": g["postcode"],
        "radius_miles": radius_miles,
        "establishments_found": len(est),
        "rating_distribution": dict(sorted(dist.items())),
        "nearest": [{
            "name": e.get("BusinessName"), "type": e.get("BusinessType"),
            "rating": e.get("RatingValue"), "rated_on": (e.get("RatingDate") or "")[:10],
            "address": ", ".join(x for x in [e.get("AddressLine1"), e.get("AddressLine2"),
                                               e.get("PostCode")] if x),
            "distance_miles": round(e.get("Distance") or 0, 2),
        } for e in est[:limit]],
        "source": "Food Standards Agency ratings API (OGL)",
    }


def _iso(v: Any) -> Any:
    try:
        return datetime.strptime(str(v), "%a, %d %b %Y").date().isoformat()
    except ValueError:
        return v


async def house_prices(postcode: str, limit: int = 20) -> dict[str, Any]:
    """Recorded residential sale prices for a postcode from HM Land Registry
    Price Paid Data (England & Wales): newest first, with median and range.

    Args:
        postcode: UK postcode (England or Wales).
        limit: Maximum sales returned (default 20, max 100).
    """
    pc = _norm(postcode)
    async with httpx.AsyncClient(headers=UA) as c:
        return await _prices_pc(c, pc, limit)


async def _prices_pc(c: httpx.AsyncClient, pc: str, limit: int = 20,
                     timeout: httpx.Timeout | None = None) -> dict[str, Any]:
    limit = max(1, min(int(limit), 100))
    d = await _get(c, "https://landregistry.data.gov.uk/data/ppi/transaction-record.json",
                   params={"propertyAddress.postcode": pc, "_pageSize": 200,
                           "_sort": "-transactionDate"},
                   **({"timeout": timeout} if timeout else {}))
    items = d.get("result", {}).get("items", [])

    def lab(v):
        if isinstance(v, dict):
            p = v.get("prefLabel") or v.get("label")
            if isinstance(p, list):
                p = p[0]
            if isinstance(p, dict):
                p = p.get("_value")
            return p
        return v

    sales = []
    for it in items:
        a = it.get("propertyAddress", {}) or {}
        sales.append({
            "date": _iso(it.get("transactionDate")), "price_gbp": it.get("pricePaid"),
            "address": " ".join(str(x) for x in [a.get("paon"), a.get("saon"), a.get("street"),
                                                   a.get("town")] if x),
            "type": lab(it.get("propertyType")), "tenure": lab(it.get("estateType")),
            "new_build": it.get("newBuild"),
        })
    sales.sort(key=lambda s: s["date"] or "", reverse=True)
    prices = sorted(s["price_gbp"] for s in sales if isinstance(s["price_gbp"], (int, float)))
    med = prices[len(prices) // 2] if prices else None
    return {
        "postcode": pc, "sales_found": len(sales), "median_gbp": med,
        "min_gbp": prices[0] if prices else None, "max_gbp": prices[-1] if prices else None,
        "sales": sales[:limit],
        "source": "HM Land Registry Price Paid Data (OGL)",
    }


async def area_report(postcode: str) -> dict[str, Any]:
    """One-call due-diligence report for a UK postcode: location & admin areas, recent
    crime, live flood warnings, food hygiene nearby and Land Registry sale prices.
    Ideal for property searches, relocation, site selection and lead enrichment.

    Args:
        postcode: UK postcode.
    """
    async def safe(coro):
        try:
            return await coro
        except Exception as e:  # noqa: BLE001
            return {"error": f"{type(e).__name__}: {e}"[:200]}

    loc, crime, flood, food, prices = await asyncio.gather(
        safe(postcode_lookup(postcode)), safe(crime_summary(postcode)),
        safe(flood_warnings(postcode)), safe(food_hygiene_nearby(postcode, 0.5, 5)),
        safe(house_prices(postcode, 10)))
    return {"location": loc, "crime": crime, "flood": flood, "food_hygiene": food,
            "house_prices": prices}
