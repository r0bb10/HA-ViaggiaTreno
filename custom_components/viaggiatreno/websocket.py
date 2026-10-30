"""Authenticated, on-demand train position lookup for the bundled card."""

import probatio as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from .api import ViaggiaTrenoError
from .const import DOMAIN


@websocket_api.websocket_command(
    {
        vol.Required("type"): "viaggiatreno/last_report",
        vol.Required("station_id"): str,
        vol.Required("service_id"): str,
    }
)
@websocket_api.async_response
async def ws_last_report(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Accept only services present in a configured station's current board."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        coordinator = getattr(entry, "runtime_data", None)
        if coordinator is None or coordinator.station_id != msg["station_id"]:
            continue
        for direction in ("arrivi", "partenze"):
            rows = (coordinator.data or {}).get(direction, [])
            for train in rows:
                if train.get("service_id") != msg["service_id"]:
                    continue
                try:
                    result = await coordinator.client.last_report(train)
                except ViaggiaTrenoError:
                    connection.send_error(
                        msg["id"], "report_unavailable", "Last report unavailable"
                    )
                else:
                    connection.send_result(msg["id"], result)
                return
    connection.send_error(msg["id"], "service_not_found", "Service no longer on board")
