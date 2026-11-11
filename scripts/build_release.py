"""Validate and build a reproducible, tracked-runtime-files-only release ZIP.

This module uses only the standard library. It never changes integration source,
creates tags, stages files, commits, or contacts GitHub.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

VERSION_PATTERN = re.compile(
    r"v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:(a|b|rc)(0|[1-9]\d*))?"
)
RUNTIME_SUFFIXES = {
    ".py",
    ".json",
    ".yaml",
    ".yml",
    ".png",
    ".svg",
    ".js",
    ".css",
    ".html",
    ".woff",
    ".woff2",
    ".ttf",
}
MAX_BYTES = 100 * 1024 * 1024
MAX_FILES = 50_000


def normalize_version(tag: str) -> str:
    """Accept SemVer-style/CalVer triples and Python a/b/rc prereleases."""
    if not isinstance(tag, str) or VERSION_PATTERN.fullmatch(tag) is None:
        raise ValueError("Use X.Y.Z or vX.Y.Z, optionally followed by aN, bN, or rcN")
    return tag.removeprefix("v")


def read_metadata(root: Path, tag: str, *, allow_template: bool = False) -> dict:
    """Validate package identity without changing any metadata."""
    if (root / ".template-only").exists() and not allow_template:
        raise ValueError(
            "Complete docs/CUSTOMIZATION.md and remove .template-only first"
        )
    if (root / ".release-blocked").exists() and not allow_template:
        raise ValueError(
            "Release blocked: " + (root / ".release-blocked").read_text().strip()
        )
    version = normalize_version(tag)
    folders = sorted((root / "custom_components").iterdir())
    components = [
        path for path in folders if path.is_dir() and path.name != "__pycache__"
    ]
    if len(components) != 1:
        raise ValueError("Exactly one integration directory is required")
    component = components[0]
    if component.is_symlink() or (root / "custom_components").is_symlink():
        raise ValueError("Integration directories must not be symlinks")
    manifest_path = component / "manifest.json"
    hacs_path = root / "hacs.json"
    if manifest_path.is_symlink() or hacs_path.is_symlink():
        raise ValueError("Metadata must not be symlinked")
    manifest = json.loads(manifest_path.read_text())
    hacs = json.loads(hacs_path.read_text())
    domain = manifest.get("domain", "")
    if (
        not isinstance(domain, str)
        or re.fullmatch(r"[a-z][a-z0-9_]*", domain) is None
        or domain != component.name
    ):
        raise ValueError("Manifest domain must match its directory and use snake_case")
    if manifest.get("version") != version:
        raise ValueError(
            "Manifest version must equal the release tag without a v prefix"
        )
    for key in ("name", "documentation", "issue_tracker"):
        if not isinstance(manifest.get(key), str) or not manifest[key].strip():
            raise ValueError(f"Manifest {key} must be a nonempty string")
    owners = manifest.get("codeowners")
    if (
        not isinstance(owners, list)
        or not owners
        or any(
            not isinstance(owner, str) or not owner.startswith("@") for owner in owners
        )
    ):
        raise ValueError("Manifest must name at least one GitHub codeowner")
    if not isinstance(hacs.get("name"), str) or not hacs["name"].strip():
        raise ValueError("hacs.json must contain a name")
    filename = hacs.get("filename", "")
    if (
        hacs.get("zip_release") is not True
        or not isinstance(filename, str)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.zip", filename) is None
    ):
        raise ValueError("hacs.json must enable zip_release and name a safe ZIP asset")
    if not allow_template and (
        domain == "example_integration" or "REPLACE_" in json.dumps(manifest)
    ):
        raise ValueError("Replace the example domain and repository placeholders first")
    return {
        "tag": tag,
        "version": version,
        "domain": domain,
        "component": component.relative_to(root).as_posix(),
        "filename": filename,
        "prerelease": "true" if VERSION_PATTERN.fullmatch(tag)[4] else "false",
    }


def tracked_files(root: Path, component: Path) -> list[tuple[Path, str]]:
    """Reject unsafe/non-runtime tracked content and omit all untracked files."""
    paths = [component.as_posix(), "LICENSE", "NOTICE", "hacs.json"]
    subprocess.run(
        ["git", "diff", "--exit-code", "--", *paths],
        cwd=root,
        check=True,
        capture_output=True,
    )
    result = subprocess.run(
        ["git", "ls-files", "--stage", "-z", "--", *paths],
        cwd=root,
        check=True,
        capture_output=True,
    )
    files = []
    for record in result.stdout.decode().split("\0"):
        if not record:
            continue
        header, filename = record.split("\t", 1)
        mode, _, stage = header.split()
        relative = Path(filename)
        source = root / relative
        if mode not in {"100644", "100755"} or stage != "0":
            raise ValueError(
                f"Only regular, unconflicted files are allowed: {relative}"
            )
        if any(part.is_symlink() for part in (source, *source.parents)):
            raise ValueError(f"Symlinks are not allowed: {relative}")
        if not source.is_file():
            raise ValueError(f"Tracked file is missing: {relative}")
        if filename == "hacs.json":
            continue  # Required in Git; Marketplace reads it outside the ZIP.
        if filename in {"LICENSE", "NOTICE"}:
            archive_name = filename
        else:
            member = relative.relative_to(component)
            if any(
                part.startswith(".")
                or part in {"__pycache__", "tests", "fixtures"}
                or part.startswith("test_")
                for part in member.parts
            ):
                raise ValueError(f"Development/private file in integration: {member}")
            if (
                member.suffix not in RUNTIME_SUFFIXES
                and member.name not in {"LICENSE", "NOTICE", "ATTRIBUTION.txt"}
                and not member.name.startswith("LICENSE.")
                and not (member.parent == Path("brand") and member.suffix == ".txt")
            ):
                raise ValueError(
                    f"Audit and explicitly allow this runtime file: {member}"
                )
            archive_name = member.as_posix()
        files.append((source, archive_name))
    names = [name for _, name in files]
    if len(names) != len(set(names)):
        raise ValueError(
            "Duplicate ZIP member names, possibly conflicting license files"
        )
    required = {"LICENSE", "__init__.py", "manifest.json", "translations/en.json"}
    release_config = root / "release.json"
    if release_config.exists():
        extra = json.loads(release_config.read_text()).get("required_files", [])
        if not isinstance(extra, list) or any(
            not isinstance(name, str)
            or Path(name).is_absolute()
            or ".." in Path(name).parts
            for name in extra
        ):
            raise ValueError(
                "release.json required_files must be relative runtime paths"
            )
        required.update(extra)
    manifest = json.loads((root / component / "manifest.json").read_text())
    if manifest.get("config_flow"):
        required.add("config_flow.py")
    if not required <= set(names):
        raise ValueError(
            f"Required files must be tracked: {sorted(required - set(names))}"
        )
    if "hacs.json" not in {
        record.split("\t", 1)[1]
        for record in result.stdout.decode().split("\0")
        if record
    }:
        raise ValueError("hacs.json must be tracked")
    if (
        len(files) > MAX_FILES
        or sum(path.stat().st_size for path, _ in files) > MAX_BYTES
    ):
        raise ValueError(
            "Package exceeds Marketplace file-count or unpacked-size limit"
        )
    return sorted(files, key=lambda item: item[1])


def build_release(root: Path, output_dir: Path, tag: str) -> Path:
    """Build a deterministic archive without modifying source or existing assets."""
    root = root.resolve()
    metadata = read_metadata(root, tag)
    files = tracked_files(root, Path(metadata["component"]))
    output_dir = output_dir.resolve()
    if output_dir.is_relative_to(root / metadata["component"]):
        raise ValueError("Release output must be outside the integration directory")
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / metadata["filename"]
    # Exclusive creation: an existing asset must never be silently overwritten.
    with archive_path.open("xb") as output:
        try:
            with ZipFile(output, "w", ZIP_DEFLATED, compresslevel=9) as archive:
                for source, name in files:
                    info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                    info.compress_type = ZIP_DEFLATED
                    info.create_system = 3
                    info.external_attr = 0o100644 << 16
                    with (
                        source.open("rb") as content,
                        archive.open(info, "w") as member,
                    ):
                        shutil.copyfileobj(content, member)
            output.flush()
            with ZipFile(archive_path) as archive:
                if archive.testzip() is not None:
                    raise ValueError("Release ZIP failed its integrity check")
                manifest = json.loads(archive.read("manifest.json"))
                if manifest["version"] != metadata["version"]:
                    raise ValueError("Packaged version differs from the release tag")
        except BaseException:
            archive_path.unlink(missing_ok=True)
            raise
    return archive_path


def main() -> None:
    """Read metadata or create an archive from the current repository."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--tag", required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("dist"))
    parser.add_argument("--metadata-only", action="store_true")
    args = parser.parse_args()
    metadata = read_metadata(args.root.resolve(), args.tag)
    if not args.metadata_only:
        print(build_release(args.root, args.output_dir, args.tag))
    print(json.dumps(metadata, sort_keys=True))
    if output := os.environ.get("GITHUB_OUTPUT"):
        with Path(output).open("a") as stream:
            for key, value in metadata.items():
                stream.write(f"{key}={value}\n")


if __name__ == "__main__":
    main()
