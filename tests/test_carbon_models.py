import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from wattson.carbon import RegionalForecastResponse

FIXTURE = Path(__file__).parent / "fixtures" / "carbon_fw48h_L1.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text())


def test_parses_real_response():
    forecast = RegionalForecastResponse.model_validate(load_fixture()).data

    assert forecast.shortname == "North Wales & Merseyside"
    assert forecast.dnoregion == "SP Manweb"
    assert len(forecast.data) == 96  # 48 hours x 2 half-hours
    first = forecast.data[0]
    assert first.intensity.forecast == 209
    assert first.intensity.index == "high"
    assert first.start.tzinfo is not None  # times are timezone-aware (UTC)


def test_rejects_unknown_index():
    raw = load_fixture()
    raw["data"]["data"][0]["intensity"]["index"] = "spicy"

    with pytest.raises(ValidationError):
        RegionalForecastResponse.model_validate(raw)