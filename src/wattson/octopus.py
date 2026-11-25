"""Client and models for Octopus Energy's public API (Agile prices)."""

from collections.abc import Iterator
from datetime import UTC, datetime

import httpx
from pydantic import BaseModel

BASE_URL = "https://api.octopus.energy/v1"
AGILE_PRODUCT = "AGILE-24-10-01"  # import tariff; Octopus renames this now and then


class UnitRate(BaseModel):
    value_exc_vat: float  # pence per kWh
    value_inc_vat: float  # what the customer actually pays
    valid_from: datetime
    valid_to: datetime


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%MZ")


class OctopusClient:
    """Looks up a postcode's region and its half-hourly Agile prices."""

    def __init__(self, http: httpx.Client | None = None) -> None:
        self._http = http or httpx.Client(base_url=BASE_URL, timeout=10.0)

    def _paginate(self, url: str, params: dict | None = None) -> Iterator[dict]:
        """Yield every result across all pages, following each 'next' link."""
        while url:
            response = self._http.get(url, params=params)
            response.raise_for_status()
            page = response.json()
            yield from page["results"]
            url = page["next"]  # None on the last page, which ends the loop
            params = None  # the 'next' link already contains the query string

    def region_for(self, postcode: str) -> str:
        outward = postcode.strip().upper().split()[0]  # "l1 8jq" -> "L1"
        results = list(
            self._paginate("/industry/grid-supply-points/", {"postcode": outward})
        )
        if not results:
            raise ValueError(f"No Octopus region found for postcode {postcode!r}")
        return results[0]["group_id"].lstrip("_")  # "_D" -> "D"

    def agile_rates(
        self,
        region: str,
        start: datetime,
        end: datetime,
        product: str = AGILE_PRODUCT,
    ) -> list[UnitRate]:
        tariff = f"E-1R-{product}-{region}"
        url = f"/products/{product}/electricity-tariffs/{tariff}/standard-unit-rates/"
        params = {"period_from": _iso(start), "period_to": _iso(end)}

        rates = [UnitRate.model_validate(r) for r in self._paginate(url, params)]
        return sorted(rates, key=lambda rate: rate.valid_from)  # API is newest-first
