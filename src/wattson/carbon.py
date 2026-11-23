"""Data models for NESO's Carbon Intensity API."""

from datetime import UTC, datetime
from typing import Literal

import httpx
from pydantic import BaseModel, Field

BASE_URL = "https://api.carbonintensity.org.uk"

IntensityIndex = Literal["very low", "low", "moderate", "high", "very high"]


class Intensity(BaseModel):
    forecast: int  # gCO2/kWh
    index: IntensityIndex


class FuelShare(BaseModel):
    fuel: str
    perc: float


class HalfHour(BaseModel):
    start: datetime = Field(alias="from")
    end: datetime = Field(alias="to")
    intensity: Intensity
    generationmix: list[FuelShare]


class RegionalForecast(BaseModel):
    regionid: int
    dnoregion: str
    shortname: str
    postcode: str
    data: list[HalfHour]


class RegionalForecastResponse(BaseModel):
    data: RegionalForecast


class CarbonIntensityClient:
    """Fetches regional carbon intensity forecasts from NESO's API."""

    def __init__(self, http: httpx.Client | None = None) -> None:
        self._http = http or httpx.Client(base_url=BASE_URL, timeout=10.0)

    def forecast_48h(
        self, postcode: str, start: datetime | None = None
    ) -> RegionalForecast:
        outward = postcode.strip().upper().split()[0]  # "l1 8jq" -> "L1"
        start = (start or datetime.now(UTC)).astimezone(UTC)
        timestamp = start.strftime("%Y-%m-%dT%H:%MZ")

        response = self._http.get(
            f"/regional/intensity/{timestamp}/fw48h/postcode/{outward}"
        )
        response.raise_for_status()
        return RegionalForecastResponse.model_validate(response.json()).data
