"""Data models for NESO's Carbon Intensity API."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

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