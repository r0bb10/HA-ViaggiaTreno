"""Offline release safety checks using throwaway Git indexes, without commits."""

import json
import subprocess
from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts.build_release import build_release, normalize_version, read_metadata


@pytest.mark.parametrize("tag", ["1.2.3", "v1.2.3", "2026.11.0", "1.2.3rc1"])
def test_supported_versions(tag: str) -> None:
    assert normalize_version(tag) == tag.removeprefix("v")


@pytest.mark.parametrize("tag", ["main", "1.02.3", "1.2", "1.2.3;id", "-1.2.3"])
def test_invalid_versions(tag: str) -> None:
    with pytest.raises(ValueError):
        normalize_version(tag)


def test_reproducible_component_only_zip(
    release_repository: Path, tmp_path: Path
) -> None:
    root = release_repository
    component = root / "custom_components/test_device"
    (component / "private-untracked.json").write_text('{"token":"not-shipped"}')
    original = (component / "manifest.json").read_bytes()
    first = build_release(root, tmp_path / "one", "v1.2.3")
    second = build_release(root, tmp_path / "two", "v1.2.3")
    assert first.read_bytes() == second.read_bytes()
    assert (component / "manifest.json").read_bytes() == original
    with ZipFile(first) as archive:
        assert set(archive.namelist()) == {
            "LICENSE",
            "__init__.py",
            "manifest.json",
            "translations/en.json",
        }
        assert json.loads(archive.read("manifest.json"))["version"] == "1.2.3"
    with pytest.raises(FileExistsError):
        build_release(root, tmp_path / "one", "v1.2.3")


def test_version_mismatch_never_rewrites_source(release_repository: Path) -> None:
    path = release_repository / "custom_components/test_device/manifest.json"
    before = path.read_bytes()
    with pytest.raises(ValueError, match="Manifest version"):
        build_release(release_repository, release_repository / "dist", "2.0.0")
    assert path.read_bytes() == before


@pytest.mark.parametrize("filename", [".env", "cached.pyc", "tests/test_secret.py"])
def test_rejects_tracked_development_files(
    release_repository: Path, filename: str
) -> None:
    path = release_repository / "custom_components/test_device" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not runtime content\n")
    subprocess.run(["git", "add", "."], cwd=release_repository, check=True)
    with pytest.raises(ValueError):
        build_release(release_repository, release_repository / "dist", "1.2.3")


def test_rejects_symlinks(release_repository: Path) -> None:
    (release_repository / "custom_components/test_device/leak.json").symlink_to(
        release_repository / "LICENSE"
    )
    subprocess.run(["git", "add", "."], cwd=release_repository, check=True)
    with pytest.raises(ValueError, match="regular"):
        build_release(release_repository, release_repository / "dist", "1.2.3")


def test_rejects_dirty_tracked_source(release_repository: Path) -> None:
    (release_repository / "custom_components/test_device/__init__.py").write_text(
        "# dirty"
    )
    with pytest.raises(subprocess.CalledProcessError):
        build_release(release_repository, release_repository / "dist", "1.2.3")


def test_template_cannot_be_released(release_repository: Path) -> None:
    (release_repository / ".template-only").write_text("Not ready")
    with pytest.raises(ValueError, match="CUSTOMIZATION"):
        read_metadata(release_repository, "1.2.3")


def test_tracked_frontend_and_brand_notices_are_preserved(
    release_repository: Path,
) -> None:
    component = release_repository / "custom_components/test_device"
    (component / "static").mkdir()
    (component / "static/card.js").write_text("export const example = 1;\n")
    (component / "brand").mkdir()
    (component / "brand/ATTRIBUTION.txt").write_text("Keep attribution\n")
    subprocess.run(["git", "add", "."], cwd=release_repository, check=True)
    archive = build_release(release_repository, release_repository / "dist", "1.2.3")
    with ZipFile(archive) as package:
        assert "static/card.js" in package.namelist()
        assert "brand/ATTRIBUTION.txt" in package.namelist()


def test_real_repository_package(repository_snapshot: Path, tmp_path: Path) -> None:
    """Package a temporary index of current candidate files without staging user work."""
    manifests = list(
        (repository_snapshot / "custom_components").glob("*/manifest.json")
    )
    version = json.loads(manifests[0].read_text())["version"]
    build_release(repository_snapshot, tmp_path / "package", version)


def test_development_release_blocker_is_enforced(release_repository: Path) -> None:
    (release_repository / ".release-blocked").write_text(
        "Repository identity not confirmed"
    )
    with pytest.raises(ValueError, match="Repository identity not confirmed"):
        read_metadata(release_repository, "1.2.3")


def test_required_runtime_assets_must_be_tracked(release_repository: Path) -> None:
    (release_repository / "release.json").write_text(
        json.dumps({"required_files": ["static/required-card.js"]})
    )
    with pytest.raises(ValueError, match="required-card.js"):
        build_release(release_repository, release_repository / "dist", "1.2.3")
