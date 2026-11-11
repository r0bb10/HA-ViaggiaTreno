"""Register the bundled card and invalidate browser caches when its bytes change."""

import hashlib
import os
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.components.lovelace.resources import ResourceStorageCollection
from homeassistant.core import HomeAssistant

from .const import STATIC_URL

CARD_PATH = "/local/community/viaggiatreno-card/viaggiatreno-card.js"
LEGACY_CARD_PATH = f"{STATIC_URL}/viaggiatreno-card.js"


def card_url() -> str:
    """Use file content, not the source manifest's development version."""
    content = (Path(__file__).parent / "static/viaggiatreno-card.js").read_bytes()
    return f"{CARD_PATH}?v={hashlib.sha256(content).hexdigest()[:16]}"


def install_card(config_dir: str) -> str:
    """Atomically install our bundled module; avoid rewriting identical content."""
    source = Path(__file__).parent / "static/viaggiatreno-card.js"
    content = source.read_bytes()
    directory = Path(config_dir) / "www/community/viaggiatreno-card"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "viaggiatreno-card.js"
    if target.is_symlink():
        raise OSError("Refusing to overwrite a symlinked ViaggiaTreno card")
    if not target.exists() or target.read_bytes() != content:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=directory, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(content)
            temporary.chmod(0o644)
            os.replace(temporary, target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return f"{CARD_PATH}?v={hashlib.sha256(content).hexdigest()[:16]}"


def _is_card_resource(url: str) -> bool:
    """Touch only our local resource, regardless of its old cache key."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return (
        not parts.scheme
        and not parts.netloc
        and parts.path in {CARD_PATH, LEGACY_CARD_PATH}
    )


async def async_register_card(hass: HomeAssistant) -> None:
    """Create/update a single module via HA's resource collection API."""
    www = Path(hass.config.path("www"))
    had_www = await hass.async_add_executor_job(www.is_dir)
    url = await hass.async_add_executor_job(install_card, hass.config.config_dir)
    if not had_www:
        # Frontend registers /local only when www exists during its setup.
        await hass.http.async_register_static_paths(
            [StaticPathConfig("/local", str(www), True)]
        )
    resources = hass.data[LOVELACE_DATA].resources
    if not isinstance(resources, ResourceStorageCollection):
        # YAML resources are user-owned: use HA's supported extra-module hook
        # rather than rewriting YAML files or modifying read-only collections.
        add_extra_js_url(hass, url)
        return

    # async_items alone does not ensure that the persisted collection is loaded.
    await resources.async_get_info()
    matches = [
        item for item in resources.async_items() if _is_card_resource(item["url"])
    ]
    if not matches:
        await resources.async_create_item({"url": url, "res_type": "module"})
        return

    existing = matches[0]
    if existing["url"] != url or existing["type"] != "module":
        await resources.async_update_item(
            existing["id"], {"url": url, "res_type": "module"}
        )
    for duplicate in matches[1:]:
        await resources.async_delete_item(duplicate["id"])
