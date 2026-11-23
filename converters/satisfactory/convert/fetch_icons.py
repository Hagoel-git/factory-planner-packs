#!/usr/bin/env python3
"""Download 64x64 Satisfactory icon PNGs into .tmp_icons/ using SFTools public API."""

from __future__ import annotations

import json
import re
import struct
import sys
import urllib.error
import urllib.request
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

API = "https://api.new.satisfactorytools.com"
ICON_HASH_RE = re.compile(r"^[A-Za-z0-9_-]+$")
SIZE = 64

REPO_ROOT = Path(__file__).resolve().parents[3]
REPORT_PATH = REPO_ROOT / "converters" / "satisfactory" / "report.json"

BELT_TIER_CLASSES = {
    f"mk{i}": f"Desc_ConveyorBeltMk{i}_C" for i in range(1, 7)
}


def build_to_desc(cls: str) -> str:
    return f"Desc_{cls[6:]}" if cls.startswith("Build_") else cls


def write_purity_badge_png(dest: Path, pips: int, rgb: tuple[int, int, int]) -> None:
    """Generate a deterministic 64x64 RGBA PNG badge with 1-3 purity pips using stdlib only."""
    w = h = SIZE
    bg = (28, 32, 38, 220)
    border = (rgb[0], rgb[1], rgb[2], 255)
    centers = {
        1: [(32.0, 32.0)],
        2: [(22.0, 32.0), (42.0, 32.0)],
        3: [(32.0, 21.0), (21.0, 41.0), (43.0, 41.0)],
    }[pips]

    rows = bytearray()
    for y in range(h):
        rows.append(0)  # PNG filter type 0
        for x in range(w):
            dx = abs(x + 0.5 - 32.0)
            dy = abs(y + 0.5 - 32.0)
            # Rounded square distance (half-size 28, corner radius 10)
            qx = max(dx - 18.0, 0.0)
            qy = max(dy - 18.0, 0.0)
            sd = (qx * qx + qy * qy) ** 0.5 - 10.0
            if sd > 1.0:
                rows.extend((0, 0, 0, 0))
                continue
            r, g, b, a = bg
            if sd > -1.5:
                r, g, b, a = border
            else:
                for cx, cy in centers:
                    dist = ((x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2) ** 0.5
                    if dist <= 7.5:
                        t = max(0.0, 1.0 - (dist / 7.5) ** 2)
                        r = min(255, int(rgb[0] + (255 - rgb[0]) * 0.35 * t))
                        g = min(255, int(rgb[1] + (255 - rgb[1]) * 0.35 * t))
                        b = min(255, int(rgb[2] + (255 - rgb[2]) * 0.35 * t))
                        a = 255
                        break
            if sd > 0.0:
                a = int(a * max(0.0, 1.0 - sd))
            rows.extend((r, g, b, a))

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    idat = zlib.compress(bytes(rows), 9)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(png)


def generate_local_option_badges(out_dir: Path) -> int:
    """Generate deterministic node_purity badge PNGs locally (no network required)."""
    purity_specs = {
        "impure": (1, (224, 128, 56)),
        "normal": (2, (90, 195, 225)),
        "pure": (3, (195, 110, 245)),
    }
    for key, (pips, rgb) in purity_specs.items():
        write_purity_badge_png(out_dir / "options" / "node_purity" / f"{key}.png", pips, rgb)
    return len(purity_specs)


def fetch_json(url: str) -> object:
    req = urllib.request.Request(url, headers={"User-Agent": "factory-planner-packs/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def main() -> None:
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    pkg_ver = report["data_version"]
    out_dir = REPO_ROOT / ".tmp_icons" / "satisfactory" / pkg_ver

    badges = generate_local_option_badges(out_dir)
    if "--badges-only" in sys.argv:
        print(f"Generated {badges} local option badge PNGs into {out_dir}.")
        return

    versions = fetch_json(f"{API}/v1/versions")
    assert isinstance(versions, list)
    version = next(
        v
        for v in versions
        if v.get("official") and not v.get("ficsmas") and not v.get("experimental")
    )
    doc = fetch_json(f"{API}/{version['dataPath']}")
    assert isinstance(doc, dict)
    data = doc["data"]

    items_by_cls = data.get("items", {})
    buildings_by_cls = data.get("buildings", {})

    targets: list[tuple[str, Path]] = []
    missing_hashes: list[str] = []

    def queue_icon(icon_hash: object, dest: Path, label: str) -> None:
        if isinstance(icon_hash, str) and ICON_HASH_RE.match(icon_hash):
            targets.append((icon_hash, dest))
        else:
            missing_hashes.append(label)

    # Resources
    for rid, cls in sorted(report["icon_class_map"]["resources"].items()):
        entry = items_by_cls.get(cls) or buildings_by_cls.get(cls) or {}
        queue_icon(entry.get("icon"), out_dir / "resources" / f"{rid}.png", f"resource:{rid} ({cls})")

    # Synthetic geothermal-geyser icon fallback (Geothermal Generator icon)
    geo_entry = items_by_cls.get("Desc_Geyser_C") or buildings_by_cls.get("Desc_GeneratorGeoThermal_C") or {}
    queue_icon(geo_entry.get("icon"), out_dir / "resources" / "geothermal-geyser.png", "resource:geothermal-geyser")

    # Machines (SFTools keys buildings by Desc_*_C)
    for mid, cls in sorted(report["icon_class_map"]["machines"].items()):
        dcls = build_to_desc(cls)
        entry = buildings_by_cls.get(dcls) or buildings_by_cls.get(cls) or items_by_cls.get(cls) or {}
        queue_icon(entry.get("icon"), out_dir / "machines" / f"{mid}.png", f"machine:{mid} ({dcls})")

    # Belt tier option icons
    for key, cls in sorted(BELT_TIER_CLASSES.items()):
        entry = buildings_by_cls.get(cls) or {}
        queue_icon(entry.get("icon"), out_dir / "options" / "belt_tiers" / f"{key}.png", f"option:belt_tiers/{key} ({cls})")

    def download(item: tuple[str, Path]) -> tuple[Path, str | None]:
        icon_hash, dest = item
        if dest.exists() and dest.stat().st_size > 0:
            return dest, None
        dest.parent.mkdir(parents=True, exist_ok=True)
        url = f"{API}/data/images/{SIZE}/{icon_hash}.png"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "factory-planner-packs/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                dest.write_bytes(resp.read())
            return dest, None
        except (urllib.error.URLError, TimeoutError) as exc:
            return dest, f"{url}: {exc}"

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(download, targets))

    failed = [(str(p), err) for p, err in results if err]
    print(
        f"SFTools version={version.get('version')} dataPath={version.get('dataPath')}\n"
        f"Queued {len(targets)} icons ({len(missing_hashes)} missing hashes, {len(failed)} download errors)."
    )
    if missing_hashes:
        print("Missing hashes:", missing_hashes)
    if failed:
        print("Download errors:", failed[:10])
        raise SystemExit(1)


if __name__ == "__main__":
    main()
