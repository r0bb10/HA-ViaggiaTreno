"""Local regression tests for failure handling and configuration safeguards."""

from datetime import timedelta

import probatio
import pytest
from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER

from custom_components.viaggiatreno.api import RateLimited, Station
from custom_components.viaggiatreno.config_flow import interval_field
from custom_components.viaggiatreno.const import DOMAIN
from custom_components.viaggiatreno.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .test_integration import make_entry, setup_station


async def test_recovery_and_downloadable_diagnostics(hass, mock_api, boards):
    entry = await setup_station(hass)
    coordinator = entry.runtime_data
    snapshot = coordinator.data
    last_success = coordinator.last_success
    mock_api[1].side_effect = RateLimited(180)
    await coordinator.async_refresh()
    assert not coordinator.last_update_success
    assert coordinator.data is snapshot
    assert coordinator.last_success == last_success
    data = await async_get_config_entry_diagnostics(hass, entry)
    assert data["arrival_count"] == 1
    assert data["last_update_success"] is False
    mock_api[1].side_effect = None
    mock_api[1].return_value = boards
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.last_update_success
    assert hass.states.get("sensor.tortona_arrivals").state == "1"


async def test_reconfigure_rejects_other_station(hass, mock_api):
    entry = await setup_station(hass)
    await setup_station(hass, make_entry("S01807", "VOGHERA"))
    mock_api[0].return_value = [Station("S01807", "VOGHERA")]
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
        data={"query": "Voghera", "refresh_interval": 60},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"station_id": "S01807"}
    )
    assert result["reason"] == "already_configured"
    assert entry.unique_id == "S01810"
    assert entry.runtime_data.station_id == "S01810"


async def test_select_station_connection_error(hass, mock_api):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
        data={"query": "Tortona", "refresh_interval": 60},
    )
    mock_api[1].side_effect = RateLimited()
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"station_id": "S01810"}
    )
    assert result["errors"] == {"base": "cannot_connect"}
    assert not hass.config_entries.async_entries(DOMAIN)


@pytest.mark.parametrize("interval", [0, 29, 3601, -30])
def test_invalid_intervals_rejected(interval):
    with pytest.raises(probatio.Invalid):
        probatio.Schema(interval_field(60))({"refresh_interval": interval})


async def test_periodic_refresh(hass, mock_api, freezer):
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    entry = await setup_station(hass)
    assert mock_api[1].await_count == 1
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert mock_api[1].await_count == 2
    assert entry.runtime_data.last_update_success
