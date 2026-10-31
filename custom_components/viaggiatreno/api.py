"""Small asynchronous client for the public ViaggiaTreno website API.

No website HTML is fetched or parsed. All train information is JSON.
"""

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime
from time import monotonic
from urllib.parse import quote
from zoneinfo import ZoneInfo

import aiohttp

from .const import BASE_URL
from .models import _timestamp

ROME = ZoneInfo("Europe/Rome")
STATION_ID = re.compile(r"S\d{5}\Z")
USER_AGENT = "Mozilla/5.0 (compatible; ViaggiaTreno; HomeAssistant)"
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=20, connect=5)
REPORT_CACHE_SECONDS = 15
MAX_REPORTS = 128


class ViaggiaTrenoError(Exception):
    """Invalid or unavailable upstream response."""


class NoData(ViaggiaTrenoError):
    """The upstream endpoint returned no content."""


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
        self._report_cache: dict[tuple[str, str, str], tuple[float, dict]] = {}
        self._report_tasks: dict[tuple[str, str, str], asyncio.Task[dict]] = {}
        self._closed = False

    async def async_close(self) -> None:
        """Release cached reports and cancel outstanding detail lookups."""
        self._closed = True
        tasks = list(self._report_tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._report_tasks.clear()
        self._report_cache.clear()

    async def _get(self, path: str) -> str:
        try:
            async with self._session.get(
                f"{BASE_URL}/{path}",
                timeout=REQUEST_TIMEOUT,
                # The website rejects aiohttp's default User-Agent with 403.
                headers={
                    "Accept": "application/json, text/plain",
                    "User-Agent": USER_AGENT,
                },
            ) as response:
                if response.status == 204:
                    raise NoData("No data returned by ViaggiaTreno")
                if response.status == 429:
                    retry = response.headers.get("Retry-After", "300")
                    raise RateLimited(
                        min(max(int(retry), 30), 3600) if retry.isdigit() else 300
                    )
                response.raise_for_status()
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
        """Share on-demand lookups by service identity and briefly cache results."""
        if self._closed:
            raise ViaggiaTrenoError("Client is closed")
        origin = str(train.get("origin_station_id") or "")
        number = str(train.get("train_number") or "")
        date = str(train.get("service_timestamp") or "")
        if (
            not STATION_ID.fullmatch(origin)
            or not re.fullmatch(r"\d{1,10}", number)
            or not re.fullmatch(r"\d{1,16}", date)
        ):
            raise ViaggiaTrenoError("Service identity unavailable")
        key = (origin, number, str(int(date)))
        cached = self._report_cache.get(key)
        if cached is not None:
            if cached[0] > monotonic():
                return dict(cached[1])
            self._report_cache.pop(key)
        task = self._report_tasks.get(key)
        if task is None:
            if len(self._report_tasks) >= MAX_REPORTS:
                raise ViaggiaTrenoError("Too many pending detail lookups")
            task = asyncio.create_task(self._fetch_last_report(*key))
            self._report_tasks[key] = task

            def completed(request: asyncio.Task[dict]) -> None:
                self._report_tasks.pop(key, None)
                if (
                    request.cancelled()
                    or request.exception() is not None
                    or self._closed
                ):
                    return
                now = monotonic()
                self._report_cache = {
                    k: value
                    for k, value in self._report_cache.items()
                    if value[0] > now
                }
                if len(self._report_cache) >= MAX_REPORTS:
                    self._report_cache.pop(next(iter(self._report_cache)))
                self._report_cache[key] = (now + REPORT_CACHE_SECONDS, request.result())

            task.add_done_callback(completed)
        # A cancelled waiter must not cancel the shared request.
        return dict(await asyncio.shield(task))

    async def _fetch_last_report(self, origin: str, number: str, date: str) -> dict:
        """Fetch a report without mistaking no content for a network failure."""
        missing = {"station": None, "timestamp": None}
        try:
            data = json.loads(
                await self._get(f"andamentoTreno/{origin}/{number}/{date}")
            )
        except NoData:
            return missing
        except ValueError as err:
            raise ViaggiaTrenoError("Invalid train detail JSON") from err
        if data is None:
            return missing
        if not isinstance(data, dict):
            raise ViaggiaTrenoError("Invalid train detail response")
        station = data.get("stazioneUltimoRilevamento")
        timestamp = _timestamp(data.get("oraUltimoRilevamento"))
        if not isinstance(station, str) or station.strip() in {"", "-", "--"}:
            return missing
        if timestamp is None or data["oraUltimoRilevamento"] <= 0:
            return missing
        return {
            "station": station.strip(),
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
