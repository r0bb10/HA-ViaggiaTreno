"""Automatic resource registration without direct storage-file access."""

import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.components.lovelace.resources import ResourceStorageCollection

from custom_components.viaggiatreno.frontend import (
    CARD_PATH,
    LEGACY_CARD_PATH,
    async_register_card,
    card_url,
    install_card,
)
from tests.test_integration import make_entry, setup_station


def collection(hass, items):
    Path(hass.config.path("www")).mkdir(exist_ok=True)
    resources = MagicMock(spec=ResourceStorageCollection)
    resources.async_get_info = AsyncMock()
    resources.async_items.return_value = items
    resources.async_create_item = AsyncMock()
    resources.async_update_item = AsyncMock()
    resources.async_delete_item = AsyncMock()
    hass.data[LOVELACE_DATA] = SimpleNamespace(resources=resources)
    return resources


def test_cache_key_tracks_content_not_manifest_version():
    with patch("pathlib.Path.read_bytes", return_value=b"first card"):
        first = card_url()
        assert (
            first == f"{CARD_PATH}?v={hashlib.sha256(b'first card').hexdigest()[:16]}"
        )
        assert card_url() == first
    with patch("pathlib.Path.read_bytes", return_value=b"updated card"):
        assert card_url() != first


async def test_creates_module_and_loads_collection_first(hass):
    resources = collection(hass, [])
    await async_register_card(hass)
    resources.async_get_info.assert_awaited_once()
    resources.async_create_item.assert_awaited_once_with(
        {"url": card_url(), "res_type": "module"}
    )
    resources.async_update_item.assert_not_awaited()


async def test_updates_existing_id_and_removes_only_own_duplicates(hass):
    resources = collection(
        hass,
        [
            {"id": "old", "url": LEGACY_CARD_PATH + "?v=old", "type": "js"},
            {"id": "duplicate", "url": CARD_PATH, "type": "module"},
            {"id": "other", "url": "/hacsfiles/other/card.js", "type": "module"},
            {
                "id": "external",
                "url": "https://example.com" + CARD_PATH,
                "type": "module",
            },
        ],
    )
    await async_register_card(hass)
    resources.async_create_item.assert_not_awaited()
    resources.async_update_item.assert_awaited_once_with(
        "old", {"url": card_url(), "res_type": "module"}
    )
    resources.async_delete_item.assert_awaited_once_with("duplicate")


async def test_unchanged_resource_is_not_written_again(hass):
    resources = collection(
        hass, [{"id": "existing", "url": card_url(), "type": "module"}]
    )
    await async_register_card(hass)
    await async_register_card(hass)
    resources.async_create_item.assert_not_awaited()
    resources.async_update_item.assert_not_awaited()
    resources.async_delete_item.assert_not_awaited()


async def test_yaml_mode_uses_frontend_hook_without_writing_yaml(hass):
    Path(hass.config.path("www")).mkdir(exist_ok=True)
    hass.data[LOVELACE_DATA] = SimpleNamespace(resources=object())
    with patch("custom_components.viaggiatreno.frontend.add_extra_js_url") as register:
        await async_register_card(hass)
    register.assert_called_once_with(hass, card_url())


async def test_station_setup_registers_one_resource_for_multiple_stations(
    hass, mock_api
):
    await setup_station(hass)
    resources = hass.data[LOVELACE_DATA].resources
    assert isinstance(resources, ResourceStorageCollection)
    expected = await hass.async_add_executor_job(card_url)
    assert [
        {"url": item["url"], "type": item["type"]} for item in resources.async_items()
    ] == [{"url": expected, "type": "module"}]
    await setup_station(hass, make_entry("S01807", "VOGHERA"))
    assert len(resources.async_items()) == 1


def test_install_card_is_atomic_and_skips_identical_bytes(tmp_path):
    url = install_card(str(tmp_path))
    target = tmp_path / "www/community/viaggiatreno-card/viaggiatreno-card.js"
    assert url == card_url()
    source = (
        Path(__file__).resolve().parents[1]
        / "custom_components/viaggiatreno/static/viaggiatreno-card.js"
    )
    assert target.read_bytes() == source.read_bytes()
    before = target.stat().st_mtime_ns
    install_card(str(tmp_path))
    assert target.stat().st_mtime_ns == before
    target.write_text("old card")
    install_card(str(tmp_path))
    assert target.read_bytes() == source.read_bytes()
    assert list(target.parent.iterdir()) == [target]


async def test_installed_community_module_is_served(hass, mock_api, hass_client):
    await setup_station(hass)
    client = await hass_client()
    response = await client.get(card_url())
    assert response.status == 200
    content = await response.read()
    assert hashlib.sha256(content).hexdigest()[:16] == card_url().split("v=")[1]
