"""Common fixtures; no network access or real device credentials."""

import json
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def release_repository(tmp_path: Path) -> Path:
    """Create an isolated index for package tests; never commit anything."""
    root = tmp_path / "repository"
    component = root / "custom_components/test_device"
    (component / "translations").mkdir(parents=True)
    (component / "__init__.py").write_text('"""Fixture integration."""\n')
    (component / "translations/en.json").write_text("{}\n")
    (component / "manifest.json").write_text(
        json.dumps(
            {
                "domain": "test_device",
                "name": "Test device",
                "version": "1.2.3",
                "documentation": "https://github.com/owner/repository",
                "issue_tracker": "https://github.com/owner/repository/issues",
                "codeowners": ["@owner"],
            }
        )
    )
    (root / "hacs.json").write_text(
        json.dumps(
            {
                "name": "Test device",
                "zip_release": True,
                "filename": "test_device.zip",
            }
        )
    )
    (root / "LICENSE").write_text("Fixture license notice\n")
    subprocess.run(["git", "init", "--quiet", str(root)], check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    return root


@pytest.fixture
def repository_snapshot(tmp_path: Path) -> Path:
    """Index a disposable copy, including reviewed candidate files, never the real repo."""
    root = Path(__file__).resolve().parents[2]
    snapshot = tmp_path / "candidate"
    snapshot.mkdir()
    output = subprocess.check_output(
        [
            "git",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
            "--",
            "custom_components",
            "hacs.json",
            "LICENSE",
            "NOTICE",
            "release.json",
        ],
        cwd=root,
    )
    for name in sorted(set(filter(None, output.decode().split("\0")))):
        source = root / name
        if not source.is_file():
            continue
        destination = snapshot / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_symlink():
            destination.symlink_to(source.readlink())
        else:
            destination.write_bytes(source.read_bytes())
    subprocess.run(["git", "init", "--quiet", str(snapshot)], check=True)
    subprocess.run(["git", "add", "."], cwd=snapshot, check=True)
    return snapshot
