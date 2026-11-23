#!/usr/bin/env python3
"""Deterministic icon extractor & layer compositor for Mindustry 160.8.

Reads authentic game assets from:
  - raw/mindustry/Mindustry-160.8/core/assets-raw/sprites/{items,blocks,units}/
  - raw/mindustry/Mindustry-160.8/core/assets/fonts/icon.ttf (power glyph \ue810, Pal.accent #ffd37f)
  - raw/mindustry/heat-unit.png (Mindustry heat icon provided in raw/mindustry/)
  - packs/mindustry/160.8/{resources,machines}.json

Writes resized/composited square PNGs (<= 64x64, V-ICON-1 compliant) into:
  - .tmp_icons/mindustry/160.8/{resources,machines,options}/

Uses Python 3 stdlib + system ImageMagick (`magick`). Never fabricates dummy PNGs;
text-only option sets remain waived in waivers.json.
"""

from __future__ import annotations

import json
import shutil
import struct
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
RAW_MINDUSTRY = REPO_ROOT / "raw" / "mindustry"
SPRITES_ROOT = RAW_MINDUSTRY / "Mindustry-160.8" / "core" / "assets-raw" / "sprites"
ICON_FONT = RAW_MINDUSTRY / "Mindustry-160.8" / "core" / "assets" / "fonts" / "icon.ttf"
HEAT_ICON_SRC = RAW_MINDUSTRY / "heat-unit.png"
PKG_DIR = REPO_ROOT / "packs" / "mindustry" / "160.8"
OUT_ICONS = REPO_ROOT / ".tmp_icons" / "mindustry" / "160.8"

# Exact authentic layer stacks matching Mindustry 160.8 Block.icons() / DrawMulti.icons()
# (bottom-to-top order; "" denotes the base `<id>.png` sprite).
BLOCK_LAYER_STACKS: dict[str, list[str]] = {
    # Crafters & attribute/heat crafters
    "phase-weaver": ["-bottom", "-weave", ""],
    "cryofluid-mixer": ["-bottom", ""],
    "melter": ["-bottom", ""],
    "separator": ["-bottom", "-spinner", ""],
    "disassembler": ["-bottom", "-spinner", ""],
    "spore-press": ["-bottom", "-piston-icon", "", "-top"],
    "pulverizer": ["", "-rotator", "-top"],
    "silicon-arc-furnace": ["-bottom", ""],
    "electrolyzer": ["-bottom", ""],
    "atmospheric-concentrator": ["-bottom", ""],
    "carbide-crucible": ["-bottom", ""],
    "slag-centrifuge": ["-bottom", ""],
    "surge-crucible": ["-bottom", ""],
    "cyanogen-synthesizer": ["-bottom", ""],
    "phase-synthesizer": ["-bottom", "-weave", ""],
    "cultivator": ["-bottom", "", "-top"],
    "vent-condenser": ["-bottom", "-rotator", "-mid", ""],
    # Heat producers (DrawHeatOutput adds -top1)
    "oxidation-chamber": ["-bottom", "", "-top1"],
    "electric-heater": ["", "-top1"],
    "slag-heater": ["-bottom", "", "-top1"],
    "phase-heater": ["", "-top1"],
    "heat-reactor": ["", "-top1"],
    # Power generators
    "steam-generator": ["", "-turbine", "-cap"],
    "turbine-condenser": ["", "-rotator"],
    "impact-reactor": ["-bottom", ""],
    "chemical-combustion-chamber": ["-bottom", "-piston-icon", "-mid", ""],
    "pyrolysis-generator": ["-bottom", "-piston-icon", "-mid", ""],
    "flux-reactor": ["-bottom", "-mid", ""],
    "neoplasia-reactor": ["-bottom", "", "-top1"],
    # Drills & solid pumps (Drill.icons / SolidPump.icons: base, rotator, top)
    "mechanical-drill": ["", "-rotator", "-top"],
    "pneumatic-drill": ["", "-rotator", "-top"],
    "laser-drill": ["", "-rotator", "-top"],
    "blast-drill": ["", "-rotator", "-top"],
    "water-extractor": ["", "-rotator", "-top"],
    "oil-extractor": ["", "-rotator", "-top"],
    # BurstDrill, BeamDrill, WallCrafter: base, top
    "impact-drill": ["", "-top"],
    "eruption-drill": ["", "-top"],
    "plasma-bore": ["", "-top"],
    "large-plasma-bore": ["", "-top"],
    "cliff-crusher": ["", "-top"],
    "large-cliff-crusher": ["", "-top"],
    # Unit factories, reconstructors, constructor: base, top (if present)
    "tank-fabricator": ["", "-top"],
    "ship-fabricator": ["", "-top"],
    "mech-fabricator": ["", "-top"],
    "additive-reconstructor": ["", "-top"],
    "multiplicative-reconstructor": ["", "-top"],
    "exponential-reconstructor": ["", "-top"],
    "tetrative-reconstructor": ["", "-top"],
    "tank-refabricator": ["", "-top"],
    "ship-refabricator": ["", "-top"],
    "mech-refabricator": ["", "-top"],
    "prime-refabricator": ["", "-top"],
    "constructor": ["", "-top"],
    # Unit assemblers: base, side1, top
    "tank-assembler": ["", "-side1", "-top"],
    "ship-assembler": ["", "-side1", "-top"],
    "mech-assembler": ["", "-side1", "-top"],
}


