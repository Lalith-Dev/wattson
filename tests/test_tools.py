import json
from datetime import UTC, datetime
from pathlib import Path

from wattson.carbon import RegionalForecastResponse
from wattson.octopus import UnitRate
from wattson.tools import TOOL_SPECS, EnergyTools, uk_time

FIXTURES = Path(__file__).parent / "fixtures"


class FakeCarbon:
    """Stands in for CarbonIntensityClient and replays the saved forecast."""

    def forecast_48h(self, postcode, start=None):
        raw = json.loads((FIXTURES / "carbon_fw48h_L1.json").read_text())
        return RegionalForecastResponse.model_validate(raw).data


class FakeOctopus:
    """Stands in for OctopusClient and replays saved prices inside the window."""

    def region_for(self, postcode):
        return "D"

    def agile_rates(self, region, start, end):
        raw = json.loads((FIXTURES / "agile_rates_D_2026-11-26.json").read_text())
        rates = [UnitRate.model_validate(r) for r in raw["results"]]
        return [r for r in rates if r.valid_to > start and r.valid_from < end]


def tools_at(moment: datetime) -> EnergyTools:
    return EnergyTools(carbon=FakeCarbon(), octopus=FakeOctopus(), now=lambda: moment)


def test_uk_time_formats_in_local_time():
    assert uk_time(datetime(2026, 11, 26, 22, 30, tzinfo=UTC)) == "Thu 26 Nov 22:30"
    assert uk_time(datetime(2026, 7, 1, 12, 0, tzinfo=UTC)) == "Wed 01 Jul 13:00"  # BST


def test_greenest_times_picks_lowest_carbon():
    result = tools_at(datetime(2026, 11, 23, 8, 0, tzinfo=UTC)).greenest_times(
        "L1", hours_ahead=48, top=1
    )

    assert result["region"] == "North Wales & Merseyside"
    assert result["slots"][0]["gco2_per_kwh"] == 39


def test_cheapest_times_flags_unpublished_prices():
    result = tools_at(datetime(2026, 11, 26, 12, 0, tzinfo=UTC)).cheapest_times(
        "L1", hours_ahead=24
    )

    assert result["slots"][0]["pence_per_kwh"] == 32.92
    assert result["prices_published_until"] == "Thu 26 Nov 23:00"
    assert "later slots are unknown" in result["note"]


def test_cheapest_times_when_nothing_published():
    result = tools_at(datetime(2026, 11, 28, 0, 0, tzinfo=UTC)).cheapest_times("L1")

    assert result["slots"] == []
    assert "not published yet" in result["note"]


def test_specs_are_valid_json_schema_shapes():
    names = [spec["function"]["name"] for spec in TOOL_SPECS]

    assert names == ["get_greenest_times", "get_cheapest_times"]
    for spec in TOOL_SPECS:
        assert spec["function"]["parameters"]["required"] == ["postcode"]
