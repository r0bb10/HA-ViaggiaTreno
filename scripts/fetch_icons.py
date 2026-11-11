"""Maintainer-only icon acquisition; never called by the running integration.

Download branding embedded in the RFI Tortona monitor ONCE and save image-only
assets. Train data is NOT extracted. Remaining categories use original text
badges. Third-party trademarks remain the property of their respective owners.
Run with Python 3.13+ from any directory. No third-party modules are needed.
"""

import argparse
import base64
import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1] / "custom_components/viaggiatreno/static"
SOURCE = (
    "https://iechub.rfi.it/ArriviPartenze/ArrivalsDepartures/Monitor"
    "?placeId=332&arrivals=False"
)
OPERATORS = {"TRENITALIA": "trenitalia", "TRENORD": "trenord", "INTERCITY": "intercity"}
CATEGORIES = ("REG", "RV", "RE", "S", "IC", "ICN", "EC", "EN", "FR", "FA", "FB")
CATEGORY_IMAGES = {
    "Categoria INTERCITY": "ic",
    "Categoria REG": "reg",
    "Categoria RE": "re",
}


class Icons(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        src = attrs.get("src", "")
        if tag == "img" and src.startswith("data:image/"):
            self.images.setdefault(attrs.get("alt", ""), src.strip())


def badge(text: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="144" height="48" '
        'viewBox="0 0 144 48" role="img">'
        f"<title>{text}</title>"
        '<rect width="144" height="48" rx="8" fill="#174c42"/>'
        '<text x="72" y="31" text-anchor="middle" font-family="sans-serif" '
        f'font-size="23" font-weight="bold" fill="white">{text}</text></svg>\n'
    )


def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--html", type=Path, help="Use an already downloaded RFI page")
    options = args.parse_args()
    if options.html:
        html = options.html.read_text()
    else:
        with urlopen(
            Request(SOURCE, headers={"User-Agent": "Mozilla/5.0"}), timeout=30
        ) as r:
            html = r.read().decode("utf-8")
    parser = Icons()
    parser.feed(html)
    for folder in ("operators", "categories"):
        (ROOT / folder).mkdir(parents=True, exist_ok=True)
        (ROOT / folder / "unknown.svg").write_text(badge("?"))
    for category in CATEGORIES:
        # Never replace separately acquired category artwork with a fallback.
        path = ROOT / "categories" / f"{category.lower()}.svg"
        if not path.exists():
            path.write_text(badge(category))
    provenance = []
    images = [(alt, "operators", name) for alt, name in OPERATORS.items()]
    images.extend(
        (alt, "categories", name)
        for alt, name in CATEGORY_IMAGES.items()
        if alt in parser.images
    )
    for alt, folder, name in images:
        data_uri = parser.images.get(alt)
        if data_uri is None:
            raise RuntimeError(f"Required operator image missing: {alt}")
        # The SVG is only a wrapper for inert GIF/PNG bytes, not upstream markup.
        header, payload = data_uri.split(",", 1)
        raw = base64.b64decode(payload)
        if not raw.startswith((b"GIF87a", b"GIF89a", b"\x89PNG\r\n\x1a\n")):
            raise RuntimeError(f"Unexpected image format for {alt}")
        encoded = base64.b64encode(raw).decode()
        mime = header.split(";")[0].removeprefix("data:")
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="224" height="64" '
            f'viewBox="0 0 224 64" role="img"><title>{alt}</title>'
            f'<image width="224" height="64" '
            f'href="data:{mime};base64,{encoded}"/>'
            "</svg>\n"
        )
        path = ROOT / folder / f"{name}.svg"
        path.write_text(svg)
        provenance.append(
            {
                "file": str(path.relative_to(ROOT)),
                "source": SOURCE,
                "alt": alt,
                "image_sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    # Keep separately acquired artwork when refreshing the RFI image set.
    sources_path = ROOT / "sources.json"
    refreshed = {source["file"] for source in provenance}
    if sources_path.exists():
        provenance.extend(
            source
            for source in json.loads(sources_path.read_text())
            if source["file"] not in refreshed
        )
    sources_path.write_text(json.dumps(provenance, indent=2) + "\n")
    print(f"Downloaded {len(provenance)} icons; generated category fallbacks in {ROOT}")


if __name__ == "__main__":
    main()
