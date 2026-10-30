"""UI station search, station replacement, and polling options."""

from __future__ import annotations

from typing import Any

import probatio as schema
from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)
from homeassistant.util import dt as dt_util

from .api import Station, ViaggiaTrenoClient, ViaggiaTrenoError
from .const import (
    CONF_REFRESH_INTERVAL,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    DEFAULT_REFRESH_INTERVAL,
    DOMAIN,
    MAX_REFRESH_INTERVAL,
    MIN_REFRESH_INTERVAL,
)


def interval_field(default: int):
    """Use an integer selector with server-side range validation."""
    return {
        schema.Required(CONF_REFRESH_INTERVAL, default=default): schema.All(
            NumberSelector(
                NumberSelectorConfig(
                    min=MIN_REFRESH_INTERVAL,
                    max=MAX_REFRESH_INTERVAL,
                    step=1,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="s",
                )
            ),
            schema.Coerce(int),
        )
    }


class ViaggiaTrenoFlow(ConfigFlow, domain=DOMAIN):
    """Configure a single station; multiple entries support multiple stations."""

    VERSION = 1

    def __init__(self) -> None:
        self._stations: list[Station] = []
        self._interval = DEFAULT_REFRESH_INTERVAL

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> ViaggiaTrenoOptions:
        return ViaggiaTrenoOptions()

    def _client(self) -> ViaggiaTrenoClient:
        return ViaggiaTrenoClient(async_get_clientsession(self.hass))

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        return await self._search("user", user_input)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None):
        return await self._search("reconfigure", user_input)

    async def _search(
        self, step: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        errors = {}
        default_query = ""
        if self.source == SOURCE_RECONFIGURE:
            entry = self._get_reconfigure_entry()
            default_query = entry.data[CONF_STATION_NAME]
            self._interval = entry.options.get(
                CONF_REFRESH_INTERVAL, DEFAULT_REFRESH_INTERVAL
            )
        if user_input is not None:
            self._interval = user_input[CONF_REFRESH_INTERVAL]
            default_query = user_input["query"]
            try:
                self._stations = await self._client().search_stations(default_query)
            except ViaggiaTrenoError:
                errors["base"] = "cannot_connect"
            else:
                if self._stations:
                    return await self.async_step_station()
                errors["query"] = "no_stations"
        return self.async_show_form(
            step_id=step,
            data_schema=schema.Schema(
                {
                    schema.Required("query", default=default_query): TextSelector(),
                    **interval_field(self._interval),
                }
            ),
            errors=errors,
        )

    async def async_step_station(self, user_input: dict[str, Any] | None = None):
        errors = {}
        if user_input is not None:
            station = next(
                (s for s in self._stations if s.id == user_input[CONF_STATION_ID]), None
            )
            if station is None:
                return self.async_abort(reason="invalid_station")
            # Exclude the entry being reconfigured, but reject other duplicates.
            existing = (
                self._get_reconfigure_entry()
                if self.source == SOURCE_RECONFIGURE
                else None
            )
            await self.async_set_unique_id(station.id)
            if any(
                entry.unique_id == station.id and entry is not existing
                for entry in self._async_current_entries()
            ):
                return self.async_abort(reason="already_configured")
            try:
                await self._client().boards(station.id, dt_util.utcnow())
            except ViaggiaTrenoError:
                errors["base"] = "cannot_connect"
            else:
                data = {CONF_STATION_ID: station.id, CONF_STATION_NAME: station.name}
                options = {CONF_REFRESH_INTERVAL: self._interval}
                if existing is not None:
                    # The configured station changes, while entity and device IDs
                    # remain tied to the entry so existing dashboard references work.
                    return self.async_update_reload_and_abort(
                        existing,
                        unique_id=station.id,
                        title=station.name.title(),
                        data_updates=data,
                        options=options,
                    )
                return self.async_create_entry(
                    title=station.name.title(), data=data, options=options
                )
        return self.async_show_form(
            step_id="station",
            data_schema=schema.Schema(
                {
                    schema.Required(CONF_STATION_ID): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                {"value": s.id, "label": f"{s.name} ({s.id})"}
                                for s in self._stations
                            ],
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
            errors=errors,
        )


class ViaggiaTrenoOptions(OptionsFlowWithReload):
    """Adjust polling; Home Assistant reloads only this station's entry."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=schema.Schema(
                interval_field(
                    self.config_entry.options.get(
                        CONF_REFRESH_INTERVAL, DEFAULT_REFRESH_INTERVAL
                    )
                )
            ),
        )
