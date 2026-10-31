"""ViaggiaTreno integration."""

from pathlib import Path

from homeassistant.components import websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ViaggiaTrenoClient
from .const import DOMAIN, PLATFORMS, STATIC_URL
from .coordinator import StationCoordinator
from .websocket import ws_last_report

type ViaggiaTrenoConfigEntry = ConfigEntry[StationCoordinator]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register bundled read-only assets once, including after entry reloads."""
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(STATIC_URL, str(Path(__file__).parent / "static"), True),
            StaticPathConfig(
                "/viaggiatreno/brand", str(Path(__file__).parent / "brand"), True
            ),
        ]
    )
    client = ViaggiaTrenoClient(async_get_clientsession(hass))
    hass.data[DOMAIN] = client

    async def async_stop(event: Event) -> None:
        await client.async_close()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, async_stop)
    websocket_api.async_register_command(hass, ws_last_report)
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: ViaggiaTrenoConfigEntry
) -> bool:
    """Initialize one configured station."""
    coordinator = StationCoordinator(hass, entry, hass.data[DOMAIN])
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: ViaggiaTrenoConfigEntry
) -> bool:
    """Unload station entities and their coordinator subscriptions."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