def png_dimensions(path: Path) -> tuple[int, int]:
    hdr = path.read_bytes()[:24]
    if hdr[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"Not a PNG file: {path}")
    return struct.unpack(">II", hdr[16:24])


def build_square_png(magick_bin: str, layers: list[Path], out_path: Path) -> None:
    """Composite layers centered on a transparent square canvas, area-downscale to <= 64x64, strip metadata."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    max_w = 0
    max_h = 0
    for lp in layers:
        w, h = png_dimensions(lp)
        max_w = max(max_w, w)
        max_h = max(max_h, h)
    canvas = max(max_w, max_h)
    target = min(canvas, 64)

    cmd: list[str] = [magick_bin, "-size", f"{canvas}x{canvas}", "xc:none"]
    for lp in layers:
        cmd.extend([str(lp), "-gravity", "center", "-compose", "over", "-composite"])
    if canvas > 64:
        cmd.extend(["-filter", "Box", "-resize", f"{target}x{target}!"])
    cmd.extend(["-strip", "-define", "png:exclude-chunk=date,time", f"PNG32:{out_path}"])
    subprocess.run(cmd, check=True)


def render_power_glyph_png(magick_bin: str, out_path: Path) -> None:
    """Render official Mindustry Iconc.power (\ue810 from icon.ttf) in Pal.accent (#ffd37f) at 64x64."""
    if not ICON_FONT.exists():
        raise RuntimeError(f"Missing Mindustry icon font: {ICON_FONT}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            magick_bin,
            "-background", "none",
            "-fill", "#ffd37f",
            "-font", str(ICON_FONT),
            "-pointsize", "56",
            "-gravity", "center",
            "-size", "64x64",
            "label:\ue810",
            "-trim", "+repage",
            "-resize", "56x56",
            "-gravity", "center",
            "-background", "none",
            "-extent", "64x64",
            "-strip", "-define", "png:exclude-chunk=date,time",
            f"PNG32:{out_path}",
        ],
        check=True,
    )


def main() -> int:
    magick_bin = shutil.which("magick")
    if not magick_bin:
        raise RuntimeError("ImageMagick `magick` binary not found on PATH")

    resources = json.loads((PKG_DIR / "resources.json").read_text(encoding="utf-8"))["resources"]
    machines = json.loads((PKG_DIR / "machines.json").read_text(encoding="utf-8"))["machines"]

    items_map = {p.stem: p for p in (SPRITES_ROOT / "items").rglob("*.png")}
    units_map = {p.stem: p for p in (SPRITES_ROOT / "units").rglob("*.png")}
    blocks_map = {p.stem: p for p in (SPRITES_ROOT / "blocks").rglob("*.png")}

    # Clean output icon scratch directory
    if OUT_ICONS.exists():
        shutil.rmtree(OUT_ICONS)
    OUT_ICONS.mkdir(parents=True, exist_ok=True)

    counts = {"resources": 0, "machines": 0, "options": 0}

    # 1. Resource icons (100% coverage: items, liquids, gases, payloads, units, heat, power)
    for r in resources:
        rid = r["id"]
        kind = r["kind"]
        out_path = OUT_ICONS / "resources" / f"{rid}.png"
        if kind == "heat":
            if not HEAT_ICON_SRC.exists():
                raise RuntimeError(f"Missing raw heat icon: {HEAT_ICON_SRC}")
            build_square_png(magick_bin, [HEAT_ICON_SRC], out_path)
            counts["resources"] += 1
            continue
        if kind == "power":
            render_power_glyph_png(magick_bin, out_path)
            counts["resources"] += 1
            continue
        if kind == "item":
            src = items_map.get(f"item-{rid}")
        elif kind in ("liquid", "gas"):
            src = items_map.get(f"liquid-{rid}")
        elif kind == "payload":
            src = blocks_map.get(rid)
        elif kind == "unit":
            src = units_map.get(rid)
        else:
            raise RuntimeError(f"Unexpected resource kind {kind!r} for {rid!r}")
        if not src:
            raise RuntimeError(f"Missing authentic sprite for resource {rid!r} (kind={kind})")
        build_square_png(magick_bin, [src], out_path)
        counts["resources"] += 1

    # 2. Machine icons (with authentic multi-layer compositing)
    for m in machines:
        mid = m["id"]
        suffixes = BLOCK_LAYER_STACKS.get(mid, [""])
        layers: list[Path] = []
        for suf in suffixes:
            key = f"{mid}{suf}"
            if key not in blocks_map:
                raise RuntimeError(f"Missing layer sprite {key!r} for machine {mid!r}")
            layers.append(blocks_map[key])
        build_square_png(magick_bin, layers, OUT_ICONS / "machines" / f"{mid}.png")
        counts["machines"] += 1

    # 3. Authentic option icons for overdrive_tiers (projector, projector-phase, dome)
    option_sources = {
        ("overdrive_tiers", "projector"): [blocks_map["overdrive-projector"]],
        ("overdrive_tiers", "projector-phase"): [items_map["item-phase-fabric"]],
        ("overdrive_tiers", "dome"): [blocks_map["overdrive-dome"]],
    }
    for (opt_set, opt_key), layers in sorted(option_sources.items()):
        build_square_png(magick_bin, layers, OUT_ICONS / "options" / opt_set / f"{opt_key}.png")
        counts["options"] += 1

    print(
        f"Built authentic Mindustry icons in {OUT_ICONS.relative_to(REPO_ROOT)}: "
        f"{counts['resources']} resources, {counts['machines']} machines, {counts['options']} options"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
