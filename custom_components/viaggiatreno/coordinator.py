"""Shared, atomic station updates for the three entities."""

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import RateLimited, ViaggiaTrenoClient, ViaggiaTrenoError
from .const import (
    CONF_REFRESH_INTERVAL,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    DEFAULT_REFRESH_INTERVAL,
)
from .models import merge_boards

_LOGGER = logging.getLogger(__name__)


class StationCoordinator(DataUpdateCoordinator[dict]):
    """One pair of API calls per station per refresh, regardless of card count."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: ViaggiaTrenoClient
    ) -> None:
        self.client = client
        self.station_id = entry.data[CONF_STATION_ID]
        self.station_name = entry.data[CONF_STATION_NAME]
        self.last_success = None
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
            arrivals, departures = await self.client.boards(
                self.station_id, dt_util.utcnow()
            )
            data = merge_boards(arrivals, departures)
        except RateLimited as err:
            raise UpdateFailed(str(err), retry_after=err.retry_after) from err
        except ViaggiaTrenoError as err:
            raise UpdateFailed(str(err)) from err
        self.last_success = dt_util.utcnow()
        return {**data, "last_refresh": self.last_success}
