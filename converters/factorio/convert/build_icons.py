#!/usr/bin/env python3
"""Stage authentic Factorio 2.1.25 PNG icons into .tmp_icons/factorio/2.1.25/.

Copies native <= 64x64 square PNG sprites directly from
raw/factorio/2.1.25/script-output/ with zero fabricated placeholder icons.
"""

from __future__ import annotations

import json
import shutil
import struct
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = REPO_ROOT / "raw" / "factorio" / "2.1.25" / "script-output"
PKG_DIR = REPO_ROOT / "packs" / "factorio" / "2.1.25"
ICON_OUT = REPO_ROOT / ".tmp_icons" / "factorio" / "2.1.25"

# Authentic Factorio 2.1.25 sprites for split/typed/passive entities
SPECIAL_RESOURCE_ICONS = {
    "steam-165c": RAW_DIR / "fluid" / "steam.png",
    "steam-500c": RAW_DIR / "fluid" / "steam.png",
    "heat": RAW_DIR / "virtual-signal" / "signal-thermometer-red.png",
    "power": RAW_DIR / "virtual-signal" / "signal-lightning.png",
    "science": RAW_DIR / "item" / "science.png",
}

SPECIAL_MACHINE_ICONS = {
    "spoiling": RAW_DIR / "item" / "spoilage.png",
}

SURFACE_OPTION_ICONS = {
    "nauvis": RAW_DIR / "space-location" / "nauvis.png",
    "vulcanus": RAW_DIR / "space-location" / "vulcanus.png",
    "gleba": RAW_DIR / "space-location" / "gleba.png",
    "fulgora": RAW_DIR / "space-location" / "fulgora.png",
    "aquilo": RAW_DIR / "space-location" / "aquilo.png",
    "space-platform": RAW_DIR / "surface" / "space-platform.png",
}

SOLAR_LOCATION_ICONS = {
    "nauvis-surface": RAW_DIR / "space-location" / "nauvis.png",
    "vulcanus-surface": RAW_DIR / "space-location" / "vulcanus.png",
    "gleba-surface": RAW_DIR / "space-location" / "gleba.png",
    "fulgora-surface": RAW_DIR / "space-location" / "fulgora.png",
    "aquilo-surface": RAW_DIR / "space-location" / "aquilo.png",
    "nauvis-orbit": RAW_DIR / "space-location" / "nauvis.png",
    "vulcanus-orbit": RAW_DIR / "space-location" / "vulcanus.png",
    "gleba-orbit": RAW_DIR / "space-location" / "gleba.png",
    "fulgora-orbit": RAW_DIR / "space-location" / "fulgora.png",
    "aquilo-orbit": RAW_DIR / "space-location" / "aquilo.png",
    "solar-system-edge": RAW_DIR / "space-location" / "solar-system-edge.png",
}


def verify_png_v_icon_1(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"Not a PNG: {path}")
    w, h = struct.unpack(">II", data[16:24])
    if w != h or w > 64 or w <= 0:
        raise ValueError(f"Icon fails V-ICON-1 ({w}x{h}): {path}")
    return w, h


def copy_icon(src: Path, dst: Path) -> None:
    if not src.exists():
        raise FileNotFoundError(f"Missing raw icon: {src}")
    verify_png_v_icon_1(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)


def stage_icons() -> dict[str, int]:
    if ICON_OUT.exists():
        shutil.rmtree(ICON_OUT)
    ICON_OUT.mkdir(parents=True, exist_ok=True)

    with open(PKG_DIR / "game.json", "r", encoding="utf-8") as f:
        manifest = json.load(f)
    with open(PKG_DIR / "resources.json", "r", encoding="utf-8") as f:
        resources = json.load(f)["resources"]
    with open(PKG_DIR / "machines.json", "r", encoding="utf-8") as f:
        machines = json.load(f)["machines"]

    counts = {"resources": 0, "machines": 0, "options": 0}

    # 1. Resources
    for r in resources:
        rid = r["id"]
        kind = r["kind"]
        if rid in SPECIAL_RESOURCE_ICONS:
            src = SPECIAL_RESOURCE_ICONS[rid]
        elif kind == "fluid":
            src = RAW_DIR / "fluid" / f"{rid}.png"
        else:
            src = RAW_DIR / "item" / f"{rid}.png"
            if not src.exists():
                src = RAW_DIR / "entity" / f"{rid}.png"
        copy_icon(src, ICON_OUT / "resources" / f"{rid}.png")
        counts["resources"] += 1

    # 2. Machines
    for m in machines:
        mid = m["id"]
        if mid in SPECIAL_MACHINE_ICONS:
            src = SPECIAL_MACHINE_ICONS[mid]
        else:
            src = RAW_DIR / "entity" / f"{mid}.png"
        copy_icon(src, ICON_OUT / "machines" / f"{mid}.png")
        counts["machines"] += 1

    # 3. Visual option sets (text-only sets waived in waivers.json)
    opt_sets = manifest.get("option_sets") or {}
    for opt in opt_sets.get("qualities", {}).get("options", []):
        k = opt["key"]
        copy_icon(RAW_DIR / "quality" / f"{k}.png", ICON_OUT / "options" / "qualities" / f"{k}.png")
        counts["options"] += 1

    for opt in opt_sets.get("modules", {}).get("options", []):
        k = opt["key"]
        copy_icon(RAW_DIR / "item" / f"{k}.png", ICON_OUT / "options" / "modules" / f"{k}.png")
        counts["options"] += 1

    for opt in opt_sets.get("surfaces", {}).get("options", []):
        k = opt["key"]
        if k in SURFACE_OPTION_ICONS:
            copy_icon(SURFACE_OPTION_ICONS[k], ICON_OUT / "options" / "surfaces" / f"{k}.png")
            counts["options"] += 1

    for opt in opt_sets.get("solar_locations", {}).get("options", []):
        k = opt["key"]
        if k in SOLAR_LOCATION_ICONS:
            copy_icon(SOLAR_LOCATION_ICONS[k], ICON_OUT / "options" / "solar_locations" / f"{k}.png")
            counts["options"] += 1

    return counts


if __name__ == "__main__":
    c = stage_icons()
    print(f"Staged {sum(c.values())} authentic Factorio 2.1.25 icons into {ICON_OUT}: {c}")
