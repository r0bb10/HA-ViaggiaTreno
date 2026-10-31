"""Downloadable station diagnostics."""

from homeassistant.core import HomeAssistant

from . import ViaggiaTrenoConfigEntry
from .const import CONF_REFRESH_INTERVAL, DEFAULT_REFRESH_INTERVAL


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ViaggiaTrenoConfigEntry
) -> dict:
    coordinator = entry.runtime_data
    return {
        "station": dict(entry.data),
        "refresh_interval": entry.options.get(
            CONF_REFRESH_INTERVAL, DEFAULT_REFRESH_INTERVAL
        ),
        "last_update_success": coordinator.last_update_success,
        "last_success": (
            coordinator.last_success.isoformat() if coordinator.last_success else None
        ),
        "arrival_count": len(coordinator.data.get("arrivi", [])),
        "departure_count": len(coordinator.data.get("partenze", [])),
    }
