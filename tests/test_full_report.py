import asyncio
import os

import pytest

from uk_postcode_intel import full_report as fr
from uk_postcode_intel.full_report import _shape_census, build_summary, deprivation

GEO_EN = {
    "postcode": "M1 1AE", "country": "England", "latitude": 53.48, "longitude": -2.23,
    "admin_district": "Manchester", "admin_ward": "Piccadilly", "lsoa21": "Manchester 055F",
    "ruc21": "Urban", "index_of_multiple_deprivation": 10952,
    "codes": {"lsoa21": "E01034129", "admin_district": "E08000003"},
}


def test_deprivation_england_uses_iod2025():
    d = deprivation(GEO_EN)
    assert d["index"].startswith("English Indices of Deprivation 2025")
    assert d["imd_rank"] == 15371 and d["imd_decile"] == 5 and d["out_of"] == 33755
    assert set(d["domain_deciles"]) >= {"Income", "Crime", "Living environment"}


def test_deprivation_other_nations_decile_from_rank():
    w = deprivation({"country": "Wales", "index_of_multiple_deprivation": 1,
                     "codes": {"lsoa21": "W0"}})
    assert w["imd_decile"] == 1
    s = deprivation({"country": "Scotland", "index_of_multiple_deprivation": 6976,
                     "codes": {}})
    assert s["imd_decile"] == 10
    assert deprivation({"country": "Narnia", "codes": {}})["index"] is None


def test_census_shaping():
    raw = {
        "tenure": {"L": {"Owned": 25.0, "Private rented": 70.5,
                         "Owned: Owns outright": 5.8}},
        "cars": {"L": {"No cars or vans in household": 57.6,
                       "2 cars or vans in household": 6.0,
                       "3 or more cars or vans in household": 0.8}},
        "age": {"L": {"Aged 65 to 69 years": 0.6, "Aged 85 years and over": 0.4}},
    }
    out = _shape_census(raw, {"neighbourhood_lsoa": "L"}, {"population": {"L": 1082}})
    assert out["usual_residents"]["neighbourhood_lsoa"] == 1082
    assert out["tenure_pct"]["neighbourhood_lsoa"]["private_rented"] == 70.5
    assert out["cars_pct"]["neighbourhood_lsoa"]["two_plus_cars"] == 6.8
    assert out["age_bands_pct"]["neighbourhood_lsoa"]["65+"] == 1.0


def test_summary_handles_missing_and_zero_crime():
    s = build_summary({"location": {"postcode": "M1 1AE", "country": "England"},
                       "crime": {"total_crimes": 0},
                       "sources_status": {"flood": {"ok": False, "error": "timed out"}}})
    text = " ".join(s)
    assert "not that the area is crime-free" in text and "Not included: flood" in text


async def test_degrades_gracefully_when_sources_fail(monkeypatch):
    async def fake_geo(c, pc):
        return dict(GEO_EN)

    async def boom(*a, **k):
        raise RuntimeError("source down")

    async def slow(*a, **k):
        await asyncio.sleep(5)

    monkeypatch.setattr(fr, "_geo", fake_geo)
    monkeypatch.setattr(fr, "_crime_g", boom)
    monkeypatch.setattr(fr, "_flood_g", slow)
    monkeypatch.setattr(fr, "_food_g", boom)
    monkeypatch.setattr(fr, "house_price_block", boom)
    monkeypatch.setattr(fr, "census", boom)
    monkeypatch.setattr(fr, "SOURCE_TIMEOUT", 0.2)
    r = await fr.full_area_intelligence("M1 1AE")
    st = r["sources_status"]
    assert st["crime"]["ok"] is False and "source down" in st["crime"]["error"]
    assert st["flood"]["error"] == "timed out"
    assert r["deprivation"]["imd_decile"] == 5  # bundled data still works
    assert r["location"]["postcode"] == "M1 1AE" and r["summary"]
    assert len(r["data_sources"]) >= 7


async def test_invalid_postcode():
    with pytest.raises(ValueError):
        await fr.full_area_intelligence("not a postcode")


LIVE = pytest.mark.skipif(os.getenv("LIVE") != "1", reason="set LIVE=1 for network tests")


@LIVE
@pytest.mark.parametrize("pc,country", [("SW1A 1AA", "England"), ("M1 1AE", "England"),
                                        ("EH1 1YZ", "Scotland"), ("CF10 1EP", "Wales")])
async def test_live_postcodes(pc, country):
    r = await fr.full_area_intelligence(pc)
    assert r["location"]["country"] == country
    assert r["deprivation"]["imd_decile"] in range(1, 11)
    assert r["food_hygiene"]["establishments_found"] > 0
    if country in ("England", "Wales"):
        assert r["demographics"]["usual_residents"]["neighbourhood_lsoa"] > 0
        assert r["sources_status"]["house_prices"]["ok"]
        assert r["sources_status"]["crime"]["ok"]
    else:
        assert r["sources_status"]["demographics"].get("skipped")
