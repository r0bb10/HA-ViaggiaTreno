from unittest.mock import AsyncMock, patch

from custom_components.viaggiatreno.api import ViaggiaTrenoError

from .test_integration import setup_station


async def test_last_report_websocket(hass, hass_ws_client, mock_api):
    await setup_station(hass)
    client = await hass_ws_client(hass)
    with patch(
        "custom_components.viaggiatreno.api.ViaggiaTrenoClient.last_report",
        new_callable=AsyncMock,
        return_value={
            "station": "PONTECURONE",
            "timestamp": "2026-10-29T17:27:00+00:00",
        },
    ) as fetch:
        query = {
            "type": "viaggiatreno/last_report",
            "station_id": "S01810",
            "service_id": "2026-10-29:S01700:665",
        }
        await client.send_json({"id": 1, **query})
        result = await client.receive_json()
        assert result["success"]
        assert result["result"]["station"] == "PONTECURONE"
        fetch.assert_awaited_once()
        await client.send_json({"id": 2, **query, "service_id": "unknown"})
        result = await client.receive_json()
        assert result["error"]["code"] == "service_not_found"
        assert fetch.await_count == 1
        fetch.side_effect = ViaggiaTrenoError("Offline")
        await client.send_json({"id": 3, **query})
        result = await client.receive_json()
        assert result["error"]["code"] == "report_unavailable"
        fetch.side_effect = None
        fetch.return_value = {"station": None, "timestamp": None}
        await client.send_json({"id": 4, **query})
        result = await client.receive_json()
        assert result["success"]
        assert result["result"] == {"station": None, "timestamp": None}
