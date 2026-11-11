"""Local metadata and toolchain consistency; hassfest checks HA schemas in CI."""

import json
import tomllib
from pathlib import Path

from scripts.build_release import read_metadata

ROOT = Path(__file__).resolve().parents[2]


def test_metadata_and_english_source() -> None:
    manifests = list((ROOT / "custom_components").glob("*/manifest.json"))
    assert len(manifests) == 1
    component = manifests[0].parent
    manifest = json.loads(manifests[0].read_text())
    read_metadata(ROOT, manifest["version"], allow_template=True)
    english = json.loads((component / "translations/en.json").read_text())
    if (component / "strings.json").exists():
        assert english == json.loads((component / "strings.json").read_text())


def test_dependency_declarations_match() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    requirements = [
        line.strip()
        for line in (ROOT / "requirements-dev.txt").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert sorted(requirements) == sorted(project["dependency-groups"]["dev"])


def test_manifest_order_and_project_version():
    manifest = json.loads(
        next((ROOT / "custom_components").glob("*/manifest.json")).read_text()
    )
    assert list(manifest) == ["domain", "name"] + sorted(
        key for key in manifest if key not in {"domain", "name"}
    )
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert project["project"]["version"] == manifest["version"]
