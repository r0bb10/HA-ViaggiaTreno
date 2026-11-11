import json
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components/viaggiatreno"


def test_hacs_metadata_and_translations():
    from awesomeversion import AwesomeVersion, AwesomeVersionStrategy

    manifest = json.loads((INTEGRATION / "manifest.json").read_text())
    assert manifest["domain"] == "viaggiatreno"
    assert manifest["name"] == "ViaggiaTreno"
    assert AwesomeVersion(manifest["version"]).strategy is AwesomeVersionStrategy.CALVER
    assert manifest["config_flow"]
    assert all(
        manifest[k]
        for k in ("version", "name", "documentation", "issue_tracker", "codeowners")
    )
    assert json.loads((ROOT / "hacs.json").read_text())["homeassistant"] == "2026.10.0"
    en = json.loads((INTEGRATION / "translations/en.json").read_text())
    assert en == json.loads((INTEGRATION / "strings.json").read_text())
    it = json.loads((INTEGRATION / "translations/it.json").read_text())
    assert en["entity"]["sensor"].keys() == it["entity"]["sensor"].keys()
    assert (INTEGRATION / "brand/icon.png").read_bytes().startswith(b"\x89PNG")


def test_icon_assets_are_inert_and_complete():
    for path in (INTEGRATION / "static").rglob("*.svg"):
        root = ET.fromstring(path.read_text())
        assert root.tag.endswith("svg")
        for element in root.iter():
            assert not element.tag.endswith("script")
            assert not any(key.lower().startswith("on") for key in element.attrib)
            assert not element.attrib.get("href", "").startswith("http")
    sources = json.loads((INTEGRATION / "static/sources.json").read_text())
    assert len(sources) == 17
    assert any(source["file"] == "operators/trenitalia-tper.svg" for source in sources)
    for source in sources:
        assert (INTEGRATION / "static" / source["file"]).is_file()
    from custom_components.viaggiatreno.models import CATEGORIES, OPERATORS

    sourced = {source["file"] for source in sources}
    assert {f"categories/{code.lower()}.svg" for code in CATEGORIES} <= sourced
    assert {f"operators/{asset}.svg" for _, asset in OPERATORS.values()} <= sourced


def test_icon_refresh_preserves_extra_artwork(tmp_path, monkeypatch):
    import base64
    import sys

    from scripts import fetch_icons

    root = tmp_path / "static"
    (root / "categories").mkdir(parents=True)
    art = root / "categories/icn.svg"
    art.write_text("separately acquired artwork")
    (root / "sources.json").write_text(
        json.dumps([{"file": "categories/icn.svg", "source": "additional source"}])
    )
    uri = "data:image/gif;base64," + base64.b64encode(b"GIF89a").decode()
    html = tmp_path / "board.html"
    html.write_text(
        "".join(f'<img alt="{alt}" src="{uri}">' for alt in fetch_icons.OPERATORS)
    )
    monkeypatch.setattr(fetch_icons, "ROOT", root)
    monkeypatch.setattr(sys, "argv", ["fetch_icons.py", "--html", str(html)])
    fetch_icons.main()
    assert art.read_text() == "separately acquired artwork"
    assert any(
        source["file"] == "categories/icn.svg"
        for source in json.loads((root / "sources.json").read_text())
    )


async def test_brand_images_served(hass, hass_client, mock_api):
    from homeassistant.setup import async_setup_component
    from PIL import Image

    from .test_integration import setup_station

    await setup_station(hass)
    assert await async_setup_component(hass, "brands", {})
    client = await hass_client()
    for name, size in (
        ("icon.png", (256, 256)),
        ("icon@2x.png", (512, 512)),
        ("logo.png", (256, 43)),
        ("logo@2x.png", (512, 87)),
    ):
        path = INTEGRATION / "brand" / name
        image = Image.open(path)
        assert image.size == size
        assert image.mode == "RGBA"
        assert image.getchannel("A").getextrema() == (0, 255)
        response = await client.get(f"/api/brands/integration/viaggiatreno/{name}")
        assert response.status == 200
        assert await response.read() == path.read_bytes()
        response = await client.get(f"/viaggiatreno/brand/{name}")
        assert response.status == 200
        assert await response.read() == path.read_bytes()
