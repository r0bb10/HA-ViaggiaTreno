"""Small asynchronous client for the public ViaggiaTreno website API.

No website HTML is fetched or parsed. All train information is JSON.
"""

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

import aiohttp

from .const import BASE_URL

ROME = ZoneInfo("Europe/Rome")
STATION_ID = re.compile(r"S\d{5}\Z")
USER_AGENT = "Mozilla/5.0 (compatible; ViaggiaTreno; HomeAssistant)"


class ViaggiaTrenoError(Exception):
    """Invalid or unavailable upstream response."""


class RateLimited(ViaggiaTrenoError):
    """The server requested a pause."""

    def __init__(self, retry_after: int = 300) -> None:
        super().__init__("ViaggiaTreno rate limited the request")
        self.retry_after = retry_after


@dataclass(frozen=True)
class Station:
    """A station returned by the upstream autocomplete endpoint."""

    id: str
    name: str


def request_date(now: datetime) -> str:
    """Format an English, Rome-local date without process locale dependencies."""
    local = now.astimezone(ROME)
    weekdays = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    months = (
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    )
    return (
        f"{weekdays[local.weekday()]} {months[local.month - 1]} "
        f"{local.day:02d} {local.year} {local:%H:%M:%S} GMT{local:%z}"
    )


class ViaggiaTrenoClient:
    """Read-only API client using Home Assistant's shared HTTP session."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def _get(self, path: str) -> str:
        try:
            async with asyncio.timeout(20):
                async with self._session.get(
                    f"{BASE_URL}/{path}",
                    # The website rejects aiohttp's default User-Agent with 403.
                    headers={
                        "Accept": "application/json, text/plain",
                        "User-Agent": USER_AGENT,
                    },
                ) as response:
                    if response.status == 429:
                        retry = response.headers.get("Retry-After", "300")
                        raise RateLimited(
                            min(max(int(retry), 30), 3600) if retry.isdigit() else 300
                        )
                    response.raise_for_status()
                    # Reject unexpectedly large or non-API responses.
                    body = bytearray()
                    async for chunk in response.content.iter_chunked(65536):
                        body.extend(chunk)
                        if len(body) > 2_000_000:
                            raise ViaggiaTrenoError("API response exceeded size limit")
                    return body.decode("utf-8-sig")
        except (aiohttp.ClientError, TimeoutError, UnicodeError) as err:
            raise ViaggiaTrenoError("Cannot reach ViaggiaTreno") from err

    async def search_stations(self, query: str) -> list[Station]:
        """Resolve a station name using the plain-text autocomplete API."""
        if not query.strip():
            return []
        text = await self._get(f"autocompletaStazione/{quote(query.strip(), safe='')}")
        stations: dict[str, Station] = {}
        for line in text.splitlines():
            name, sep, code = line.rpartition("|")
            if sep and name.strip() and STATION_ID.fullmatch(code.strip()):
                code = code.strip()
                stations[code] = Station(code, name.strip())
        if text.strip() and not stations:
            raise ViaggiaTrenoError("Invalid station search response")
        return sorted(stations.values(), key=lambda station: station.name)

    async def last_report(self, train: dict) -> dict:
        """Fetch a single service's last observed location, only on demand."""
        from .models import _timestamp

        origin = str(train.get("origin_station_id") or "")
        number = str(train.get("train_number") or "")
        date = str(train.get("service_timestamp") or "")
        if (
            not STATION_ID.fullmatch(origin)
            or not re.fullmatch(r"\d{1,10}", number)
            or not re.fullmatch(r"\d{1,16}", date)
        ):
            raise ViaggiaTrenoError("Service identity unavailable")
        try:
            data = json.loads(
                await self._get(f"andamentoTreno/{origin}/{number}/{date}")
            )
        except ValueError as err:
            raise ViaggiaTrenoError("Invalid train detail JSON") from err
        if not isinstance(data, dict):
            raise ViaggiaTrenoError("Invalid train detail response")
        station = data.get("stazioneUltimoRilevamento")
        timestamp = _timestamp(data.get("oraUltimoRilevamento"))
        return {
            "station": station.strip() if isinstance(station, str) else None,
            "timestamp": timestamp,
        }

    async def board(self, station_id: str, direction: str, now: datetime) -> list[dict]:
        """Return one board, validating it before replacing any current data."""
        if not STATION_ID.fullmatch(station_id) or direction not in {
            "arrivi",
            "partenze",
        }:
            raise ValueError("Invalid station or board direction")
        text = await self._get(
            f"{direction}/{station_id}/{quote(request_date(now), safe='')}"
        )
        try:
            data = json.loads(text)
        except (ValueError, TypeError) as err:
            raise ViaggiaTrenoError("Invalid board JSON") from err
        if not isinstance(data, list) or any(
            not isinstance(item, dict) or item.get("numeroTreno") is None
            for item in data
        ):
            raise ViaggiaTrenoError("Invalid board response")
        return data

    async def boards(
        self, station_id: str, now: datetime
    ) -> tuple[list[dict], list[dict]]:
        """Fetch both boards with one timestamp; fail the entire snapshot on error."""
        # Wait for both requests even on failure; leave no orphaned requests running.
        results = await asyncio.gather(
            self.board(station_id, "arrivi", now),
            self.board(station_id, "partenze", now),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, BaseException):
                raise result
        return results[0], results[1]
