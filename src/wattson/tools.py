"""Tools the agent can call. Code does the maths; the LLM does the talking."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from wattson.carbon import CarbonIntensityClient
from wattson.octopus import OctopusClient

UK = ZoneInfo("Europe/London")


def uk_time(moment: datetime) -> str:
    """'Thu 26 Nov 22:30' in UK local time, so the LLM never converts timezones."""
    return moment.astimezone(UK).strftime("%a %d %b %H:%M")


class EnergyTools:
    def __init__(
        self,
        carbon: CarbonIntensityClient | None = None,
        octopus: OctopusClient | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.carbon = carbon or CarbonIntensityClient()
        self.octopus = octopus or OctopusClient()
        self.now = now or (lambda: datetime.now(UTC))

    def greenest_times(
        self, postcode: str, hours_ahead: int = 24, top: int = 3
    ) -> dict[str, Any]:
        now = self.now()
        horizon = now + timedelta(hours=min(max(hours_ahead, 1), 48))
        forecast = self.carbon.forecast_48h(postcode, start=now)

        upcoming = [h for h in forecast.data if h.end > now and h.start < horizon]
        best = sorted(upcoming, key=lambda h: h.intensity.forecast)[:top]
        return {
            "region": forecast.shortname,
            "slots": [
                {
                    "start": uk_time(h.start),
                    "end": uk_time(h.end),
                    "gco2_per_kwh": h.intensity.forecast,
                    "index": h.intensity.index,
                }
                for h in best
            ],
        }

    def cheapest_times(
        self, postcode: str, hours_ahead: int = 24, top: int = 3
    ) -> dict[str, Any]:
        now = self.now()
        horizon = now + timedelta(hours=min(max(hours_ahead, 1), 48))
        region = self.octopus.region_for(postcode)
        rates = self.octopus.agile_rates(region, now, horizon)

        if not rates:
            return {
                "region": region,
                "slots": [],
                "note": "Agile prices for this period are not published yet. "
                "Next-day prices usually appear around 4pm UK time.",
            }

        best = sorted(rates, key=lambda r: r.value_inc_vat)[:top]
        published_until = max(r.valid_to for r in rates)
        result: dict[str, Any] = {
            "region": region,
            "prices_published_until": uk_time(published_until),
            "slots": [
                {
                    "start": uk_time(r.valid_from),
                    "end": uk_time(r.valid_to),
                    "pence_per_kwh": r.value_inc_vat,
                }
                for r in best
            ],
        }
        if published_until < horizon:
            result["note"] = (
                f"Prices are only published up to {uk_time(published_until)}; "
                "later slots are unknown, so a cheaper time may still appear."
            )
        return result


def _spec(name: str, description: str) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {
                    "postcode": {
                        "type": "string",
                        "description": "UK postcode or outward code, e.g. 'L1'",
                    },
                    "hours_ahead": {
                        "type": "integer",
                        "description": "How many hours ahead to search (1-48)",
                    },
                    "top": {
                        "type": "integer",
                        "description": "How many best slots to return",
                    },
                },
                "required": ["postcode"],
            },
        },
    }


TOOL_SPECS = [
    _spec(
        "get_greenest_times",
        "Find the half-hour slots with the lowest carbon intensity (gCO2/kWh) "
        "for a UK postcode area. Times are UK local time.",
    ),
    _spec(
        "get_cheapest_times",
        "Find the cheapest half-hour Octopus Agile electricity prices "
        "(pence/kWh, VAT included) for a UK postcode area. Times are UK local time.",
    ),
]
