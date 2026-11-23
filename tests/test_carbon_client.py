import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from wattson.carbon import BASE_URL, CarbonIntensityClient

FIXTURE = Path(__file__).parent / "fixtures" / "carbon_fw48h_L1.json"


def make_client(handler) -> CarbonIntensityClient:
    """A client whose 'internet' is our handler function."""
    http = httpx.Client(base_url=BASE_URL, transport=httpx.MockTransport(handler))
    return CarbonIntensityClient(http=http)


def test_builds_url_and_parses_response():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(200, json=json.loads(FIXTURE.read_text()))

    client = make_client(handler)
    forecast = client.forecast_48h(
        "l1 8jq", start=datetime(2026, 11, 23, 8, 0, tzinfo=UTC)
    )

    assert seen["path"] == "/regional/intensity/2026-11-23T08:00Z/fw48h/postcode/L1"
    assert len(forecast.data) == 96


def test_raises_on_server_error():
    client = make_client(lambda request: httpx.Response(500))

    with pytest.raises(httpx.HTTPStatusError):
        client.forecast_48h("L1")
