"""Shared, atomic station updates for the three entities."""

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import ROME, RateLimited, ViaggiaTrenoClient, ViaggiaTrenoError
from .const import (
    CONF_REFRESH_INTERVAL,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    CONF_TARGET_SERVICES,
    DEFAULT_REFRESH_INTERVAL,
    DEFAULT_TARGET_SERVICES,
    MAX_BOARD_WINDOWS,
)
from .models import combine_windows, merge_boards

_LOGGER = logging.getLogger(__name__)


class StationCoordinator(DataUpdateCoordinator[dict]):
    """Bounded overlapping board windows, shared by every card for a station."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: ViaggiaTrenoClient
    ) -> None:
        self.client = client
        self.station_id = entry.data[CONF_STATION_ID]
        self.station_name = entry.data[CONF_STATION_NAME]
        self.last_success = None
        self.target_services = entry.options.get(
            CONF_TARGET_SERVICES, DEFAULT_TARGET_SERVICES
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"ViaggiaTreno {self.station_name}",
            update_interval=timedelta(
                seconds=entry.options.get(
                    CONF_REFRESH_INTERVAL, DEFAULT_REFRESH_INTERVAL
                )
            ),
        )

    async def _async_update_data(self) -> dict:
        try:
            now = dt_util.utcnow()
            arrival_windows = []
            departure_windows = []
            for offset in range(MAX_BOARD_WINDOWS):
                requested = now + timedelta(hours=offset)
                if requested.astimezone(ROME).date() != now.astimezone(ROME).date():
                    break
                arrivals, departures = await self.client.boards(
                    self.station_id, requested
                )
                arrival_windows.append(arrivals)
                departure_windows.append(departures)
                data = merge_boards(
                    combine_windows(arrival_windows), combine_windows(departure_windows)
                )
                # Both direction sensors get the configured target, when available.
                # Completed records remain present for the card's existing filtering.
                if all(
                    sum(not row["arrived"] for row in data[direction])
                    >= self.target_services
                    for direction in ("arrivi", "partenze")
                ):
                    break
            data["window_count"] = len(arrival_windows)
        except RateLimited as err:
            raise UpdateFailed(str(err), retry_after=err.retry_after) from err
        except ViaggiaTrenoError as err:
            raise UpdateFailed(str(err)) from err
        self.last_success = dt_util.utcnow()
        return {**data, "last_refresh": self.last_success}
