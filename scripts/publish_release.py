"""Publish a validated ZIP through gh; never create/move tags or replace assets."""

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import quote
from zipfile import ZipFile

from scripts.build_release import VERSION_PATTERN, normalize_version


def gh(*arguments: str) -> str:
    """Run GitHub CLI without a shell; errors stop publication."""
    result = subprocess.run(
        ["gh", *arguments], check=False, text=True, capture_output=True
    )
    if result.returncode:
        raise RuntimeError(f"GitHub CLI failed ({result.returncode}): {result.stderr}")
    return result.stdout


def should_mark_latest(tag: str, releases: list[dict]) -> bool:
    """Never promote a prerelease, unknown version scheme, or historical stable."""
    current = VERSION_PATTERN.fullmatch(tag)
    if current is None or current[4] or len(releases) >= 1000:
        return False
    current_key = tuple(int(current[index]) for index in (1, 2, 3))
    for release in releases:
        if release["isDraft"] or release["isPrerelease"]:
            continue
        previous = VERSION_PATTERN.fullmatch(release["tagName"])
        if previous is None or previous[4]:
            return False
        if tuple(int(previous[index]) for index in (1, 2, 3)) > current_key:
            return False
    return True


def publish(repository: str, tag: str, commit: str, asset: Path) -> None:
    """Recheck the immutable source and create one new release via a draft."""
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) is None:
        raise ValueError("Use owner/repository")
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ValueError("Expected a full commit SHA")
    version = normalize_version(tag)
    if asset.is_symlink() or not asset.is_file() or asset.suffix != ".zip":
        raise ValueError("Expected a regular ZIP asset")
    with ZipFile(asset) as archive:
        if archive.testzip() is not None:
            raise ValueError("Corrupt ZIP asset")
        if json.loads(archive.read("manifest.json"))["version"] != version:
            raise ValueError("Asset version does not match tag")
    # Resolve the exact tag ref, never an ambiguous branch/tag short name.
    actual = json.loads(
        gh("api", f"repos/{repository}/git/ref/tags/{quote(tag, safe='')}")
    )["object"]
    seen = set()
    while actual["type"] == "tag":
        sha = actual["sha"]
        if re.fullmatch(r"[0-9a-f]{40}", sha) is None or sha in seen or len(seen) >= 16:
            raise ValueError("Invalid or cyclic annotated release tag")
        seen.add(sha)
        actual = json.loads(gh("api", f"repos/{repository}/git/tags/{sha}"))["object"]
    if actual["type"] != "commit" or actual["sha"] != commit:
        raise ValueError("Release tag moved: refusing publication")
    releases = json.loads(
        gh(
            "release",
            "list",
            "--repo",
            repository,
            "--limit",
            "1000",
            "--json",
            "tagName,isDraft,isPrerelease",
        )
    )
    if any(release["tagName"] == tag for release in releases):
        raise ValueError(
            "Release already exists; inspect it manually or use a new version"
        )
    prerelease = bool(VERSION_PATTERN.fullmatch(tag)[4])
    latest = should_mark_latest(tag, releases)
    gh(
        "release",
        "create",
        tag,
        str(asset.resolve()),
        "--repo",
        repository,
        "--verify-tag",
        "--draft",
        "--title",
        version,
        "--generate-notes",
        "--latest=false",
        f"--prerelease={str(prerelease).lower()}",
    )
    # Keep failures visible as a draft. Never delete/recreate an existing release.
    gh(
        "release",
        "edit",
        tag,
        "--repo",
        repository,
        "--draft=false",
        f"--latest={str(latest).lower()}",
    )


def main() -> None:
    """Read release identifiers only from explicit arguments/environment."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset", type=Path, required=True)
    args = parser.parse_args()
    publish(
        os.environ["GH_REPO"],
        os.environ["RELEASE_TAG"],
        os.environ["RELEASE_COMMIT"],
        args.asset,
    )


if __name__ == "__main__":
    main()
