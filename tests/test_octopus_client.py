import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from wattson.octopus import BASE_URL, OctopusClient

FIXTURE = Path(__file__).parent / "fixtures" / "agile_rates_D_2026-11-26.json"
START = datetime(2026, 11, 26, 0, 0, tzinfo=UTC)
END = datetime(2026, 11, 26, 23, 0, tzinfo=UTC)


def make_client(handler) -> OctopusClient:
    http = httpx.Client(base_url=BASE_URL, transport=httpx.MockTransport(handler))
    return OctopusClient(http=http)


def test_region_for_postcode():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["postcode"] = request.url.params["postcode"]
        body = {
            "count": 1,
            "next": None,
            "previous": None,
            "results": [{"group_id": "_D"}],
        }
        return httpx.Response(200, json=body)

    assert make_client(handler).region_for("l1 8jq") == "D"
    assert seen["postcode"] == "L1"


def test_unknown_postcode_raises():
    empty = {"count": 0, "next": None, "previous": None, "results": []}
    client = make_client(lambda request: httpx.Response(200, json=empty))

    with pytest.raises(ValueError):
        client.region_for("ZZ99")


def test_agile_rates_from_real_fixture():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = request.url
        return httpx.Response(200, json=json.loads(FIXTURE.read_text()))

    rates = make_client(handler).agile_rates("D", START, END)

    assert seen["url"].path.endswith("/E-1R-AGILE-24-10-01-D/standard-unit-rates/")
    assert seen["url"].params["period_from"] == "2026-11-26T00:00Z"
    assert len(rates) == 46
    assert rates[0].valid_from < rates[-1].valid_from  # sorted oldest-first
    assert min(r.value_inc_vat for r in rates) == 32.92


def test_agile_rates_follows_every_page():
    def rate(hour: int, price: float) -> dict:
        return {
            "value_exc_vat": price,
            "value_inc_vat": price,
            "valid_from": f"2026-11-26T{hour:02d}:00:00Z",
            "valid_to": f"2026-11-26T{hour:02d}:30:00Z",
            "payment_method": None,
        }

    page_2_url = f"{BASE_URL}/next-page/?page=2"
    pages = {
        "1": {
            "count": 2,
            "next": page_2_url,
            "previous": None,
            "results": [rate(9, 20.0)],
        },
        "2": {"count": 2, "next": None, "previous": None, "results": [rate(8, 10.0)]},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=pages[request.url.params.get("page", "1")])

    rates = make_client(handler).agile_rates("D", START, END)

    assert [r.value_inc_vat for r in rates] == [10.0, 20.0]  # both pages, sorted
