#!/usr/bin/env python3
"""Deterministic converter from Mindustry 160.8 Java source tree to Factory Planner GameData v4.

Reads:
  - raw/mindustry/Mindustry-160.8/core/src/mindustry/content/{Items,Liquids,Blocks,UnitTypes,SerpuloTechTree,ErekirTechTree}.java
  - raw/mindustry/Mindustry-160.8/core/assets/bundles/bundle.properties
  - converters/mindustry/template/{game,overrides,waivers}.json

Writes (strictly scoped):
  - packs/mindustry/160.8/{game,resources,machines,waivers}.json
  - packs/mindustry/160.8/recipes/{crafting,extraction,heat,power,units}.json
  - converters/mindustry/report.json

Never touches raw/, sibling packages, or icons.pak. Uses Python 3 stdlib only.
"""

from __future__ import annotations

import ast
import json
import math
import operator
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
RAW_ROOT = REPO_ROOT / "raw" / "mindustry" / "Mindustry-160.8"
CONV_ROOT = REPO_ROOT / "converters" / "mindustry"
TEMPLATE_DIR = CONV_ROOT / "template"
OUT_PKG = REPO_ROOT / "packs" / "mindustry" / "160.8"
REPORT_PATH = CONV_ROOT / "report.json"

TICKS_PER_SECOND = 60.0
HARDNESS_DRILL_MULT = 50.0
ASSEMBLER_MODULE_POWER = 3.5 * TICKS_PER_SECOND  # basic-assembler-module: consumePower(3.5f) = 210 u/s

# Exact slugify() matching core_gamedata (src/common/StringUtils.h, author reference §8.2)
def slugify(text: str) -> str:
    s = text.strip().lower()
    s = s.replace("+", "plus")
    s = re.sub(r"[:./]", "-", s)
    s = re.sub(r"[^a-z0-9\s:._-]", "", s)
    s = re.sub(r"[\s-]+", "-", s)
    return s.strip("-")


def clean_num(val: float) -> int | float:
    if not math.isfinite(val):
        raise ValueError(f"Non-finite number encountered: {val!r}")
    r = round(float(val), 10)
    if abs(r) <= 1e-12:
        return 0
    if abs(r - round(r)) <= 1e-10:
        return int(round(r))
    return r


def strip_java_comments(text: str) -> str:
    # Remove /* ... */ and // ... comments without touching string literals
    pattern = re.compile(r'("(?:\\.|[^"\\])*")|(/\*[\s\S]*?\*/)|(//[^\n]*)')
    return pattern.sub(lambda m: m.group(1) if m.group(1) else "", text)


_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def eval_java_number(expr: str, env: dict[str, float] | None = None) -> float:
    """Safely evaluate a Java arithmetic expression like '60f * 2.25f / 4f' or 'heating / coolantPower'."""
    s = expr.strip()
    # Strip trailing 'f'/'F'/'d'/'D' on numeric literals (not inside identifiers)
    s = re.sub(r"(?<![A-Za-z0-9_])(\d+(?:\.\d+)?|\.\d+)[fFdD](?![A-Za-z0-9_])", r"\1", s)
    # Leading decimal like .5 -> 0.5
    s = re.sub(r"(?<![A-Za-z0-9_])\.(\d+)", r"0.\1", s)
    node = ast.parse(s, mode="eval").body
    local_env = env or {}

    def _eval(n: ast.AST) -> float:
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return float(n.value)
        if isinstance(n, ast.Name):
            if n.id in local_env:
                return float(local_env[n.id])
            raise ValueError(f"Unknown variable {n.id!r} in numeric expression {expr!r}")
        if isinstance(n, ast.UnaryOp) and type(n.op) in _UNARY_OPS:
            return _UNARY_OPS[type(n.op)](_eval(n.operand))
        if isinstance(n, ast.BinOp) and type(n.op) in _BIN_OPS:
            return _BIN_OPS[type(n.op)](_eval(n.left), _eval(n.right))
        raise ValueError(f"Unsupported AST {ast.dump(n)} in numeric expression {expr!r}")

    return _eval(node)


def parse_bundle(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            v = v.strip()
            # Decode simple unicode escapes if any
            if "\\u" in v:
                v = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), v)
            # Strip Mindustry color tags like [accent]
            v = re.sub(r"\[[a-zA-Z0-9#]*\]", "", v)
            out[k.strip()] = v.strip()
    return out


