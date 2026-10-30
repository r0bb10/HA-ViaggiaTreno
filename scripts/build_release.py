"""Validate a CalVer tag and build a reproducible, integration-only HACS ZIP."""

import argparse
import json
import re
import subprocess
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = Path("custom_components/viaggiatreno")
VERSION = re.compile(r"20\d{2}\.(?:[1-9]|1[0-2])\.[1-9]\d*\Z")
SUFFIXES = {".py", ".json", ".js", ".svg", ".png"}


def validate_release(root: Path, tag: str | None = None) -> str:
    """Fail before publishing if the tag or HACS download configuration disagrees."""
    manifest = json.loads((root / INTEGRATION / "manifest.json").read_text())
    hacs = json.loads((root / "hacs.json").read_text())
    if tag is None:
        tag = manifest["version"]
    version = tag.removeprefix("v")
    if not VERSION.fullmatch(version) or version != manifest["version"]:
        raise ValueError(
            "Tag must match manifest version: [v]YYYY.month.release-counter"
        )
    if manifest["domain"] != "viaggiatreno":
        raise ValueError("Unexpected integration domain")
    if not hacs.get("zip_release") or hacs.get("filename") != "viaggiatreno.zip":
        raise ValueError("HACS must be configured to download viaggiatreno.zip")
    return tag


def build_release(root: Path, output: Path) -> Path:
    """Include only tracked runtime files, with manifest.json at the ZIP root."""
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", str(INTEGRATION)],
        cwd=root,
        check=True,
        capture_output=True,
    )
    files = sorted(Path(name) for name in result.stdout.decode().split("\0") if name)
    included = []
    for path in files:
        relative = path.relative_to(INTEGRATION)
        if path.suffix not in SUFFIXES or any(
            part.startswith(".") or part in {"__pycache__", "tests"}
            for part in relative.parts
        ):
            continue
        if (root / path).is_symlink():
            raise ValueError(f"Release files must not be symlinks: {path}")
        included.append((path, relative.as_posix()))
    required = {"__init__.py", "manifest.json", "static/viaggiatreno-card.js"}
    if not required <= {name for _, name in included}:
        raise ValueError("Required integration files are missing from Git")
    output.mkdir(parents=True, exist_ok=True)
    archive = output / "viaggiatreno.zip"
    with ZipFile(archive, "w", compression=ZIP_DEFLATED, compresslevel=9) as package:
        for path, name in included:
            # Fixed metadata makes identical sources produce identical archives.
            info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            package.writestr(info, (root / path).read_bytes())
    return archive


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="Existing tag; defaults to the manifest version")
    parser.add_argument("--github-output", type=Path, help="Write validated tag output")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    try:
        tag = validate_release(ROOT, args.tag)
        if args.github_output:
            with args.github_output.open("a") as output:
                output.write(f"tag={tag}\n")
        if not args.check_only:
            print(build_release(ROOT, args.output))
    except ValueError as err:
        parser.error(str(err))


if __name__ == "__main__":
    main()
