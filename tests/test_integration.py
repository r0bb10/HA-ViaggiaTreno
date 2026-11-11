from datetime import timedelta

from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.viaggiatreno.api import NoData, Station, ViaggiaTrenoError
from custom_components.viaggiatreno.const import DOMAIN


def make_entry(station_id="S01810", name="TORTONA", interval=60):
    return MockConfigEntry(
        domain=DOMAIN,
        title=name.title(),
        unique_id=station_id,
        data={"station_id": station_id, "station_name": name},
        options={"refresh_interval": interval},
    )


async def setup_station(hass, entry=None):
    entry = entry or make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_setup_entities_outage_unload(hass, mock_api):
    entry = await setup_station(hass)
    states = hass.states.async_all("sensor")
    assert len(states) == 3
    arrivals = hass.states.get("sensor.tortona_arrivals")
    assert arrivals.state == "1"
    assert arrivals.attributes["trains"][0]["destination"] == "LA SPEZIA CENTRALE"
    refresh_id = "sensor.tortona_last_successful_refresh"
    refresh = hass.states.get(refresh_id)
    assert refresh is not None
    registry_entry = er.async_get(hass).async_get(refresh_id)
    assert registry_entry.entity_category.value == "diagnostic"
    previous = refresh.state
    mock_api[1].side_effect = ViaggiaTrenoError("offline")
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("sensor.tortona_arrivals").state == "unavailable"
    assert hass.states.get(refresh_id).state == previous
    assert not hass.states.get(refresh_id).attributes["last_update_success"]
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_multiple_stations(hass, mock_api):
    first = await setup_station(hass)
    second = await setup_station(hass, make_entry("S01807", "VOGHERA", 90))
    assert len(hass.states.async_all("sensor")) == 6
    assert first.runtime_data is not second.runtime_data
    assert first.runtime_data.client is second.runtime_data.client
    assert second.runtime_data.update_interval == timedelta(seconds=90)
    assert len(dr.async_get(hass).devices) == 2
    assert mock_api[1].await_count == 2


async def test_empty_upstream_response_does_not_advance_refresh(hass, mock_api):
    entry = await setup_station(hass)
    previous = hass.states.get("sensor.tortona_last_successful_refresh").state
    mock_api[1].side_effect = NoData("No board data")
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("sensor.tortona_arrivals").state == "unavailable"
    assert hass.states.get("sensor.tortona_last_successful_refresh").state == previous


async def test_user_flow(hass, mock_api):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "query": "Tortona",
            "refresh_interval": 60,
        },
    )
    assert result["step_id"] == "station"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"station_id": "S01810"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    assert len(hass.states.async_all("sensor")) == 3


async def test_duplicate(hass, mock_api):
    make_entry().add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
        data={"query": "Tortona", "refresh_interval": 60},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"station_id": "S01810"}
    )
    assert result["reason"] == "already_configured"


async def test_search_and_validation_errors(hass, mock_api):
    mock_api[0].return_value = []
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
        data={"query": "Missing", "refresh_interval": 60},
    )
    assert result["errors"] == {"query": "no_stations"}
    mock_api[0].side_effect = ViaggiaTrenoError("offline")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"query": "Tortona", "refresh_interval": 60}
    )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_reconfigure_preserves_entity_ids(hass, mock_api):
    entry = await setup_station(hass)
    before = {
        entity.entity_id
        for entity in er.async_entries_for_config_entry(
            er.async_get(hass), entry.entry_id
        )
    }
    mock_api[0].return_value = [Station("S01807", "VOGHERA")]
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"query": "Voghera", "refresh_interval": 90}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"station_id": "S01807"}
    )
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    assert entry.unique_id == "S01807"
    assert entry.runtime_data.station_id == "S01807"
    after = {
        entity.entity_id
        for entity in er.async_entries_for_config_entry(
            er.async_get(hass), entry.entry_id
        )
    }
    assert before == after
    assert entry.runtime_data.update_interval == timedelta(seconds=90)
    assert (
        hass.states.get("sensor.tortona_arrivals").attributes["station_name"]
        == "VOGHERA"
    )


async def test_options_reload(hass, mock_api):
    entry = await setup_station(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"refresh_interval": 120}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.runtime_data.update_interval == timedelta(seconds=120)


async def test_static_icons_served(hass, mock_api, hass_client):
    await setup_station(hass)
    client = await hass_client()
    for path in (
        "operators/intercity.svg",
        "operators/trenitalia.svg",
        "categories/ic.svg",
    ):
        response = await client.get(f"/viaggiatreno/static/{path}")
        assert response.status == 200
        assert "<svg" in await response.text()


async def test_initial_failure_retries(hass, mock_api):
    mock_api[1].side_effect = ViaggiaTrenoError("offline")
    entry = make_entry()
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state.value == "setup_retry"
