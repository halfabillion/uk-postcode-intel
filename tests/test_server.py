from fastmcp import Client

from uk_postcode_intel.server import mcp


async def test_lists_tools():
    async with Client(mcp) as c:
        names = {t.name for t in await c.list_tools()}
    assert "area_report" in names and "house_prices" in names


async def test_seven_tools_with_headline():
    async with Client(mcp) as c:
        tools = await c.list_tools()
    names = [t.name for t in tools]
    assert set(names) == {"full_area_intelligence", "area_report", "postcode_lookup",
                          "crime_summary", "flood_warnings", "food_hygiene_nearby",
                          "house_prices"}
    head = next(t for t in tools if t.name == "full_area_intelligence")
    assert head.description.startswith("HEADLINE TOOL")