def extract_top_level_decls(java_text: str) -> list[tuple[str, str, str, str]]:
    """Extract top-level 'var = new ClassName(args){{ body }};' or 'var = new ClassName(args);' blocks.

    Returns list of (var_name, class_name, ctor_args, body_text).
    """
    clean = strip_java_comments(java_text)
    decls: list[tuple[str, str, str, str]] = []
    # Match declarations indented inside load()
    pat = re.compile(r"^[ \t]{4,12}(\w+)\s*=\s*new\s+([A-Z]\w*)\s*\(", re.M)
    pos = 0
    while True:
        m = pat.search(clean, pos)
        if not m:
            break
        var_name, cls_name = m.group(1), m.group(2)
        # Find matching ')' for constructor args
        i = m.end()
        depth = 1
        in_str = False
        esc = False
        while i < len(clean) and depth > 0:
            ch = clean[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
            i += 1
        ctor_args = clean[m.end():i - 1].strip()
        # Skip whitespace
        j = i
        while j < len(clean) and clean[j] in " \t\r\n":
            j += 1
        body = ""
        if j < len(clean) and clean[j] == "{":
            bstart = j
            bdepth = 0
            in_str = False
            esc = False
            while j < len(clean):
                ch = clean[j]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                else:
                    if ch == '"':
                        in_str = True
                    elif ch == "{":
                        bdepth += 1
                    elif ch == "}":
                        bdepth -= 1
                        if bdepth == 0:
                            j += 1
                            break
                j += 1
            body = clean[bstart:j]
        decls.append((var_name, cls_name, ctor_args, body))
        pos = j
    return decls


def first_string_arg(ctor_args: str) -> str | None:
    m = re.match(r'\s*"([^"]+)"', ctor_args)
    return m.group(1) if m else None


def find_field_expr(body: str, field: str) -> str | None:
    # Match 'field = expr;' at statement level (avoiding ==, !=, <=, >= and nested anonymous classes)
    # Remove nested {{ ... }} or { ... } inside drawer = ... before searching top-level fields
    top = strip_nested_blocks(body)
    m = re.search(rf"(?<![A-Za-z0-9_.]){re.escape(field)}\s*=\s*([^;]+);", top)
    return m.group(1).strip() if m else None


def strip_nested_blocks(body: str) -> str:
    """Keep only depth 1-2 content of a Java double-brace block '{{ ... }}' and replace deeper '{...}' with '{}'."""
    if not body:
        return ""
    # Strip outer '{' ... '}' and inner '{' ... '}' if double-brace
    s = body.strip()
    if s.startswith("{{") and s.endswith("}}"):
        inner = s[2:-2]
    elif s.startswith("{") and s.endswith("}"):
        inner = s[1:-1]
    else:
        inner = s

    out: list[str] = []
    depth = 0
    in_str = False
    esc = False
    for ch in inner:
        if in_str:
            if depth == 0:
                out.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            if depth == 0:
                out.append(ch)
        elif ch == "{":
            if depth == 0:
                out.append("{}")
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
        else:
            if depth == 0:
                out.append(ch)
    return "".join(out)


def parse_items(path: Path) -> tuple[dict[str, dict[str, Any]], set[str], set[str]]:
    text = path.read_text(encoding="utf-8")
    clean = strip_java_comments(text)
    items: dict[str, dict[str, Any]] = {}
    for var, cls, ctor, body in extract_top_level_decls(clean):
        if cls != "Item":
            continue
        raw_id = first_string_arg(ctor)
        if not raw_id:
            continue
        top = strip_nested_blocks(body)
        def _num(f: str, d: float) -> float:
            e = find_field_expr(body, f)
            return eval_java_number(e) if e else d
        items[var] = {
            "var": var,
            "id": slugify(raw_id),
            "raw_id": raw_id,
            "hardness": int(round(_num("hardness", 0))),
            "cost": _num("cost", 1.0),
            "flammability": _num("flammability", 0.0),
            "radioactivity": _num("radioactivity", 0.0),
            "explosiveness": _num("explosiveness", 0.0),
            "hidden": bool(re.search(r"\bhidden\s*=\s*true\b", top)),
        }

    def _seq_vars(seq_name: str) -> set[str]:
        m = re.search(rf"{seq_name}\.addAll\(([^)]+)\)", clean)
        if not m:
            return set()
        return {tok.strip() for tok in m.group(1).split(",") if tok.strip()}

    serpulo_vars = _seq_vars("serpuloItems")
    erekir_vars = _seq_vars("erekirItems")
    return items, serpulo_vars, erekir_vars


def parse_liquids(path: Path) -> dict[str, dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    liquids: dict[str, dict[str, Any]] = {}
    for var, cls, ctor, body in extract_top_level_decls(text):
        if cls not in ("Liquid", "CellLiquid"):
            continue
        raw_id = first_string_arg(ctor)
        if not raw_id:
            continue
        top = strip_nested_blocks(body)
        flam_e = find_field_expr(body, "flammability")
        liquids[var] = {
            "var": var,
            "id": slugify(raw_id),
            "raw_id": raw_id,
            "gas": bool(re.search(r"\bgas\s*=\s*true\b", top)),
            "flammability": eval_java_number(flam_e) if flam_e else 0.0,
            "hidden": bool(re.search(r"\bhidden\s*=\s*true\b", top)),
        }
    return liquids


def parse_units(path: Path) -> dict[str, dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    units: dict[str, dict[str, Any]] = {}
    for var, cls, ctor, _body in extract_top_level_decls(text):
        raw_id = first_string_arg(ctor)
        if not raw_id:
            continue
        units[var] = {
            "var": var,
            "id": slugify(raw_id),
            "raw_id": raw_id,
            "class": cls,
        }
    return units


def parse_tech_tree_vars(path: Path) -> set[str]:
    clean = strip_java_comments(path.read_text(encoding="utf-8"))
    # Captures node(blockVar, ...) and nodeProduce(itemOrLiquidVar, ...)
    return set(re.findall(r"node(?:Produce)?\(\s*(?:[A-Za-z]+\.)?(\w+)", clean))


def parse_item_stack_list(expr: str, items_by_var: dict[str, dict[str, Any]]) -> list[tuple[str, float]]:
    """Parse 'with(Items.a, 10, Items.b, 20)' or 'ItemStack.with(...)' into [(item_id, amount), ...]."""
    m = re.search(r"with\s*\(([\s\S]*)\)", expr)
    if not m:
        raise ValueError(f"Could not parse ItemStack list: {expr!r}")
    inner = m.group(1)
    parts = [p.strip() for p in inner.split(",") if p.strip()]
    if len(parts) % 2 != 0 or not parts:
        raise ValueError(f"Odd/empty ItemStack with() args: {expr!r}")
    out: list[tuple[str, float]] = []
    for i in range(0, len(parts), 2):
        im = re.match(r"Items\.(\w+)$", parts[i])
        if not im or im.group(1) not in items_by_var:
            raise ValueError(f"Unknown item ref {parts[i]!r} in {expr!r}")
        amt = eval_java_number(parts[i + 1])
        out.append((items_by_var[im.group(1)]["id"], amt))
    return out


def parse_liquid_stack_list(expr: str, liquids_by_var: dict[str, dict[str, Any]]) -> list[tuple[str, float]]:
    m = re.search(r"with\s*\(([\s\S]*)\)", expr)
    if not m:
        raise ValueError(f"Could not parse LiquidStack list: {expr!r}")
    parts = [p.strip() for p in m.group(1).split(",") if p.strip()]
    if len(parts) % 2 != 0 or not parts:
        raise ValueError(f"Odd/empty LiquidStack with() args: {expr!r}")
    out: list[tuple[str, float]] = []
    for i in range(0, len(parts), 2):
        lm = re.match(r"Liquids\.(\w+)$", parts[i])
        if not lm or lm.group(1) not in liquids_by_var:
            raise ValueError(f"Unknown liquid ref {parts[i]!r} in {expr!r}")
        amt = eval_java_number(parts[i + 1])
        out.append((liquids_by_var[lm.group(1)]["id"], amt))
    return out


def parse_payload_stack_list(
    expr: str,
    units_by_var: dict[str, dict[str, Any]],
    block_ids_by_var: dict[str, str],
) -> list[tuple[str, float]]:
    m = re.search(r"PayloadStack\.list\s*\(([\s\S]*)\)", expr)
    if not m:
        raise ValueError(f"Could not parse PayloadStack.list: {expr!r}")
    parts = [p.strip() for p in m.group(1).split(",") if p.strip()]
    if len(parts) % 2 != 0 or not parts:
        raise ValueError(f"Odd/empty PayloadStack.list args: {expr!r}")
    out: list[tuple[str, float]] = []
    for i in range(0, len(parts), 2):
        ref = parts[i]
        amt = eval_java_number(parts[i + 1])
        if ref.startswith("UnitTypes."):
            uvar = ref.split(".", 1)[1]
            if uvar not in units_by_var:
                raise ValueError(f"Unknown unit ref {ref!r}")
            out.append((units_by_var[uvar]["id"], amt))
        elif ref.startswith("Blocks."):
            bvar = ref.split(".", 1)[1]
            if bvar not in block_ids_by_var:
                raise ValueError(f"Unknown block payload ref {ref!r}")
            out.append((block_ids_by_var[bvar], amt))
        else:
            raise ValueError(f"Unexpected PayloadStack ref {ref!r}")
    return out


def make_short_port(res_id: str, amount: float, chance: float = 1.0, attrs: dict[str, Any] | None = None) -> Any:
    amt = clean_num(amount)
    if amt <= 0:
        raise ValueError(f"Non-positive port amount {amt} for {res_id}")
    if attrs:
        obj: dict[str, Any] = {"res": res_id, "amount": amt}
        if abs(chance - 1.0) > 1e-12:
            obj["chance"] = clean_num(chance)
        obj["attrs"] = dict(sorted(attrs.items()))
        return obj
    if abs(chance - 1.0) > 1e-12:
        return [res_id, amt, clean_num(chance)]
    return [res_id, amt]


def merge_duplicate_ports(
    ports: list[Any],
    recipe_id: str,
    direction: str,
    merged_log: list[dict[str, Any]],
) -> list[Any]:
    """Merge identical duplicate static ports (V-W-3) while preserving first-seen port order."""
    out: list[Any] = []
    index_by_key: dict[tuple[str, float, str], int] = {}
    for p in ports:
        if isinstance(p, list):
            res = p[0]
            amt = float(p[1])
            ch = float(p[2]) if len(p) == 3 else 1.0
            attrs: dict[str, Any] = {}
        else:
            res = p["res"]
            amt = float(p["amount"])
            ch = float(p.get("chance", 1.0))
            attrs = p.get("attrs", {})
        key = (res, round(ch, 10), json.dumps(attrs, sort_keys=True))
        if key in index_by_key:
            idx = index_by_key[key]
            existing = out[idx]
            if isinstance(existing, list):
                existing[1] = clean_num(float(existing[1]) + amt)
            else:
                existing["amount"] = clean_num(float(existing["amount"]) + amt)
            merged_log.append({"recipe": recipe_id, "dir": direction, "resource": res, "added_amount": clean_num(amt)})
        else:
            index_by_key[key] = len(out)
            out.append(p)
    return out


def main() -> int:
    # 1. Load templates & overrides
    template = json.loads((TEMPLATE_DIR / "game.json").read_text(encoding="utf-8"))
    overrides = json.loads((TEMPLATE_DIR / "overrides.json").read_text(encoding="utf-8"))
    waivers = json.loads((TEMPLATE_DIR / "waivers.json").read_text(encoding="utf-8"))
    excluded_blocks = set(overrides.get("exclude_blocks", []))
    rename_resources: dict[str, str] = overrides.get("rename_resources", {})
    rename_machines: dict[str, str] = overrides.get("rename_machines", {})

    # 2. Parse raw Mindustry 160.8 Java sources & localization
    content_dir = RAW_ROOT / "core" / "src" / "mindustry" / "content"
    bundle = parse_bundle(RAW_ROOT / "core" / "assets" / "bundles" / "bundle.properties")
    items_by_var, serpulo_item_vars, erekir_item_vars = parse_items(content_dir / "Items.java")
    liquids_by_var = parse_liquids(content_dir / "Liquids.java")
    units_by_var = parse_units(content_dir / "UnitTypes.java")
    serpulo_tree = parse_tech_tree_vars(content_dir / "SerpuloTechTree.java")
    erekir_tree = parse_tech_tree_vars(content_dir / "ErekirTechTree.java")

    blocks_text = (content_dir / "Blocks.java").read_text(encoding="utf-8")
    raw_block_decls = extract_top_level_decls(blocks_text)

    # Index block IDs by var and capture Wall requirements / OreBlocks / liquid floors
    block_ids_by_var: dict[str, str] = {}
    wall_reqs_by_var: dict[str, list[tuple[str, float]]] = {}
    wall_build_mult_by_var: dict[str, float] = {}
    floor_ore_vars: set[str] = set()
    wall_ore_vars: set[str] = set()
    liquid_floor_mults: dict[str, set[float]] = defaultdict(set)

    for var, cls, ctor, body in raw_block_decls:
        raw_id = first_string_arg(ctor)
        top = strip_nested_blocks(body)
        if raw_id:
            block_ids_by_var[var] = slugify(raw_id)

        # OreBlock / Floor / StaticWall drops
        if cls == "OreBlock":
            im = re.search(r"Items\.(\w+)", ctor)
            if im:
                if re.search(r"\bwallOre\s*=\s*true\b", top):
                    wall_ore_vars.add(im.group(1))
                else:
                    floor_ore_vars.add(im.group(1))
        else:
            im = re.search(r"\bitemDrop\s*=\s*Items\.(\w+)", top)
            if im:
                if cls == "StaticWall" or re.search(r"\bwallOre\s*=\s*true\b", top):
                    wall_ore_vars.add(im.group(1))
                else:
                    floor_ore_vars.add(im.group(1))
            lm = re.search(r"\bliquidDrop\s*=\s*Liquids\.(\w+)", top)
            if lm:
                lmult_e = find_field_expr(body, "liquidMultiplier")
                mult = eval_java_number(lmult_e) if lmult_e else 1.0
                liquid_floor_mults[liquids_by_var[lm.group(1)]["id"]].add(round(mult, 6))

        # Capture Wall requirements & buildCostMultiplier for Constructor payload recipes
        if cls == "Wall":
            bm_e = find_field_expr(body, "buildCostMultiplier")
            wall_build_mult_by_var[var] = eval_java_number(bm_e) if bm_e else 1.0
            rm_direct = re.search(r"requirements\([^,]+,\s*(?:BuildVisibility\.\w+,\s*)?(with\([\s\S]*?\))\s*\)", top)
            rm_mult = re.search(r"requirements\([^,]+,\s*ItemStack\.mult\(\s*(\w+)\.requirements\s*,\s*([^)]+)\)\s*\)", top)
            if rm_direct:
                wall_reqs_by_var[var] = parse_item_stack_list(rm_direct.group(1), items_by_var)
            elif rm_mult:
                base_var = rm_mult.group(1)
                factor = eval_java_number(rm_mult.group(2))
                if base_var not in wall_reqs_by_var:
                    raise RuntimeError(f"Base wall {base_var} not parsed before {var}")
                wall_reqs_by_var[var] = [(rid, amt * factor) for rid, amt in wall_reqs_by_var[base_var]]

    # Planet helpers for ores and liquids
    def item_planet(ivar: str) -> str:
        in_s = ivar in serpulo_item_vars
        in_e = ivar in erekir_item_vars
        if in_s and in_e:
            return "both"
        if in_s:
            return "serpulo"
        if in_e:
            return "erekir"
        return "both"

    serpulo_pump_liquids = {"water", "slag", "oil", "cryofluid"}
    erekir_pump_liquids = {"water", "slag", "arkycite"}

    def liquid_planet(lid: str) -> str:
        in_s = lid in serpulo_pump_liquids
        in_e = lid in erekir_pump_liquids
        if in_s and in_e:
            return "both"
        if in_s:
            return "serpulo"
        if in_e:
            return "erekir"
        return "both"

    def block_planet(var: str, is_debug: bool) -> str:
        if is_debug:
            return "both"
        in_s = var in serpulo_tree
        in_e = var in erekir_tree
        if in_s and in_e:
            return "both"
        if in_s:
            return "serpulo"
        if in_e:
            return "erekir"
        return "both"

    # Build resource lookup table (all candidates; unused ones pruned at end)
    items_by_id = {v["id"]: v for v in items_by_var.values()}
    liquids_by_id = {v["id"]: v for v in liquids_by_var.values()}

    all_resources: dict[str, dict[str, Any]] = {}
    for it in items_by_var.values():
        rid = it["id"]
        name = rename_resources.get(rid, bundle.get(f"item.{it['raw_id']}.name", rid.replace("-", " ").title()))
        tags = []
        if it["var"] in serpulo_item_vars:
            tags.append("serpulo")
        if it["var"] in erekir_item_vars:
            tags.append("erekir")
        if it["hidden"]:
            tags.append("debug")
        all_resources[rid] = {"id": rid, "name": name, "kind": "item", "tags": sorted(tags)}

    for liq in liquids_by_var.values():
        rid = liq["id"]
        name = rename_resources.get(rid, bundle.get(f"liquid.{liq['raw_id']}.name", rid.replace("-", " ").title()))
        tags = []
        if liq["hidden"]:
            tags.append("debug")
        all_resources[rid] = {
            "id": rid,
            "name": name,
            "kind": "gas" if liq["gas"] else "liquid",
            "tags": sorted(tags),
        }

    for u in units_by_var.values():
        rid = u["id"]
        name = rename_resources.get(rid, bundle.get(f"unit.{u['raw_id']}.name", rid.replace("-", " ").title()))
        all_resources[rid] = {"id": rid, "name": name, "kind": "unit", "tags": ["unit"]}

    # Synthetic Heat and Power resources (D2: A + global power_mode)
    all_resources["heat"] = {"id": "heat", "name": "Heat", "kind": "heat", "tags": ["erekir"]}
    all_resources["power"] = {"id": "power", "name": "Power", "kind": "power", "tags": ["power"]}

    # 3. Classify and convert blocks
    IN_SCOPE_CLASSES = {
        "GenericCrafter", "AttributeCrafter", "HeatCrafter", "HeatProducer", "Separator",
        "Drill", "BurstDrill", "BeamDrill", "WallCrafter", "Pump", "SolidPump", "Fracker",
        "ConsumeGenerator", "ThermalGenerator", "SolarGenerator", "NuclearReactor",
        "ImpactReactor", "HeaterGenerator", "VariableReactor",
        "UnitFactory", "Reconstructor", "UnitAssembler", "Constructor",
    }

    machines: list[dict[str, Any]] = []
    recipes_by_shard: dict[str, list[dict[str, Any]]] = {
        "crafting": [],
        "extraction": [],
        "heat": [],
        "power": [],
        "units": [],
    }
    seen_machine_ids: set[str] = set()
    seen_recipe_ids: set[str] = set()
    id_collisions: list[dict[str, Any]] = []
    merged_ports_log: list[dict[str, Any]] = []
    skipped_blocks: Counter[str] = Counter()
    skipped_block_examples: dict[str, list[str]] = defaultdict(list)
    skipped_recipes: Counter[str] = Counter()
    skipped_recipe_examples: dict[str, list[str]] = defaultdict(list)

    def log_skip(reason: str, label: str) -> None:
        skipped_blocks[reason] += 1
        if len(skipped_block_examples[reason]) < 8:
            skipped_block_examples[reason].append(label)

    def log_skip_recipe(reason: str, label: str) -> None:
        skipped_recipes[reason] += 1
        if len(skipped_recipe_examples[reason]) < 8:
            skipped_recipe_examples[reason].append(label)

    def add_machine(m: dict[str, Any]) -> None:
        mid = m["id"]
        if mid in seen_machine_ids:
            id_collisions.append({"kind": "machine", "id": mid})
            raise RuntimeError(f"Duplicate machine id: {mid}")
        seen_machine_ids.add(mid)
        machines.append(m)

    def add_recipe(shard: str, r: dict[str, Any]) -> None:
        rid = r["id"]
        if rid in seen_recipe_ids:
            id_collisions.append({"kind": "recipe", "id": rid})
            raise RuntimeError(f"Duplicate recipe id: {rid}")
        seen_recipe_ids.add(rid)
        if r.get("in"):
            r["in"] = merge_duplicate_ports(r["in"], rid, "in", merged_ports_log)
        if r.get("out"):
            r["out"] = merge_duplicate_ports(r["out"], rid, "out", merged_ports_log)
        if not r.get("in") and not r.get("out"):
            raise RuntimeError(f"Guard failed: recipe {rid} has 0 ports (V-NUM-4)")
        recipes_by_shard[shard].append(r)

    # First pass to collect required wall payloads from UnitAssembler plans
    required_wall_payload_vars: set[str] = set()
    for var, cls, ctor, body in raw_block_decls:
        if cls == "UnitAssembler":
            for m in re.finditer(r"Blocks\.(\w+)", body):
                required_wall_payload_vars.add(m.group(1))

    # Add required wall payload resources
    for wvar in sorted(required_wall_payload_vars):
        wid = block_ids_by_var[wvar]
        name = rename_resources.get(wid, bundle.get(f"block.{wid}.name", wid.replace("-", " ").title()))
        all_resources[wid] = {"id": wid, "name": name, "kind": "payload", "tags": ["erekir", "payload"]}

    def parse_consumers(top: str, local_env: dict[str, float]) -> dict[str, Any]:
        """Extract all consume* calls in declaration order from a block body."""
        items_in: list[tuple[str, float]] = []
        liquids_in: list[tuple[str, float]] = []
        boost_item: tuple[str, float] | None = None
        boost_liquid: tuple[str, float] | None = None
        power_use = 0.0
        has_flam_filter = False
        has_radio_filter = False

        # Power
        for pm in re.finditer(r"consumePower\s*\(([^)]+)\)", top):
            power_use += eval_java_number(pm.group(1), local_env)

        # Single consumeItem(Items.x[, amt])[.boost()]
        for im in re.finditer(r"consumeItem\s*\(\s*Items\.(\w+)(?:\s*,\s*([^)]+))?\s*\)(\.boost\(\))?", top):
            iid = items_by_var[im.group(1)]["id"]
            amt = eval_java_number(im.group(2), local_env) if im.group(2) else 1.0
            if im.group(3):
                boost_item = (iid, amt)
            else:
                items_in.append((iid, amt))

        # Multi consumeItems(with(...))
        for im in re.finditer(r"consumeItems\s*\(\s*(with\s*\([\s\S]*?\))\s*\)", top):
            parsed = parse_item_stack_list(im.group(1), items_by_var)
            if not parsed:
                raise RuntimeError(f"Guard failed: consumeItems parsed to 0 ports: {im.group(0)}")
            items_in.extend(parsed)

        # Single consumeLiquid(Liquids.x, amt)[.boost()|.update(false)]
        for lm in re.finditer(r"consumeLiquid\s*\(\s*Liquids\.(\w+)\s*,\s*([^)]+)\)(\.boost\(\))?", top):
            lid = liquids_by_var[lm.group(1)]["id"]
            amt = eval_java_number(lm.group(2), local_env)
            if lm.group(3):
                boost_liquid = (lid, amt)
            else:
                liquids_in.append((lid, amt))

        # Multi consumeLiquids(LiquidStack.with(...))
        for lm in re.finditer(r"consumeLiquids\s*\(\s*(LiquidStack\.with\s*\([\s\S]*?\))\s*\)", top):
            parsed = parse_liquid_stack_list(lm.group(1), liquids_by_var)
            if not parsed:
                raise RuntimeError(f"Guard failed: consumeLiquids parsed to 0 ports: {lm.group(0)}")
            liquids_in.extend(parsed)

        if "ConsumeItemFlammable" in top:
            has_flam_filter = True
        if "ConsumeItemRadioactive" in top:
            has_radio_filter = True

        return {
            "items": items_in,
            "liquids": liquids_in,
            "boost_item": boost_item,
            "boost_liquid": boost_liquid,
            "power_per_tick": power_use,
            "flammable_filter": has_flam_filter,
            "radioactive_filter": has_radio_filter,
        }

    def parse_outputs(top: str, local_env: dict[str, float]) -> tuple[list[tuple[str, float]], list[tuple[str, float]]]:
        out_items: list[tuple[str, float]] = []
        out_liquids: list[tuple[str, float]] = []

        # outputItems = with(...) overrides outputItem if present
        m_ois = re.search(r"outputItems\s*=\s*(?:ItemStack\.)?(with\s*\([\s\S]*?\))\s*;", top)
        if m_ois:
            out_items.extend(parse_item_stack_list(m_ois.group(1), items_by_var))
        else:
            m_oi = re.search(r"outputItem\s*=\s*new\s+ItemStack\s*\(\s*Items\.(\w+)\s*,\s*([^)]+)\)", top)
            if m_oi:
                out_items.append((items_by_var[m_oi.group(1)]["id"], eval_java_number(m_oi.group(2), local_env)))

        m_ols = re.search(r"outputLiquids\s*=\s*(?:LiquidStack\.)?(with\s*\([\s\S]*?\))\s*;", top)
        if m_ols:
            out_liquids.extend(parse_liquid_stack_list(m_ols.group(1), liquids_by_var))
        else:
            m_ol = re.search(r"outputLiquid\s*=\s*new\s+LiquidStack\s*\(\s*Liquids\.(\w+)\s*,\s*([^)]+)\)", top)
            if m_ol:
                out_liquids.append((liquids_by_var[m_ol.group(1)]["id"], eval_java_number(m_ol.group(2), local_env)))

        return out_items, out_liquids

    # Collect shared-recipe machine groups in Blocks.java progression order
    floor_drills: list[dict[str, Any]] = []
    wall_drills: list[dict[str, Any]] = []
    wall_crafters_seen = False
    pumps_seen = False
    solars_seen = False

    # Main block conversion loop
    for var, cls, ctor, body in raw_block_decls:
        raw_id = first_string_arg(ctor)
        label = raw_id or var
        top = strip_nested_blocks(body)

        if cls not in IN_SCOPE_CLASSES:
            if cls in ("Incinerator", "ItemIncinerator"):
                log_skip("excluded_incinerator", label)
            elif cls == "UnitAssemblerModule":
                log_skip("folded_into_tier1_assembler_power", label)
            elif cls == "OverdriveProjector":
                log_skip("modeled_as_overdrive_param", label)
            elif "sandboxOnly" in top or cls.endswith(("Source", "Void")):
                log_skip("excluded_sandbox_block", label)
            else:
                log_skip(f"non_production_class:{cls}", label)
            continue

        if not raw_id:
            log_skip("missing_raw_id", label)
            continue

        bid = slugify(raw_id)
        if bid in excluded_blocks:
            log_skip("excluded_by_override", bid)
            continue

        if "BuildVisibility.sandboxOnly" in top or "BuildVisibility.editorOnly" in top:
            log_skip("excluded_sandbox_or_editor", bid)
            continue

        if cls == "Constructor" and bid != "constructor":
            # large-constructor (minBlockSize=3..4) has no UnitAssembler payload recipes
            log_skip("constructor_no_unit_chain_payloads", bid)
            continue

        is_debug = "BuildVisibility.debugOnly" in top
        planet = block_planet(var, is_debug)
        disp_name = rename_machines.get(bid, bundle.get(f"block.{raw_id}.name", bid.replace("-", " ").title()))

        size_e = find_field_expr(body, "size")
        size = int(round(eval_java_number(size_e))) if size_e else (3 if cls == "Constructor" else 1)

        # Build local numeric env for self-referential fields (e.g. thorium-reactor heating / coolantPower)
        local_env: dict[str, float] = {}
        for fld, default_val in [
            ("heating", 0.01 if cls == "NuclearReactor" else 0.0),
            ("coolantPower", 0.5 if cls == "NuclearReactor" else 1.0),
        ]:
            fe = find_field_expr(body, fld)
            local_env[fld] = eval_java_number(fe, local_env) if fe else default_val

        cons = parse_consumers(top, local_env)
        out_items, out_liquids = parse_outputs(top, local_env)

        # ---- 1. GenericCrafter ----
        if cls == "GenericCrafter":
            ct_e = find_field_expr(body, "craftTime")
            craft_time = eval_java_number(ct_e, local_env) if ct_e else 80.0
            # Pure liquid/gas crafters without discrete items use 60 ticks (1 s) for clean /s port amounts
            if not cons["items"] and not out_items:
                craft_time = 60.0
            in_ports = [make_short_port(iid, amt) for iid, amt in cons["items"]]
            for lid, rate_pt in cons["liquids"]:
                in_ports.append(make_short_port(lid, rate_pt * craft_time))
            out_ports = [make_short_port(iid, amt) for iid, amt in out_items]
            for lid, rate_pt in out_liquids:
                out_ports.append(make_short_port(lid, rate_pt * craft_time))

            add_machine({
                "id": bid,
                "name": disp_name,
                "profile": "mindustry_crafter",
                "categories": [bid],
                "speed": 1,
                "attrs": {
                    "size": size,
                    "power": clean_num(cons["power_per_tick"] * TICKS_PER_SECOND),
                    "planet": planet,
                    "is_debug": is_debug,
                },
            })
            add_recipe("crafting", {
                "id": bid,
                "name": disp_name,
                "category": bid,
                "time": clean_num(craft_time),
                "attrs": {"planet": planet, "is_debug": is_debug},
                "in": in_ports,
                "out": out_ports,
            })

        # ---- 2. AttributeCrafter (silicon-crucible, cultivator, vent-condenser) ----
        elif cls == "AttributeCrafter":
            ct_e = find_field_expr(body, "craftTime")
            craft_time = eval_java_number(ct_e, local_env) if ct_e else 80.0
            attr_m = re.search(r"attribute\s*=\s*Attribute\.(\w+)", top)
            attr_name = attr_m.group(1) if attr_m else "heat"
            output_scale_e = find_field_expr(body, "outputScale")
            output_scale = eval_java_number(output_scale_e, local_env) if output_scale_e else 0.0
            max_boost_e = find_field_expr(body, "maxBoost")
            max_boost = eval_java_number(max_boost_e, local_env) if max_boost_e else 1.0
            base_eff_e = find_field_expr(body, "baseEfficiency")
            base_eff = eval_java_number(base_eff_e, local_env) if base_eff_e else 1.0

            if attr_name == "steam":
                # vent-condenser: fixed 9 steam tiles -> 100% efficiency, continuous water output
                craft_time = 60.0
                out_ports = [make_short_port(lid, rate_pt * craft_time) for lid, rate_pt in out_liquids]
                add_machine({
                    "id": bid,
                    "name": disp_name,
                    "profile": "mindustry_crafter",
                    "categories": [bid],
                    "speed": 1,
                    "attrs": {
                        "size": size,
                        "power": clean_num(cons["power_per_tick"] * TICKS_PER_SECOND),
                        "planet": planet,
                        "is_debug": is_debug,
                    },
                })
                add_recipe("extraction", {
                    "id": bid,
                    "name": disp_name,
                    "category": bid,
                    "time": clean_num(craft_time),
                    "attrs": {"planet": planet, "is_debug": is_debug},
                    "out": out_ports,
                })
            else:
                # silicon-crucible (heat, scales_yield=true) & cultivator (spores, fixed-rate water)
                in_ports = [make_short_port(iid, amt) for iid, amt in cons["items"]]
                for lid, rate_pt in cons["liquids"]:
                    # scaleLiquidConsumption defaults to false in AttributeCrafter.java:23 -> fixed rate/s
                    in_ports.append(make_short_port(lid, rate_pt * TICKS_PER_SECOND, attrs={"fixed_rate": True}))
                out_ports = [make_short_port(iid, amt) for iid, amt in out_items]
                for lid, rate_pt in out_liquids:
                    out_ports.append(make_short_port(lid, rate_pt * craft_time))

                add_machine({
                    "id": bid,
                    "name": disp_name,
                    "profile": "mindustry_attribute_crafter",
                    "categories": [bid],
                    "speed": 1,
                    "attrs": {
                        "size": size,
                        "power": clean_num(cons["power_per_tick"] * TICKS_PER_SECOND),
                        "planet": planet,
                        "is_debug": is_debug,
                        "tile_attr": attr_name,
                        "min_tile_eff": clean_num(base_eff * 100.0),
                        "max_tile_eff": clean_num((base_eff + max_boost) * 100.0),
                        "scales_yield": output_scale > 0.0,
                    },
                })
                add_recipe("crafting", {
                    "id": bid,
                    "name": disp_name,
                    "category": bid,
                    "time": clean_num(craft_time),
                    "attrs": {"planet": planet, "is_debug": is_debug},
                    "in": in_ports,
                    "out": out_ports,
                })

        # ---- 3. HeatCrafter ----
        elif cls == "HeatCrafter":
            ct_e = find_field_expr(body, "craftTime")
            craft_time = eval_java_number(ct_e, local_env) if ct_e else 80.0
            if not cons["items"] and not out_items:
                craft_time = 60.0
            hreq_e = find_field_expr(body, "heatRequirement")
            heat_req = eval_java_number(hreq_e, local_env) if hreq_e else 10.0
            meff_e = find_field_expr(body, "maxEfficiency")
            max_eff = eval_java_number(meff_e, local_env) if meff_e else 4.0

            in_ports = [make_short_port(iid, amt) for iid, amt in cons["items"]]
            for lid, rate_pt in cons["liquids"]:
                in_ports.append(make_short_port(lid, rate_pt * craft_time))
            out_ports = [make_short_port(iid, amt) for iid, amt in out_items]
            for lid, rate_pt in out_liquids:
                out_ports.append(make_short_port(lid, rate_pt * craft_time))

            add_machine({
                "id": bid,
                "name": disp_name,
                "profile": "mindustry_heat_crafter",
                "categories": [bid],
                "speed": 1,
                "attrs": {
                    "size": size,
                    "power": clean_num(cons["power_per_tick"] * TICKS_PER_SECOND),
                    "planet": planet,
                    "is_debug": is_debug,
                    "heat_req": clean_num(heat_req),
                    "max_heat_eff": clean_num(max_eff),
                },
            })
            rec: dict[str, Any] = {
                "id": bid,
                "name": disp_name,
                "category": bid,
                "time": clean_num(craft_time),
                "attrs": {"planet": planet, "is_debug": is_debug},
                "out": out_ports,
            }
            if in_ports:
                rec["in"] = in_ports
            add_recipe("crafting", rec)

        # ---- 4. HeatProducer ----
        elif cls == "HeatProducer":
            ct_e = find_field_expr(body, "craftTime")
            craft_time = eval_java_number(ct_e, local_env) if ct_e else 80.0
            if not cons["items"] and not out_items:
                craft_time = 60.0
            hout_e = find_field_expr(body, "heatOutput")
            heat_out = eval_java_number(hout_e, local_env) if hout_e else 10.0

            in_ports = [make_short_port(iid, amt) for iid, amt in cons["items"]]
            for lid, rate_pt in cons["liquids"]:
                in_ports.append(make_short_port(lid, rate_pt * craft_time))
            out_ports = [make_short_port(iid, amt) for iid, amt in out_items]
            for lid, rate_pt in out_liquids:
                out_ports.append(make_short_port(lid, rate_pt * craft_time))
            # Heat output per craft = heatOutput (Heat/s) * (craftTime / 60 s)
            out_ports.append(make_short_port("heat", heat_out * craft_time / TICKS_PER_SECOND))

            add_machine({
                "id": bid,
                "name": disp_name,
                "profile": "mindustry_crafter",
                "categories": [bid],
                "speed": 1,
                "attrs": {
                    "size": size,
                    "power": clean_num(cons["power_per_tick"] * TICKS_PER_SECOND),
                    "can_overdrive": False,
                    "planet": planet,
                    "is_debug": is_debug,
                },
            })
            rec = {
                "id": bid,
                "name": disp_name,
                "category": bid,
                "time": clean_num(craft_time),
                "attrs": {"planet": planet, "is_debug": is_debug},
                "out": out_ports,
            }
            if in_ports:
                rec["in"] = in_ports
            add_recipe("heat", rec)

        # ---- 5. Separator ----
        elif cls == "Separator":
            ct_e = find_field_expr(body, "craftTime")
            craft_time = eval_java_number(ct_e, local_env) if ct_e else 35.0
            rm = re.search(r"results\s*=\s*(with\s*\([\s\S]*?\))\s*;", top)
            if not rm:
                raise RuntimeError(f"Separator {bid} missing results")
            weights = parse_item_stack_list(rm.group(1), items_by_var)
            total_w = sum(w for _, w in weights)
            in_ports = [make_short_port(iid, amt) for iid, amt in cons["items"]]
            for lid, rate_pt in cons["liquids"]:
                in_ports.append(make_short_port(lid, rate_pt * craft_time))
            out_ports = [make_short_port(iid, 1.0, chance=w / total_w) for iid, w in weights]

            add_machine({
                "id": bid,
                "name": disp_name,
                "profile": "mindustry_crafter",
                "categories": [bid],
                "speed": 1,
                "attrs": {
                    "size": size,
                    "power": clean_num(cons["power_per_tick"] * TICKS_PER_SECOND),
                    "planet": planet,
                    "is_debug": is_debug,
                },
            })
            add_recipe("crafting", {
                "id": bid,
                "name": disp_name,
                "category": bid,
                "time": clean_num(craft_time),
                "attrs": {"planet": planet, "is_debug": is_debug},
                "in": in_ports,
                "out": out_ports,
            })

        # ---- 6. Drill, BurstDrill, BeamDrill (unified into mine-<ore> / bore-<ore>) ----
        elif cls in ("Drill", "BurstDrill", "BeamDrill"):
            dt_e = find_field_expr(body, "drillTime")
            drill_time = eval_java_number(dt_e, local_env) if dt_e else (200.0 if cls == "BeamDrill" else 300.0)
            tier_e = find_field_expr(body, "tier")
            tier = int(round(eval_java_number(tier_e, local_env))) if tier_e else 1

            # Blocked items
            blocked_vars: set[str] = set()
            bm = re.search(r"blockedItem\s*=\s*Items\.(\w+)", top)
            if bm:
                blocked_vars.add(bm.group(1))
            bms = re.search(r"blockedItems\s*=\s*Seq\.with\(([^)]+)\)", top)
            if bms:
                for iv in re.findall(r"Items\.(\w+)", bms.group(1)):
                    blocked_vars.add(iv)

            # Drill multipliers per item (guard: v160.8 only uses Items.beryllium)
            drill_mults: dict[str, float] = {}
            for dm in re.finditer(r"drillMultipliers\.put\(\s*Items\.(\w+)\s*,\s*([^)]+)\)", top):
                drill_mults[dm.group(1)] = eval_java_number(dm.group(2), local_env)
            unexpected_mults = set(drill_mults) - {"beryllium"}
            if unexpected_mults:
                raise RuntimeError(f"Drill {bid} has unhandled drillMultipliers: {unexpected_mults}")
            beryllium_mult = drill_mults.get("beryllium", 1.0)

            if len(cons["liquids"]) > 1:
                raise RuntimeError(f"Drill {bid} has >1 mandatory liquid: {cons['liquids']}")
            req_res, req_rate = ("", 0.0)
            if cons["liquids"]:
                req_res, req_pt = cons["liquids"][0]
                req_rate = req_pt * TICKS_PER_SECOND

            # Boost intensity & resource
            if cls == "Drill":
                lbi_e = find_field_expr(body, "liquidBoostIntensity")
                lbi = eval_java_number(lbi_e, local_env) if lbi_e else 1.6
                boost_mult = lbi * lbi  # Drill.java:188,301-305: speed * warmup -> liquidBoostIntensity^2
                max_tiles = size * size
                hardness_mult = HARDNESS_DRILL_MULT
            elif cls == "BurstDrill":
                lbi_e = find_field_expr(body, "liquidBoostIntensity")
                boost_mult = eval_java_number(lbi_e, local_env) if lbi_e else 1.6  # BurstDrill.java:65,94-99: linear
                max_tiles = size * size
                hardness_mult = 0.0
            else:  # BeamDrill
                obi_e = find_field_expr(body, "optionalBoostIntensity")
                boost_mult = eval_java_number(obi_e, local_env) if obi_e else 2.5  # BeamDrill.java:44,246: linear
                max_tiles = size
                hardness_mult = 0.0

            boost_res = ""
            boost_rate = 0.0
            if cons["boost_liquid"]:
                boost_res, boost_pt = cons["boost_liquid"]
                boost_rate = boost_pt * TICKS_PER_SECOND

            add_machine({
                "id": bid,
                "name": disp_name,
                "profile": "mindustry_drill",
                "categories": [],
                "speed": 1,
                "attrs": {
                    "size": size,
                    "power": clean_num(cons["power_per_tick"] * TICKS_PER_SECOND),
                    "planet": planet,
                    "is_debug": is_debug,
                    "max_tiles": max_tiles,
                    "drill_time": clean_num(drill_time),
                    "hardness_mult": clean_num(hardness_mult),
                    "beryllium_mult": clean_num(beryllium_mult),
                    "req_res": req_res,
                    "req_rate": clean_num(req_rate),
                    "boost_mult": clean_num(boost_mult),
                    "boost_res": boost_res,
                    "boost_rate": clean_num(boost_rate),
                },
            })

            drill_meta = {"id": bid, "tier": tier, "blocked": blocked_vars}
            if cls == "BeamDrill":
                wall_drills.append(drill_meta)
            else:
                floor_drills.append(drill_meta)

        # ---- 7. WallCrafter (cliff-crusher, large-cliff-crusher -> unified crush-sand) ----
        elif cls == "WallCrafter":
            dt_e = find_field_expr(body, "drillTime")
            drill_time = eval_java_number(dt_e, local_env) if dt_e else 150.0
            attr_m = re.search(r"attribute\s*=\s*Attribute\.(\w+)", top)
            attr_name = attr_m.group(1) if attr_m else "sand"

            if len(cons["liquids"]) > 1:
                raise RuntimeError(f"WallCrafter {bid} has >1 mandatory liquid: {cons['liquids']}")
            req_res, req_rate = ("", 0.0)
            if cons["liquids"]:
                req_res, req_pt = cons["liquids"][0]
                req_rate = req_pt * TICKS_PER_SECOND

            boost_res = ""
            boost_rate = 0.0
            boost_mult = 1.0
            if cons["boost_item"]:
                b_iid, b_amt = cons["boost_item"]
                but_e = find_field_expr(body, "boostItemUseTime")
                but = eval_java_number(but_e, local_env) if but_e else 120.0
                ibi_e = find_field_expr(body, "itemBoostIntensity")
                boost_mult = eval_java_number(ibi_e, local_env) if ibi_e else 1.6
                boost_res = b_iid
                boost_rate = b_amt * TICKS_PER_SECOND / but

            add_machine({
                "id": bid,
                "name": disp_name,
                "profile": "mindustry_wall_crafter",
                "categories": ["wall-crafter"],
                "speed": 1,
                "attrs": {
                    "size": size,
                    "power": clean_num(cons["power_per_tick"] * TICKS_PER_SECOND),
                    "planet": planet,
                    "is_debug": is_debug,
                    "drill_time": clean_num(drill_time),
                    "tile_attr": attr_name,
                    "min_tile_eff": 1,
                    "max_tile_eff": 200,
                    "req_res": req_res,
                    "req_rate": clean_num(req_rate),
                    "boost_mult": clean_num(boost_mult),
                    "boost_res": boost_res,
                    "boost_rate": clean_num(boost_rate),
                },
            })
            wall_crafters_seen = True

        # ---- 8. Pump (unified into pump-<liquid>) ----
        elif cls == "Pump":
            pa_e = find_field_expr(body, "pumpAmount")
            pump_amount = eval_java_number(pa_e, local_env) if pa_e else 0.2
            if len(cons["liquids"]) > 1:
                raise RuntimeError(f"Pump {bid} has >1 mandatory liquid: {cons['liquids']}")
            req_res, req_rate = ("", 0.0)
            if cons["liquids"]:
                req_res, req_pt = cons["liquids"][0]
                req_rate = req_pt * TICKS_PER_SECOND

            add_machine({
                "id": bid,
                "name": disp_name,
                "profile": "mindustry_pump",
                "categories": ["pump"],
                "speed": 1,
                "attrs": {
                    "size": size,
                    "power": clean_num(cons["power_per_tick"] * TICKS_PER_SECOND),
                    "planet": planet,
                    "is_debug": is_debug,
                    "max_tiles": size * size,
                    "pump_rate": clean_num(pump_amount * TICKS_PER_SECOND),
                    "req_res": req_res,
                    "req_rate": clean_num(req_rate),
                },
            })
            pumps_seen = True

        # ---- 9. SolidPump (water-extractor) & Fracker (oil-extractor) ----
        elif cls in ("SolidPump", "Fracker"):
            pa_e = find_field_expr(body, "pumpAmount")
            pump_amount = eval_java_number(pa_e, local_env) if pa_e else 0.2
            res_m = re.search(r"result\s*=\s*Liquids\.(\w+)", top)
            out_lid = liquids_by_var[res_m.group(1)]["id"] if res_m else "water"
            attr_m = re.search(r"attribute\s*=\s*Attribute\.(\w+)", top)
            attr_name = attr_m.group(1) if attr_m else "water"

            if cls == "Fracker":
                iut_e = find_field_expr(body, "itemUseTime")
                cycle_ticks = eval_java_number(iut_e, local_env) if iut_e else 100.0
            else:
                cycle_ticks = 60.0

            in_ports = [make_short_port(iid, amt) for iid, amt in cons["items"]]
            for lid, rate_pt in cons["liquids"]:
                in_ports.append(make_short_port(lid, rate_pt * cycle_ticks))
            out_ports = [make_short_port(out_lid, pump_amount * cycle_ticks)]

            add_machine({
                "id": bid,
                "name": disp_name,
                "profile": "mindustry_solid_pump",
                "categories": [bid],
                "speed": 1,
                "attrs": {
                    "size": size,
                    "power": clean_num(cons["power_per_tick"] * TICKS_PER_SECOND),
                    "planet": planet,
                    "is_debug": is_debug,
                    "tile_attr": attr_name,
                    "min_tile_eff": 1,
                    "max_tile_eff": 200,
                },
            })
            rec = {
                "id": bid,
                "name": disp_name,
                "category": bid,
                "time": clean_num(cycle_ticks),
                "attrs": {"planet": planet, "is_debug": is_debug},
                "out": out_ports,
            }
            if in_ports:
                rec["in"] = in_ports
            add_recipe("extraction", rec)

        # ---- 10. ConsumeGenerator & HeaterGenerator ----
        elif cls in ("ConsumeGenerator", "HeaterGenerator"):
            pp_e = find_field_expr(body, "powerProduction")
            power_prod = eval_java_number(pp_e, local_env) if pp_e else 0.0
            id_e = find_field_expr(body, "itemDuration")
            item_dur = eval_java_number(id_e, local_env) if id_e else 120.0
            is_heater_gen = cls == "HeaterGenerator"
            hout_e = find_field_expr(body, "heatOutput")
            heat_out = (eval_java_number(hout_e, local_env) if hout_e else 10.0) if is_heater_gen else 0.0

            dur_mults: dict[str, float] = {}
            for dm in re.finditer(r"itemDurationMultipliers\.put\(\s*Items\.(\w+)\s*,\s*([^)]+)\)", top):
                dur_mults[dm.group(1)] = eval_java_number(dm.group(2), local_env)

            add_machine({
                "id": bid,
                "name": disp_name,
                "profile": "mindustry_crafter",
                "categories": [bid],
                "speed": 1,
                "attrs": {
                    "size": size,
                    "power": clean_num((cons["power_per_tick"] - power_prod) * TICKS_PER_SECOND),
                    "can_overdrive": not is_heater_gen,
                    "planet": planet,
                    "is_debug": is_debug,
                },
            })

            if cons["flammable_filter"] or cons["radioactive_filter"]:
                has_explode = "ConsumeItemExplode" in top
                for ivar, it in sorted(items_by_var.items(), key=lambda kv: kv[1]["id"]):
                    if cons["flammable_filter"]:
                        if it["flammability"] < 0.2 or it["hidden"]:
                            continue
                        if has_explode and it["explosiveness"] >= 0.5:
                            # Excluded per D5: ConsumeItemExplode damages/destroys generator
                            log_skip_recipe("excluded_explosive_fuel", f"{bid}:{it['id']}")
                            continue
                        pmult = it["flammability"]
                    else:
                        if it["radioactivity"] < 0.2:
                            continue
                        pmult = it["radioactivity"]

                    r_is_debug = is_debug or it["hidden"]
                    r_planet = "both" if r_is_debug else planet
                    eff_dur = item_dur * dur_mults.get(ivar, 1.0)
                    in_ports = [make_short_port(it["id"], 1.0)]
                    for lid, rate_pt in cons["liquids"]:
                        in_ports.append(make_short_port(lid, rate_pt * eff_dur))
                    out_ports = [make_short_port(lid, rate_pt * eff_dur) for lid, rate_pt in out_liquids]
                    fuel_name = all_resources[it["id"]]["name"]
                    rec = {
                        "id": f"{bid}-{it['id']}",
                        "name": f"{disp_name}: {fuel_name}",
                        "category": bid,
                        "time": clean_num(eff_dur),
                        "attrs": {
                            "planet": r_planet,
                            "is_debug": r_is_debug,
                            "power_mult": clean_num(pmult),
                        },
                        "in": in_ports,
                    }
                    if out_ports:
                        rec["out"] = out_ports
                    add_recipe("power", rec)
            else:
                cycle = item_dur if cons["items"] else 60.0
                in_ports = [make_short_port(iid, amt) for iid, amt in cons["items"]]
                for lid, rate_pt in cons["liquids"]:
                    in_ports.append(make_short_port(lid, rate_pt * cycle))
                out_ports = [make_short_port(lid, rate_pt * cycle) for lid, rate_pt in out_liquids]
                if is_heater_gen and heat_out > 0:
                    out_ports.append(make_short_port("heat", heat_out * cycle / TICKS_PER_SECOND))
                rec = {
                    "id": bid,
                    "name": disp_name,
                    "category": bid,
                    "time": clean_num(cycle),
                    "attrs": {"planet": planet, "is_debug": is_debug},
                    "in": in_ports,
                }
                if out_ports:
                    rec["out"] = out_ports
                add_recipe("power", rec)

        # ---- 11. ThermalGenerator (thermal-generator & turbine-condenser) ----
        elif cls == "ThermalGenerator":
            pp_e = find_field_expr(body, "powerProduction")
            power_prod = eval_java_number(pp_e, local_env) if pp_e else 0.0
            attr_m = re.search(r"attribute\s*=\s*Attribute\.(\w+)", top)
            attr_name = attr_m.group(1) if attr_m else "heat"

            if attr_name == "steam":
                # turbine-condenser: fixed 9 steam tiles -> 9 * powerProduction * 60 u/s and 9 * outputLiquid * 60 /s
                tile_count = size * size
                out_ports = [make_short_port(lid, rate_pt * tile_count * TICKS_PER_SECOND) for lid, rate_pt in out_liquids]
                add_machine({
                    "id": bid,
                    "name": disp_name,
                    "profile": "mindustry_crafter",
                    "categories": [bid],
                    "speed": 1,
                    "attrs": {
                        "size": size,
                        "power": clean_num(-power_prod * tile_count * TICKS_PER_SECOND),
                        "planet": planet,
                        "is_debug": is_debug,
                    },
                })
                add_recipe("power", {
                    "id": bid,
                    "name": disp_name,
                    "category": bid,
                    "time": 60,
                    "attrs": {"planet": planet, "is_debug": is_debug},
                    "out": out_ports,
                })
            else:
                # thermal-generator: 0-port generator using tile_preset (thermal: 200% hotrock, 300% magmarock, 340% slag)
                add_machine({
                    "id": bid,
                    "name": disp_name,
                    "profile": "mindustry_thermal",
                    "categories": [bid],
                    "speed": 1,
                    "attrs": {
                        "size": size,
                        "power": clean_num(-power_prod * TICKS_PER_SECOND),
                        "planet": planet,
                        "is_debug": is_debug,
                        "tile_attr": "thermal",
                        "min_tile_eff": 1,
                        "max_tile_eff": 340,
                    },
                })
                add_recipe("power", {
                    "id": bid,
                    "name": disp_name,
                    "category": bid,
                    "time": 60,
                    "attrs": {"planet": planet, "is_debug": is_debug},
                    "out": [make_short_port("power", 1.0)],
                })

        # ---- 12. SolarGenerator (unified into solar-power) ----
        elif cls == "SolarGenerator":
            pp_e = find_field_expr(body, "powerProduction")
            power_prod = eval_java_number(pp_e, local_env) if pp_e else 0.0
            add_machine({
                "id": bid,
                "name": disp_name,
                "profile": "mindustry_solar",
                "categories": ["solar"],
                "speed": 1,
                "attrs": {
                    "size": size,
                    "power": clean_num(-power_prod * TICKS_PER_SECOND),
                    "planet": planet,
                    "is_debug": is_debug,
                },
            })
            solars_seen = True

        # ---- 13. NuclearReactor (thorium-reactor) & ImpactReactor ----
        elif cls in ("NuclearReactor", "ImpactReactor"):
            pp_e = find_field_expr(body, "powerProduction")
            power_prod = eval_java_number(pp_e, local_env) if pp_e else 0.0
            id_e = find_field_expr(body, "itemDuration")
            item_dur = eval_java_number(id_e, local_env) if id_e else (120.0 if cls == "NuclearReactor" else 60.0)
            # Net power: ImpactReactor consumes 25/tick and produces 130/tick -> net -105/tick = -6300 u/s
            net_power = (cons["power_per_tick"] - power_prod) * TICKS_PER_SECOND
            in_ports = [make_short_port(iid, amt) for iid, amt in cons["items"]]
            for lid, rate_pt in cons["liquids"]:
                in_ports.append(make_short_port(lid, rate_pt * item_dur))

            add_machine({
                "id": bid,
                "name": disp_name,
                "profile": "mindustry_crafter",
                "categories": [bid],
                "speed": 1,
                "attrs": {
                    "size": size,
                    "power": clean_num(net_power),
                    "planet": planet,
                    "is_debug": is_debug,
                },
            })
            add_recipe("power", {
                "id": bid,
                "name": disp_name,
                "category": bid,
                "time": clean_num(item_dur),
                "attrs": {"planet": planet, "is_debug": is_debug},
                "in": in_ports,
            })

        # ---- 14. VariableReactor (flux-reactor) ----
        elif cls == "VariableReactor":
            pp_e = find_field_expr(body, "powerProduction")
            power_prod = eval_java_number(pp_e, local_env) if pp_e else 20.0
            mh_e = find_field_expr(body, "maxHeat")
            max_heat = eval_java_number(mh_e, local_env) if mh_e else 100.0
            in_ports = [make_short_port(lid, rate_pt * TICKS_PER_SECOND) for lid, rate_pt in cons["liquids"]]

            add_machine({
                "id": bid,
                "name": disp_name,
                "profile": "mindustry_flux_reactor",
                "categories": [bid],
                "speed": 1,
                "attrs": {
                    "size": size,
                    "power": clean_num((cons["power_per_tick"] - power_prod) * TICKS_PER_SECOND),
                    "planet": planet,
                    "is_debug": is_debug,
                    "heat_req": clean_num(max_heat),
                    "max_heat_eff": 1,
                },
            })
            add_recipe("power", {
                "id": bid,
                "name": disp_name,
                "category": bid,
                "time": 60,
                "attrs": {"planet": planet, "is_debug": is_debug},
                "in": in_ports,
            })

        # ---- 15. UnitFactory ----
        elif cls == "UnitFactory":
            add_machine({
                "id": bid,
                "name": disp_name,
                "profile": "mindustry_unit",
                "categories": [bid],
                "speed": 1,
                "attrs": {
                    "size": size,
                    "power": clean_num(cons["power_per_tick"] * TICKS_PER_SECOND),
                    "planet": planet,
                    "is_debug": is_debug,
                },
            })
            plans_found = 0
            for pm in re.finditer(r"new\s+UnitPlan\s*\(\s*UnitTypes\.(\w+)\s*,\s*([^,]+)\s*,\s*(with\s*\([\s\S]*?\))\s*\)", top):
                plans_found += 1
                uvar = pm.group(1)
                uid = units_by_var[uvar]["id"]
                ptime = eval_java_number(pm.group(2), local_env)
                reqs = parse_item_stack_list(pm.group(3), items_by_var)
                in_ports = [make_short_port(iid, amt) for iid, amt in reqs]
                for lid, rate_pt in cons["liquids"]:
                    in_ports.append(make_short_port(lid, rate_pt * TICKS_PER_SECOND, attrs={"fixed_rate": True}))
                uname = all_resources[uid]["name"]
                add_recipe("units", {
                    "id": f"{bid}-{uid}",
                    "name": f"{disp_name}: {uname}",
                    "category": bid,
                    "time": clean_num(ptime),
                    "attrs": {"planet": planet, "is_debug": is_debug},
                    "in": in_ports,
                    "out": [make_short_port(uid, 1.0)],
                })
            if plans_found == 0:
                raise RuntimeError(f"UnitFactory {bid} parsed 0 UnitPlans")

        # ---- 16. Reconstructor ----
        elif cls == "Reconstructor":
            ct_e = find_field_expr(body, "constructTime")
            construct_time = eval_java_number(ct_e, local_env) if ct_e else 120.0
            add_machine({
                "id": bid,
                "name": disp_name,
                "profile": "mindustry_unit",
                "categories": [bid],
                "speed": 1,
                "attrs": {
                    "size": size,
                    "power": clean_num(cons["power_per_tick"] * TICKS_PER_SECOND),
                    "planet": planet,
                    "is_debug": is_debug,
                },
            })
            upgrades_found = 0
            for um in re.finditer(r"new\s+UnitType\s*\[\]\s*\{\s*UnitTypes\.(\w+)\s*,\s*UnitTypes\.(\w+)\s*\}", body):
                upgrades_found += 1
                u_from = units_by_var[um.group(1)]["id"]
                u_to = units_by_var[um.group(2)]["id"]
                in_ports: list[Any] = [make_short_port(u_from, 1.0, attrs={"no_cost_scale": True})]
                for iid, amt in cons["items"]:
                    in_ports.append(make_short_port(iid, amt))
                for lid, rate_pt in cons["liquids"]:
                    in_ports.append(make_short_port(lid, rate_pt * TICKS_PER_SECOND, attrs={"fixed_rate": True}))
                to_name = all_resources[u_to]["name"]
                add_recipe("units", {
                    "id": f"{bid}-{u_to}",
                    "name": f"{disp_name}: {to_name}",
                    "category": bid,
                    "time": clean_num(construct_time),
                    "attrs": {"planet": planet, "is_debug": is_debug},
                    "in": in_ports,
                    "out": [make_short_port(u_to, 1.0)],
                })
            if upgrades_found == 0:
                raise RuntimeError(f"Reconstructor {bid} parsed 0 upgrades")

        # ---- 17. UnitAssembler ----
        elif cls == "UnitAssembler":
            add_machine({
                "id": bid,
                "name": disp_name,
                "profile": "mindustry_unit",
                "categories": [bid],
                "speed": 1,
                "attrs": {
                    "size": size,
                    "power": clean_num(cons["power_per_tick"] * TICKS_PER_SECOND),
                    "planet": planet,
                    "is_debug": is_debug,
                },
            })
            plans_found = 0
            for tier_idx, pm in enumerate(
                re.finditer(
                    r"new\s+AssemblerUnitPlan\s*\(\s*UnitTypes\.(\w+)\s*,\s*([^,]+)\s*,\s*(PayloadStack\.list\s*\([\s\S]*?\))\s*\)",
                    top,
                )
            ):
                plans_found += 1
                uid = units_by_var[pm.group(1)]["id"]
                ptime = eval_java_number(pm.group(2), local_env)
                payloads = parse_payload_stack_list(pm.group(3), units_by_var, block_ids_by_var)
                in_ports = [make_short_port(pid, amt) for pid, amt in payloads]
                for lid, rate_pt in cons["liquids"]:
                    in_ports.append(make_short_port(lid, rate_pt * TICKS_PER_SECOND, attrs={"fixed_rate": True}))
                extra_power = ASSEMBLER_MODULE_POWER if tier_idx >= 1 else 0.0
                uname = all_resources[uid]["name"]
                rec_attrs: dict[str, Any] = {"planet": planet, "is_debug": is_debug}
                if extra_power > 0:
                    rec_attrs["extra_power"] = clean_num(extra_power)
                add_recipe("units", {
                    "id": f"{bid}-{uid}",
                    "name": f"{disp_name}: {uname}",
                    "category": bid,
                    "time": clean_num(ptime),
                    "attrs": rec_attrs,
                    "in": in_ports,
                    "out": [make_short_port(uid, 1.0)],
                })
            if plans_found == 0:
                raise RuntimeError(f"UnitAssembler {bid} parsed 0 AssemblerUnitPlans")

        # ---- 18. Constructor (required large wall payloads for UnitAssembler) ----
        elif cls == "Constructor":
            bs_e = find_field_expr(body, "buildSpeed")
            build_speed = eval_java_number(bs_e, local_env) if bs_e else 0.4
            add_machine({
                "id": bid,
                "name": disp_name,
                "profile": "mindustry_crafter",
                "categories": [bid],
                "speed": clean_num(build_speed),
                "attrs": {
                    "size": size,
                    "power": clean_num(cons["power_per_tick"] * TICKS_PER_SECOND),
                    "planet": planet,
                    "is_debug": is_debug,
                },
            })
            for wvar in sorted(required_wall_payload_vars):
                wid = block_ids_by_var[wvar]
                reqs = wall_reqs_by_var[wvar]
                bmult = wall_build_mult_by_var.get(wvar, 1.0)
                # Block.java:1453-1464: buildTime = sum(stack.amount * stack.item.cost) * buildCostMultiplier
                build_time = sum(amt * items_by_id[iid]["cost"] for iid, amt in reqs) * bmult
                wname = all_resources[wid]["name"]
                add_recipe("units", {
                    "id": f"{bid}-{wid}",
                    "name": f"{disp_name}: {wname}",
                    "category": bid,
                    "time": clean_num(build_time),
                    "attrs": {"planet": planet, "is_debug": is_debug},
                    "in": [make_short_port(iid, amt) for iid, amt in reqs],
                    "out": [make_short_port(wid, 1.0)],
                })

    # 3b. Emit unified multi-machine extraction & solar recipes
    for ivar in sorted(floor_ore_vars, key=lambda v: items_by_var[v]["id"]):
        it = items_by_var[ivar]
        if it["hidden"]:
            continue
        compat = [d["id"] for d in floor_drills if ivar not in d["blocked"] and it["hardness"] <= d["tier"]]
        if not compat:
            raise RuntimeError(f"Floor ore {it['id']} has 0 compatible drills")
        ore_name = all_resources[it["id"]]["name"]
        rec_attrs: dict[str, Any] = {
            "planet": item_planet(ivar),
            "is_debug": False,
            "hardness": it["hardness"],
        }
        if it["id"] == "beryllium":
            rec_attrs["is_beryllium"] = True
        add_recipe("extraction", {
            "id": f"mine-{it['id']}",
            "name": f"Mine {ore_name}",
            "machines": compat,
            "time": 60,
            "attrs": rec_attrs,
            "out": [make_short_port(it["id"], 1.0)],
        })

    for ivar in sorted(wall_ore_vars, key=lambda v: items_by_var[v]["id"]):
        it = items_by_var[ivar]
        if it["hidden"]:
            continue
        compat = [d["id"] for d in wall_drills if ivar not in d["blocked"] and it["hardness"] <= d["tier"]]
        if not compat:
            raise RuntimeError(f"Wall ore {it['id']} has 0 compatible beam drills")
        ore_name = all_resources[it["id"]]["name"]
        add_recipe("extraction", {
            "id": f"bore-{it['id']}",
            "name": f"Mine {ore_name} (Wall)",
            "machines": compat,
            "time": 60,
            "attrs": {
                "planet": "erekir",
                "is_debug": False,
                "hardness": it["hardness"],
            },
            "out": [make_short_port(it["id"], 1.0)],
        })

    if wall_crafters_seen:
        add_recipe("extraction", {
            "id": "crush-sand",
            "name": "Crush Sand (Wall)",
            "category": "wall-crafter",
            "time": 60,
            "attrs": {"planet": "erekir", "is_debug": False},
            "out": [make_short_port("sand", 1.0)],
        })

    if pumps_seen:
        for lid in sorted(liquid_floor_mults):
            mults = liquid_floor_mults[lid]
            liq_name = all_resources[lid]["name"]
            add_recipe("extraction", {
                "id": f"pump-{lid}",
                "name": f"Pump {liq_name}",
                "category": "pump",
                "time": 60,
                "attrs": {
                    "planet": liquid_planet(lid),
                    "is_debug": False,
                    "min_liquid_mult": clean_num(min(mults)),
                    "max_liquid_mult": clean_num(max(mults)),
                },
                "out": [make_short_port(lid, 1.0)],
            })

    if solars_seen:
        add_recipe("power", {
            "id": "solar-power",
            "name": "Solar Power",
            "category": "solar",
            "time": 60,
            "attrs": {"planet": "serpulo", "is_debug": False},
            "out": [make_short_port("power", 1.0)],
        })

    # 4. Collect all referenced resources and prune unused ones (V-W-2)
    referenced_resources: set[str] = set()
    for shard_recs in recipes_by_shard.values():
        for r in shard_recs:
            for p in r.get("in", []) + r.get("out", []):
                referenced_resources.add(p[0] if isinstance(p, list) else p["res"])
    for m in machines:
        for key in ("boost_res", "req_res"):
            r_id = m.get("attrs", {}).get(key, "")
            if r_id:
                referenced_resources.add(r_id)
    # extra_ports fixed resources "heat" and "power" used by profiles
    referenced_resources.add("heat")
    referenced_resources.add("power")

    emitted_resources: list[dict[str, Any]] = []
    pruned_resources: dict[str, list[str]] = defaultdict(list)
    for rid in sorted(all_resources):
        if rid in referenced_resources:
            res = dict(all_resources[rid])
            if not res.get("tags"):
                res.pop("tags", None)
            emitted_resources.append(res)
        else:
            pruned_resources[all_resources[rid]["kind"]].append(rid)

    # Sort deterministically
    machines.sort(key=lambda m: m["id"])
    for shard in recipes_by_shard:
        recipes_by_shard[shard].sort(key=lambda r: r["id"])

    # 5. Scoped writes: clean ONLY JSON files inside packs/mindustry/160.8/ (never touch icons.pak!)
    OUT_PKG.mkdir(parents=True, exist_ok=True)
    recipes_dir = OUT_PKG / "recipes"
    recipes_dir.mkdir(parents=True, exist_ok=True)

    for old_json in list(OUT_PKG.glob("*.json")) + list(recipes_dir.glob("*.json")):
        old_json.unlink()

    def write_json(path: Path, data: Any) -> None:
        text = json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        path.write_text(text, encoding="utf-8")

    manifest = dict(template)
    manifest["include"] = ["resources.json", "machines.json", "waivers.json", "recipes"]
    write_json(OUT_PKG / "game.json", manifest)
    write_json(OUT_PKG / "resources.json", {"resources": emitted_resources})
    write_json(OUT_PKG / "machines.json", {"machines": machines})
    write_json(OUT_PKG / "waivers.json", waivers)

    for shard_name in sorted(recipes_by_shard):
        write_json(recipes_dir / f"{shard_name}.json", {"recipes": recipes_by_shard[shard_name]})

    # 6. Write reconciliation report
    total_recipes = sum(len(v) for v in recipes_by_shard.values())
    report = {
        "game": "mindustry",
        "version": "160.8",
        "raw_counts": {
            "items": len(items_by_var),
            "liquids": len(liquids_by_var),
            "units": len(units_by_var),
            "blocks_top_level": len(raw_block_decls),
        },
        "emitted_counts": {
            "resources": len(emitted_resources),
            "resources_by_kind": dict(sorted(Counter(r["kind"] for r in emitted_resources).items())),
            "machines": len(machines),
            "recipes": total_recipes,
            "recipes_by_shard": {k: len(recipes_by_shard[k]) for k in sorted(recipes_by_shard)},
        },
        "reconciliation": {
            "blocks_emitted_plus_skipped": len(machines) + sum(skipped_blocks.values()),
            "blocks_raw_total": len(raw_block_decls),
            "blocks_balanced": (len(machines) + sum(skipped_blocks.values())) == len(raw_block_decls),
        },
        "pruned_unused_resources": {k: sorted(v) for k, v in sorted(pruned_resources.items())},
        "skipped_blocks_by_reason": dict(sorted(skipped_blocks.items())),
        "skipped_block_examples": {k: sorted(v) for k, v in sorted(skipped_block_examples.items())},
        "skipped_recipes_by_reason": dict(sorted(skipped_recipes.items())),
        "skipped_recipe_examples": {k: sorted(v) for k, v in sorted(skipped_recipe_examples.items())},
        "id_collisions": id_collisions,
        "merged_duplicate_ports": merged_ports_log,
    }
    write_json(REPORT_PATH, report)

    print(
        f"Generated packs/mindustry/160.8: {len(emitted_resources)} resources, "
        f"{len(machines)} machines, {total_recipes} recipes "
        f"(blocks reconciled: {report['reconciliation']['blocks_emitted_plus_skipped']}/{report['reconciliation']['blocks_raw_total']})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
