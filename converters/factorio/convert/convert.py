#!/usr/bin/env python3
"""Deterministic Factorio 2.1.25 -> Factory Planner GameData v4 converter.

Reads read-only Factorio 2.1.25 dump under raw/factorio/2.1.25/script-output/
plus converters/factorio/template/{game.json,overrides.json,waivers.json}.
Deletes and rewrites ONLY JSON files inside packs/factorio/2.1.25/ and
converters/factorio/report.json. Never modifies raw/ or icons.pak.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = REPO_ROOT / "raw" / "factorio" / "2.1.25" / "script-output"
CONV_DIR = REPO_ROOT / "converters" / "factorio"
TEMPLATE_DIR = CONV_DIR / "template"
OUT_DIR = REPO_ROOT / "packs" / "factorio" / "2.1.25"
REPORT_PATH = CONV_DIR / "report.json"

SURFACES = ("nauvis", "vulcanus", "gleba", "fulgora", "aquilo", "space-platform")
SURFACE_ATTR_MAP = {
    "nauvis": "on_nauvis",
    "vulcanus": "on_vulcanus",
    "gleba": "on_gleba",
    "fulgora": "on_fulgora",
    "aquilo": "on_aquilo",
    "space-platform": "on_space",
}

PROD_TECH_MAP = {
    "steel-plate-productivity": "steel",
    "low-density-structure-productivity": "lds",
    "plastic-bar-productivity": "plastic",
    "processing-unit-productivity": "processing-unit",
    "rocket-fuel-productivity": "rocket-fuel",
    "rocket-part-productivity": "rocket-part",
    "scrap-recycling-productivity": "scrap",
    "asteroid-productivity": "asteroid",
}

EXCLUDED_TOOL_TYPES = {
    "blueprint",
    "blueprint-book",
    "copy-paste-tool",
    "deconstruction-item",
    "selection-tool",
    "upgrade-item",
}

# Machine preference order when multiple machines can run a recipe (default machine is first)
MACHINE_PREF_ORDER = [
    "assembling-machine-2",
    "assembling-machine-3",
    "assembling-machine-1",
    "electric-furnace",
    "steel-furnace",
    "stone-furnace",
    "electromagnetic-plant",
    "foundry",
    "cryogenic-plant",
    "biochamber",
    "chemical-plant",
    "oil-refinery",
    "centrifuge",
    "crusher",
    "recycler",
    "rocket-silo",
    "captive-biter-spawner",
    "electric-mining-drill",
    "big-mining-drill",
    "burner-mining-drill",
    "pumpjack",
    "lab",
    "biolab",
]
MACHINE_PREF_RANK = {m: i for i, m in enumerate(MACHINE_PREF_ORDER)}

SCIENCE_PACK_ORDER = [
    ("automation-science-pack", "automation"),
    ("logistic-science-pack", "logistic"),
    ("military-science-pack", "military"),
    ("chemical-science-pack", "chemical"),
    ("production-science-pack", "production"),
    ("utility-science-pack", "utility"),
    ("space-science-pack", "space"),
    ("metallurgic-science-pack", "metallurgic"),
    ("agricultural-science-pack", "agricultural"),
    ("electromagnetic-science-pack", "electromagnetic"),
    ("cryogenic-science-pack", "cryogenic"),
    ("promethium-science-pack", "promethium"),
]

POWER_RE = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)\s*([a-zA-Z]*)\s*$")

POWER_TO_MW = {
    "W": 1e-6,
    "kW": 1e-3,
    "MW": 1.0,
    "GW": 1e3,
    "TW": 1e6,
}

ENERGY_TO_MJ = {
    "J": 1e-6,
    "kJ": 1e-3,
    "MJ": 1.0,
    "GJ": 1e3,
    "TJ": 1e6,
}


def slugify(s: str) -> str:
    s = s.strip().lower().replace("+", "plus")
    s = re.sub(r"[:./]", "-", s)
    s = re.sub(r"[^a-z0-9\s:._-]", "", s)
    s = re.sub(r"[\s-]+", "-", s)
    return s.strip("-")


def clean_num(val: float) -> int | float:
    if not math.isfinite(val):
        raise ValueError(f"Non-finite number: {val}")
    if abs(val) < 1e-12:
        return 0
    rounded = round(val, 10)
    if abs(rounded - round(rounded)) < 1e-10:
        return int(round(rounded))
    return rounded


def parse_power_mw(s: str | None) -> float:
    if not s:
        return 0.0
    m = POWER_RE.match(str(s))
    if not m:
        raise ValueError(f"Unparseable power string: {s!r}")
    val = float(m.group(1))
    unit = m.group(2)
    if unit not in POWER_TO_MW:
        raise ValueError(f"Unknown power unit {unit!r} in {s!r}")
    return val * POWER_TO_MW[unit]


def parse_energy_mj(s: str | None) -> float:
    if not s:
        return 0.0
    m = POWER_RE.match(str(s))
    if not m:
        raise ValueError(f"Unparseable energy string: {s!r}")
    val = float(m.group(1))
    unit = m.group(2)
    if unit not in ENERGY_TO_MJ:
        raise ValueError(f"Unknown energy unit {unit!r} in {s!r}")
    return val * ENERGY_TO_MJ[unit]


def compute_surface_props(raw: dict[str, Any]) -> dict[str, dict[str, float]]:
    defaults = {k: float(v["default_value"]) for k, v in raw["surface-property"].items()}
    surfaces: dict[str, dict[str, float]] = {}
    for pid in ("nauvis", "vulcanus", "gleba", "fulgora", "aquilo"):
        props = dict(defaults)
        for k, v in (raw["planet"][pid].get("surface_properties") or {}).items():
            props[k] = float(v)
        surfaces[pid] = props
    sp = dict(defaults)
    for k, v in (raw["surface"]["space-platform"].get("surface_properties") or {}).items():
        sp[k] = float(v)
    surfaces["space-platform"] = sp
    return surfaces


def eval_surface_conditions(
    conds: list[dict[str, Any]] | None,
    surface_props: dict[str, dict[str, float]],
) -> set[str]:
    if not conds:
        return set(SURFACES)
    allowed: set[str] = set()
    for sname, props in surface_props.items():
        ok = True
        for c in conds:
            val = props[c["property"]]
            if "min" in c and val < float(c["min"]):
                ok = False
                break
            if "max" in c and val > float(c["max"]):
                ok = False
                break
        if ok:
            allowed.add(sname)
    return allowed


def surface_attrs_from_allowed(allowed: set[str]) -> dict[str, bool]:
    # Only emit non-default (False) booleans to keep JSON compact and clean.
    attrs: dict[str, bool] = {}
    for s in SURFACES:
        if s not in allowed:
            attrs[SURFACE_ATTR_MAP[s]] = False
    return attrs


def load_locale(name: str) -> dict[str, str]:
    with open(RAW_DIR / f"{name}-locale.json", "r", encoding="utf-8") as f:
        return json.load(f).get("names", {})


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
    path.write_text(text, encoding="utf-8")


def format_signed_pct(val: float) -> str:
    pct = val * 100.0
    sign = "+" if pct > 0 else "-"
    mag = abs(pct)
    if abs(mag - round(mag)) < 1e-9:
        num = f"{int(round(mag))}"
    else:
        num = f"{mag:.4f}".rstrip("0").rstrip(".")
    return f"{sign}{num}%"


def build_module_tooltip(mod_proto: dict[str, Any]) -> str:
    effect = mod_proto.get("effect") or {}
    category = mod_proto.get("category", "")
    cat_to_stat = {
        "productivity": "productivity",
        "speed": "speed",
        "efficiency": "consumption",
        "quality": "quality",
    }
    stat_labels = {
        "productivity": "Productivity",
        "speed": "Speed",
        "consumption": "Consumption",
        "pollution": "Pollution",
        "quality": "Quality",
    }
    base_order = ["productivity", "speed", "consumption", "pollution", "quality"]
    primary = cat_to_stat.get(category)
    order = ([primary] if primary else []) + [k for k in base_order if k != primary]
    parts = []
    for key in order:
        raw_v = effect.get(key)
        if raw_v is not None and abs(float(raw_v)) > 1e-12:
            parts.append(f"{stat_labels[key]} {format_signed_pct(float(raw_v))}")
    return ", ".join(parts)


def clean_json_outputs(pkg_dir: Path) -> None:
    """Remove only JSON files inside target package directory; never touch icons.pak."""
    if not pkg_dir.exists():
        pkg_dir.mkdir(parents=True, exist_ok=True)
        return
    for p in sorted(pkg_dir.rglob("*.json")):
        p.unlink()


def convert() -> dict[str, Any]:
    with open(RAW_DIR / "data-raw-dump.json", "r", encoding="utf-8") as f:
        raw = json.load(f)
    with open(TEMPLATE_DIR / "game.json", "r", encoding="utf-8") as f:
        template = json.load(f)
    with open(TEMPLATE_DIR / "overrides.json", "r", encoding="utf-8") as f:
        overrides = json.load(f)
    with open(TEMPLATE_DIR / "waivers.json", "r", encoding="utf-8") as f:
        waivers = json.load(f)

    item_locale = load_locale("item")
    fluid_locale = load_locale("fluid")
    entity_locale = load_locale("entity")
    recipe_locale = load_locale("recipe")

    surface_props = compute_surface_props(raw)

    # Index all stackable item prototypes across item subtypes
    item_protos: dict[str, tuple[str, dict[str, Any]]] = {}
    for ptype, bucket in sorted(raw.items()):
        if isinstance(bucket, dict):
            for name, obj in sorted(bucket.items()):
                if isinstance(obj, dict) and "stack_size" in obj:
                    item_protos[name] = (ptype, obj)

    # Planet natural availability from map_gen_settings
    resource_planets: dict[str, set[str]] = {}
    fluid_tile_planets: dict[str, set[str]] = {}
    plant_planets: dict[str, set[str]] = {
        "yumako-tree": {"gleba"},
        "jellystem": {"gleba"},
        "tree-plant": {"nauvis"},
    }
    for pid in ("nauvis", "vulcanus", "gleba", "fulgora", "aquilo"):
        mgs = raw["planet"][pid].get("map_gen_settings") or {}
        ae = (mgs.get("autoplace_settings") or {}).get("entity", {}).get("settings", {})
        at = (mgs.get("autoplace_settings") or {}).get("tile", {}).get("settings", {})
        for ent in ae.keys():
            if ent in raw["resource"]:
                resource_planets.setdefault(ent, set()).add(pid)
        for tile_name in at.keys():
            fl = (raw["tile"].get(tile_name) or {}).get("fluid")
            if fl:
                fluid_tile_planets.setdefault(fl, set()).add(pid)

    # Recipe productivity tech mapping (dynamic from raw technologies)
    recipe_prod_tech: dict[str, str] = {}
    for tname, tech in sorted(raw["technology"].items()):
        if tname in PROD_TECH_MAP:
            code = PROD_TECH_MAP[tname]
            for eff in tech.get("effects") or []:
                if eff.get("type") == "change-recipe-productivity":
                    recipe_prod_tech[eff["recipe"]] = code

    report: dict[str, Any] = {
        "game_version": "2.1.25",
        "skipped_recipes": [],
        "skipped_machines": [],
        "pruned_resources": [],
        "merged_duplicate_ports": [],
        "id_collisions": [],
        "counts": {},
    }

    # ------------------------------------------------------------------
    # 1. MACHINES
    # ------------------------------------------------------------------
    machines: list[dict[str, Any]] = []
    machine_by_id: dict[str, dict[str, Any]] = {}
    crafter_cats: dict[str, list[str]] = {}  # recipe_category -> [machine_ids]

    def register_machine(entry: dict[str, Any]) -> None:
        mid = entry["id"]
        if mid in machine_by_id:
            report["id_collisions"].append({"kind": "machine", "id": mid})
            raise ValueError(f"Duplicate machine id: {mid}")
        machine_by_id[mid] = entry
        machines.append(entry)

    # 1a. Crafting machines: assembling-machine, furnace, rocket-silo
    for ptype in ("assembling-machine", "furnace", "rocket-silo"):
        for eid, obj in sorted(raw.get(ptype, {}).items()):
            if obj.get("hidden"):
                report["skipped_machines"].append({"id": eid, "type": ptype, "reason": "hidden_prototype"})
                continue
            mid = slugify(eid)
            es = obj.get("energy_source") or {}
            es_type = es.get("type", "electric")
            power_mw = parse_power_mw(obj.get("energy_usage"))
            drain_mw = 0.0
            burner_cat = ""
            burner_eff = 1.0
            if es_type == "electric":
                if "drain" in es:
                    drain_mw = parse_power_mw(es["drain"])
                else:
                    # prototype-api.json: CraftingMachinePrototype electric drain defaults to energy_usage / 30
                    drain_mw = power_mw / 30.0
            elif es_type == "burner":
                fcats = es.get("fuel_categories") or ["chemical"]
                burner_cat = fcats[0]
                burner_eff = float(es.get("effectivity", 1.0))

            heating_mw = parse_power_mw(obj.get("heating_energy"))
            mod_slots = int(obj.get("module_slots", 0))
            er = obj.get("effect_receiver") or {}
            base_prod = float((er.get("base_effect") or {}).get("productivity", 0.0))

            # prototype-api.json: CraftingMachinePrototype.allowed_effects defaults to no effects allowed
            raw_ae = obj.get("allowed_effects")
            ae_set = set(raw_ae) if isinstance(raw_ae, list) else set()
            uses_mod = er.get("uses_module_effects", True)
            uses_bcn = er.get("uses_beacon_effects", True)
            allows_prod = uses_mod and ("productivity" in ae_set)
            allows_qual = uses_mod and ("quality" in ae_set)
            allows_beacons = bool(uses_bcn and len(ae_set & {"speed", "consumption", "pollution"}) > 0)

            emissions = es.get("emissions_per_minute") or {}
            pol = float(emissions.get("pollution", 0.0))

            allowed_s = eval_surface_conditions(obj.get("surface_conditions"), surface_props)

            attrs: dict[str, Any] = {}
            if power_mw != 0:
                attrs["power"] = clean_num(power_mw)
            if drain_mw != 0:
                attrs["drain"] = clean_num(drain_mw)
            if heating_mw != 0:
                attrs["heating_energy"] = clean_num(heating_mw)
            if mod_slots > 0:
                attrs["module_slots"] = mod_slots
            if base_prod != 0:
                attrs["base_prod"] = clean_num(base_prod)
            if allows_prod:
                attrs["allows_productivity"] = True
            if allows_qual:
                attrs["allows_quality"] = True
            if allows_beacons:
                attrs["allows_beacons"] = True
            if burner_cat:
                attrs["burner_cat"] = burner_cat
            if burner_eff != 1.0:
                attrs["burner_eff"] = clean_num(burner_eff)
            if pol != 0:
                attrs["pollution"] = clean_num(pol)
            attrs.update(surface_attrs_from_allowed(allowed_s))

            register_machine({
                "id": mid,
                "name": entity_locale.get(eid, eid),
                "profile": "fa_crafter",
                "speed": clean_num(float(obj["crafting_speed"])),
                "attrs": attrs,
            })

            for cat in obj.get("crafting_categories") or []:
                crafter_cats.setdefault(cat, []).append(mid)

    # Sort crafter lists by intentional preference rank then alphabetical
    for cat in crafter_cats:
        crafter_cats[cat].sort(key=lambda m: (MACHINE_PREF_RANK.get(m, 999), m))

    # 1b. Mining drills & pumpjack
    drill_cats: dict[str, list[str]] = {}
    drill_has_fluid_in: dict[str, bool] = {}
    for eid, obj in sorted(raw.get("mining-drill", {}).items()):
        if obj.get("hidden"):
            report["skipped_machines"].append({"id": eid, "type": "mining-drill", "reason": "hidden_prototype"})
            continue
        mid = slugify(eid)
        es = obj.get("energy_source") or {}
        es_type = es.get("type", "electric")
        power_mw = parse_power_mw(obj.get("energy_usage"))
        burner_cat = ""
        burner_eff = 1.0
        if es_type == "burner":
            burner_cat = (es.get("fuel_categories") or ["chemical"])[0]
            burner_eff = float(es.get("effectivity", 1.0))

        heating_mw = parse_power_mw(obj.get("heating_energy"))
        mod_slots = int(obj.get("module_slots", 0))
        er = obj.get("effect_receiver") or {}
        # prototype-api.json: MiningDrillPrototype.allowed_effects defaults to ALL effects allowed
        if "allowed_effects" not in obj:
            ae_set = {"consumption", "speed", "productivity", "pollution", "quality"}
        elif isinstance(obj["allowed_effects"], list):
            ae_set = set(obj["allowed_effects"])
        else:
            ae_set = set()
        uses_mod = er.get("uses_module_effects", True)
        uses_bcn = er.get("uses_beacon_effects", True)
        allows_prod = uses_mod and ("productivity" in ae_set)
        allows_qual = uses_mod and ("quality" in ae_set)
        allows_beacons = bool(uses_bcn and len(ae_set & {"speed", "consumption", "pollution"}) > 0)

        pol = float((es.get("emissions_per_minute") or {}).get("pollution", 0.0))
        allowed_s = eval_surface_conditions(obj.get("surface_conditions"), surface_props)

        attrs = {}
        if power_mw != 0:
            attrs["power"] = clean_num(power_mw)
        if heating_mw != 0:
            attrs["heating_energy"] = clean_num(heating_mw)
        if mod_slots > 0:
            attrs["module_slots"] = mod_slots
        if allows_prod:
            attrs["allows_productivity"] = True
        if allows_qual:
            attrs["allows_quality"] = True
        if allows_beacons:
            attrs["allows_beacons"] = True
        if burner_cat:
            attrs["burner_cat"] = burner_cat
        if burner_eff != 1.0:
            attrs["burner_eff"] = clean_num(burner_eff)
        if pol != 0:
            attrs["pollution"] = clean_num(pol)
        attrs.update(surface_attrs_from_allowed(allowed_s))

        register_machine({
            "id": mid,
            "name": entity_locale.get(eid, eid),
            "profile": "fa_miner",
            "speed": clean_num(float(obj["mining_speed"])),
            "attrs": attrs,
        })
        drill_has_fluid_in[mid] = "input_fluid_box" in obj
        for rc in obj.get("resource_categories") or ["basic-solid"]:
            drill_cats.setdefault(rc, []).append(mid)

    for rc in drill_cats:
        drill_cats[rc].sort(key=lambda m: (MACHINE_PREF_RANK.get(m, 999), m))

    # 1c. Offshore pump
    for eid, obj in sorted(raw.get("offshore-pump", {}).items()):
        if obj.get("hidden"):
            continue
        allowed_s = eval_surface_conditions(obj.get("surface_conditions"), surface_props)
        heating_mw = parse_power_mw(obj.get("heating_energy"))
        attrs = surface_attrs_from_allowed(allowed_s)
        if heating_mw != 0:
            attrs["heating_energy"] = clean_num(heating_mw)
        register_machine({
            "id": slugify(eid),
            "name": entity_locale.get(eid, eid),
            "profile": "fa_offshore",
            "speed": 1,
            "attrs": attrs,
        })

    # 1d. Agricultural tower
    for eid, obj in sorted(raw.get("agricultural-tower", {}).items()):
        if obj.get("hidden"):
            continue
        es = obj.get("energy_source") or {}
        allowed_s = eval_surface_conditions(obj.get("surface_conditions"), surface_props)
        attrs = {
            "power": clean_num(parse_power_mw(obj.get("energy_usage"))),
            "spores": clean_num(float((es.get("emissions_per_minute") or {}).get("spores", 0.0))),
        }
        heating_mw = parse_power_mw(obj.get("heating_energy"))
        if heating_mw != 0:
            attrs["heating_energy"] = clean_num(heating_mw)
        attrs.update(surface_attrs_from_allowed(allowed_s))
        register_machine({
            "id": slugify(eid),
            "name": entity_locale.get(eid, eid),
            "profile": "fa_agriculture",
            "speed": 1,
            "attrs": attrs,
        })

    # 1e. Boilers & Heat Exchangers
    for eid, obj in sorted(raw.get("boiler", {}).items()):
        if obj.get("hidden"):
            continue
        es = obj.get("energy_source") or {}
        es_type = es.get("type", "burner")
        power_mw = parse_power_mw(obj.get("energy_consumption"))
        allowed_s = eval_surface_conditions(obj.get("surface_conditions"), surface_props)
        attrs = {"power": clean_num(power_mw)}
        if es_type == "burner":
            attrs["burner_cat"] = (es.get("fuel_categories") or ["chemical"])[0]
            eff = float(es.get("effectivity", 1.0))
            if eff != 1.0:
                attrs["burner_eff"] = clean_num(eff)
            pol = float((es.get("emissions_per_minute") or {}).get("pollution", 0.0))
            if pol != 0:
                attrs["pollution"] = clean_num(pol)
        heating_mw = parse_power_mw(obj.get("heating_energy"))
        if heating_mw != 0:
            attrs["heating_energy"] = clean_num(heating_mw)
        attrs.update(surface_attrs_from_allowed(allowed_s))
        register_machine({
            "id": slugify(eid),
            "name": entity_locale.get(eid, eid),
            "profile": "fa_boiler",
            "speed": 1,
            "attrs": attrs,
        })

    # 1f. Steam Engine & Steam Turbine
    for eid, obj in sorted(raw.get("generator", {}).items()):
        if obj.get("hidden"):
            continue
        allowed_s = eval_surface_conditions(obj.get("surface_conditions"), surface_props)
        attrs = surface_attrs_from_allowed(allowed_s)
        heating_mw = parse_power_mw(obj.get("heating_energy"))
        if heating_mw != 0:
            attrs["heating_energy"] = clean_num(heating_mw)
        register_machine({
            "id": slugify(eid),
            "name": entity_locale.get(eid, eid),
            "profile": "fa_generator",
            "speed": 1,
            "attrs": attrs,
        })

    # 1g. Nuclear Reactor & Heating Tower
    for eid, obj in sorted(raw.get("reactor", {}).items()):
        if obj.get("hidden"):
            continue
        es = obj.get("energy_source") or {}
        power_mw = parse_power_mw(obj.get("consumption"))
        fcats = es.get("fuel_categories") or ["chemical"]
        eff = float(es.get("effectivity", 1.0))
        pol = float((es.get("emissions_per_minute") or {}).get("pollution", 0.0))
        nb = float(obj.get("neighbour_bonus", 1.0))
        conns = (obj.get("neighbour_connectable") or {}).get("connections") or []
        max_nb = len(conns) if nb > 0 else 0
        allowed_s = eval_surface_conditions(obj.get("surface_conditions"), surface_props)
        attrs = {"power": clean_num(power_mw)}
        if fcats[0] == "chemical":
            attrs["burner_cat"] = "chemical"
        if eff != 1.0:
            attrs["burner_eff"] = clean_num(eff)
        if pol != 0:
            attrs["pollution"] = clean_num(pol)
        if max_nb > 0:
            attrs["max_neighbors"] = max_nb
        attrs.update(surface_attrs_from_allowed(allowed_s))
        register_machine({
            "id": slugify(eid),
            "name": entity_locale.get(eid, eid),
            "profile": "fa_reactor",
            "speed": 1,
            "attrs": attrs,
        })

    # 1h. Fusion Reactor & Fusion Generator
    for eid, obj in sorted(raw.get("fusion-reactor", {}).items()):
        if obj.get("hidden"):
            continue
        allowed_s = eval_surface_conditions(obj.get("surface_conditions"), surface_props)
        attrs = {"power": clean_num(parse_power_mw(obj.get("power_input")))}
        attrs.update(surface_attrs_from_allowed(allowed_s))
        register_machine({
            "id": slugify(eid),
            "name": entity_locale.get(eid, eid),
            "profile": "fa_fusion_reactor",
            "speed": 1,
            "attrs": attrs,
        })

    for eid, obj in sorted(raw.get("fusion-generator", {}).items()):
        if obj.get("hidden"):
            continue
        allowed_s = eval_surface_conditions(obj.get("surface_conditions"), surface_props)
        attrs = surface_attrs_from_allowed(allowed_s)
        register_machine({
            "id": slugify(eid),
            "name": entity_locale.get(eid, eid),
            "profile": "fa_fusion_generator",
            "speed": 1,
            "attrs": attrs,
        })

    # 1i. Solar Panel
    for eid, obj in sorted(raw.get("solar-panel", {}).items()):
        if obj.get("hidden"):
            continue
        allowed_s = eval_surface_conditions(obj.get("surface_conditions"), surface_props)
        attrs = {"power": clean_num(parse_power_mw(obj.get("production")))}
        attrs.update(surface_attrs_from_allowed(allowed_s))
        register_machine({
            "id": slugify(eid),
            "name": entity_locale.get(eid, eid),
            "profile": "fa_solar",
            "speed": 1,
            "attrs": attrs,
        })

    # 1j. Labs
    for eid, obj in sorted(raw.get("lab", {}).items()):
        if obj.get("hidden"):
            continue
        es = obj.get("energy_source") or {}
        power_mw = parse_power_mw(obj.get("energy_usage"))
        heating_mw = parse_power_mw(obj.get("heating_energy"))
        mod_slots = int(obj.get("module_slots", 0))
        pol = float((es.get("emissions_per_minute") or {}).get("pollution", 0.0))
        drain_pct = float(obj.get("science_pack_drain_rate_percent", 100.0)) / 100.0
        allowed_s = eval_surface_conditions(obj.get("surface_conditions"), surface_props)
        # prototype-api.json: LabPrototype.allowed_effects defaults to all except quality
        attrs = {
            "power": clean_num(power_mw),
            "module_slots": mod_slots,
            "allows_productivity": True,
            "allows_beacons": True,
        }
        if heating_mw != 0:
            attrs["heating_energy"] = clean_num(heating_mw)
        if pol != 0:
            attrs["pollution"] = clean_num(pol)
        if drain_pct != 1.0:
            attrs["science_drain"] = clean_num(drain_pct)
        attrs.update(surface_attrs_from_allowed(allowed_s))
        register_machine({
            "id": slugify(eid),
            "name": entity_locale.get(eid, eid),
            "profile": "fa_lab",
            "speed": clean_num(float(obj.get("researching_speed", 1.0))),
            "attrs": attrs,
        })

    # 1k. Passive Spoiling machine (D3)
    register_machine({
        "id": "spoiling",
        "name": "Spoiling",
        "profile": "fa_spoiling",
        "speed": 1,
        "attrs": {},
        "notes": "Passive item decay based on ItemPrototype.spoil_ticks and spoil_result (Factorio 2.1.25).",
    })

    # Log deferred / hidden machine prototypes explicitly
    for ptype, reason in [
        ("burner-generator", "hidden_prototype"),
        ("electric-energy-interface", "hidden_prototype"),
        ("asteroid-collector", "deferred_v2_route_dependent"),
        ("thruster", "deferred_v2_nonlinear_curve"),
        ("lightning-attractor", "deferred_v2_stochastic_lightning"),
    ]:
        for eid in sorted(raw.get(ptype, {}).keys()):
            report["skipped_machines"].append({"id": eid, "type": ptype, "reason": reason})

    # ------------------------------------------------------------------
    # 2. RECIPES (sharded across 9 files)
    # ------------------------------------------------------------------
    shards: dict[str, list[dict[str, Any]]] = {
        "crafting": [],
        "smelting": [],
        "chemistry_oil": [],
        "space_age": [],
        "extraction": [],
        "power_heat": [],
        "research": [],
        "spoilage": [],
        "recycling": [],
    }

    exclude_recipes = set(overrides.get("exclude_recipes") or [])
    seen_recipe_ids: set[str] = set()

    def add_recipe(shard: str, rec: dict[str, Any]) -> None:
        rid = rec["id"]
        if rid in seen_recipe_ids:
            report["id_collisions"].append({"kind": "recipe", "id": rid, "shard": shard})
            raise ValueError(f"Duplicate recipe id: {rid}")
        seen_recipe_ids.add(rid)
        shards[shard].append(rec)

    def choose_raw_shard(rid: str, cats: list[str], is_auto_recycling: bool) -> str:
        if is_auto_recycling or rid == "scrap-recycling":
            return "recycling"
        cat_set = set(cats)
        if cat_set == {"smelting"}:
            return "smelting"
        if cat_set & {"metallurgy", "electromagnetics", "organic", "cryogenics", "crushing", "captive-spawner-process"}:
            return "space_age"
        if cat_set & {"chemistry", "oil-processing"}:
            return "chemistry_oil"
        return "crafting"

    def convert_raw_port(
        port: dict[str, Any],
        is_output: bool,
        recipe_id: str,
    ) -> list[Any] | dict[str, Any]:
        pname = port["name"]
        ptype = port["type"]
        # Steam temperature handling (D18)
        if ptype == "fluid" and pname == "steam":
            if is_output:
                temp = float(port.get("temperature", 165))
                res_id = "steam-500c" if temp >= 400 else "steam-165c"
            else:
                # Port-bound resource_choice for any-temperature steam consumers
                param_name = "steam_temp_500" if recipe_id == "steam-condensation" else "steam_temp_165"
                amt = clean_num(float(port["amount"]))
                return {"resource_param": param_name, "amount": amt}
        else:
            res_id = slugify(pname)

        raw_amt = float(port.get("amount", 0))
        extra_frac = float(port.get("extra_count_fraction", 0.0))
        amt = raw_amt + extra_frac
        if amt <= 0:
            raise ValueError(f"Recipe {recipe_id} port {pname} resolved to non-positive amount {amt}")

        # Factorio 2.1 probability fields (ProductPrototypeBase)
        chance = 1.0
        if "independent_probability" in port:
            chance *= float(port["independent_probability"])
        if "shared_probability" in port:
            sp = port["shared_probability"]
            chance *= float(sp["max"]) - float(sp["min"])
        if chance <= 0 or chance > 1.0 + 1e-9:
            raise ValueError(f"Recipe {recipe_id} port {pname} invalid chance {chance}")
        chance = min(1.0, chance)

        catalyst = 0.0
        if is_output:
            # prototype-api.json: ignored_by_productivity defaults to ignored_by_stats
            if "ignored_by_productivity" in port:
                ign = float(port["ignored_by_productivity"])
            else:
                ign = float(port.get("ignored_by_stats", 0.0))
            catalyst = min(amt, max(0.0, ign))

        amt_c = clean_num(amt)
        chance_c = clean_num(chance)
        cat_c = clean_num(catalyst)

        if cat_c == 0:
            if chance_c == 1:
                return [res_id, amt_c]
            return [res_id, amt_c, chance_c]
        out_obj: dict[str, Any] = {"res": res_id, "amount": amt_c, "catalyst": cat_c}
        if chance_c != 1:
            out_obj["chance"] = chance_c
        return out_obj

    # Precompute non-hidden recipe referenced items (for pruning debug/pistol recycling)
    non_hidden_ref_items: set[str] = set()
    for r in raw["recipe"].values():
        if r.get("hidden") or r.get("parameter"):
            continue
        for p in (r.get("ingredients") or []) + (r.get("results") or []):
            if p.get("type") == "item":
                non_hidden_ref_items.add(p["name"])
    # Also include items from extraction/spoilage/fuels/science
    for res_obj in raw["resource"].values():
        m = res_obj.get("minable") or {}
        if m.get("result"):
            non_hidden_ref_items.add(m["result"])
        for p in m.get("results") or []:
            if p.get("type") == "item":
                non_hidden_ref_items.add(p["name"])
    for p_obj in raw["plant"].values():
        for p in (p_obj.get("minable") or {}).get("results") or []:
            if p.get("type") == "item":
                non_hidden_ref_items.add(p["name"])
    for ptype_name, (_, obj) in item_protos.items():
        if obj.get("spoil_result"):
            non_hidden_ref_items.add(ptype_name)
            non_hidden_ref_items.add(obj["spoil_result"])
        if obj.get("burnt_result"):
            non_hidden_ref_items.add(obj["burnt_result"])

    # 2a. Raw Factorio recipes (normal + gated gameplay recycling)
    for rid, r in sorted(raw["recipe"].items()):
        if rid in exclude_recipes:
            report["skipped_recipes"].append({"id": rid, "reason": "excluded_by_override"})
            continue
        if r.get("parameter"):
            report["skipped_recipes"].append({"id": rid, "reason": "parameter_template"})
            continue
        cats = r.get("categories") or ["crafting"]
        is_auto_recycling = bool(r.get("hidden") and "recycling" in cats)

        if r.get("hidden") and not is_auto_recycling:
            report["skipped_recipes"].append({"id": rid, "reason": "hidden_debug_or_creative"})
            continue

        if is_auto_recycling:
            ings = r.get("ingredients") or []
            if not ings:
                report["skipped_recipes"].append({"id": rid, "reason": "empty_recycling_recipe"})
                continue
            ing_name = ings[0]["name"]
            ptype, obj = item_protos.get(ing_name, ("unknown", {}))
            if obj.get("hidden") or ptype in EXCLUDED_TOOL_TYPES:
                report["skipped_recipes"].append({"id": rid, "reason": "recycling_hidden_or_tool_item"})
                continue
            if ing_name not in non_hidden_ref_items:
                report["skipped_recipes"].append({"id": rid, "reason": "recycling_unreferenced_debug_item"})
                continue

        # Resolve compatible crafting machines across all raw categories (D7)
        compat_machines: list[str] = []
        seen_m: set[str] = set()
        for c in cats:
            for m in crafter_cats.get(c, []):
                if m not in seen_m:
                    seen_m.add(m)
                    compat_machines.append(m)
        compat_machines.sort(key=lambda m: (MACHINE_PREF_RANK.get(m, 999), m))
        if not compat_machines:
            report["skipped_recipes"].append({"id": rid, "reason": f"no_compatible_machine:{cats}"})
            continue

        raw_ings = r.get("ingredients") or []
        raw_ress = r.get("results") or []
        if isinstance(raw_ings, dict):
            raw_ings = []
        if isinstance(raw_ress, dict):
            raw_ress = []

        in_ports = [convert_raw_port(p, False, rid) for p in raw_ings]
        out_ports = [convert_raw_port(p, True, rid) for p in raw_ress]
        if raw_ings and not in_ports:
            raise ValueError(f"Non-empty raw ingredients parsed to 0 ports for {rid}")
        if raw_ress and not out_ports:
            raise ValueError(f"Non-empty raw results parsed to 0 ports for {rid}")
        if not in_ports and not out_ports:
            report["skipped_recipes"].append({"id": rid, "reason": "zero_ports"})
            continue

        time_s = float(r.get("energy_required", 0.5))
        allowed_s = eval_surface_conditions(r.get("surface_conditions"), surface_props)

        attrs: dict[str, Any] = {}
        if r.get("allow_productivity"):
            attrs["allows_productivity"] = True
        if r.get("allow_quality") is False:
            attrs["allows_quality"] = False
        max_prod = float(r.get("maximum_productivity", 3.0))
        if max_prod != 3.0:
            attrs["max_prod"] = clean_num(max_prod)
        if rid in recipe_prod_tech:
            attrs["prod_tech"] = recipe_prod_tech[rid]
        if is_auto_recycling:
            attrs["is_auto_recycling"] = True
        attrs.update(surface_attrs_from_allowed(allowed_s))

        rec_entry: dict[str, Any] = {
            "id": slugify(rid),
            "name": recipe_locale.get(rid, rid),
            "machines": compat_machines,
            "time": clean_num(time_s),
        }
        if in_ports:
            rec_entry["in"] = in_ports
        if out_ports:
            rec_entry["out"] = out_ports
        if attrs:
            rec_entry["attrs"] = attrs

        add_recipe(choose_raw_shard(rid, cats, is_auto_recycling), rec_entry)

    # 2b. Extraction recipes: Solid mining drills & Pumpjacks (D8, D9)
    for res_id, res_obj in sorted(raw["resource"].items()):
        rcat = res_obj.get("category", "basic-solid")
        minable = res_obj.get("minable") or {}
        mtime = float(minable["mining_time"])
        req_fluid = minable.get("required_fluid")
        fluid_amt = float(minable.get("fluid_amount", 0.0))

        drills = list(drill_cats.get(rcat, []))
        if req_fluid:
            drills = [d for d in drills if drill_has_fluid_in.get(d, False)]
        if not drills:
            report["skipped_recipes"].append({"id": f"extract-{res_id}", "reason": f"no_drill_for_{rcat}"})
            continue

        is_fluid_well = rcat == "basic-fluid"
        is_infinite = bool(res_obj.get("infinite", False))

        in_ports = []
        if req_fluid and fluid_amt > 0:
            # Factorio wiki: 10 fluid_amount per 10 mining operations -> fluid_amount / 10 per mined item
            in_ports.append([slugify(req_fluid), clean_num(fluid_amt / 10.0)])

        out_ports = []
        if minable.get("result"):
            out_ports.append([slugify(minable["result"]), clean_num(float(minable.get("count", 1)))])
        else:
            for p in minable.get("results") or []:
                out_ports.append([slugify(p["name"]), clean_num(float(p["amount"]))])

        planets = resource_planets.get(res_id, set(SURFACES) - {"space-platform"})
        attrs = {"allows_productivity": True}
        if is_fluid_well:
            attrs["allows_quality"] = False
            if is_infinite:
                attrs["is_infinite_fluid"] = True
        attrs.update(surface_attrs_from_allowed(planets))

        display_target = entity_locale.get(res_id, res_id)
        if is_fluid_well:
            rec_id = f"pump-{slugify(res_id)}"
            rec_name = f"Pump {display_target}"
        else:
            rec_id = f"mine-{slugify(res_id)}"
            rec_name = f"Mine {display_target}"

        rec_entry = {
            "id": rec_id,
            "name": rec_name,
            "machines": drills,
            "time": clean_num(mtime),
            "out": out_ports,
            "attrs": attrs,
        }
        if in_ports:
            rec_entry["in"] = in_ports
        add_recipe("extraction", rec_entry)

    # 2c. Offshore Pump recipes (4 tile fluids)
    offshore_speed_per_s = float(raw["offshore-pump"]["offshore-pump"]["pumping_speed"]) * 60.0
    for fl_id, planets in sorted(fluid_tile_planets.items()):
        attrs = surface_attrs_from_allowed(planets)
        attrs["allows_quality"] = False
        add_recipe("extraction", {
            "id": f"offshore-{slugify(fl_id)}",
            "name": f"Pump {fluid_locale.get(fl_id, fl_id)} (offshore)",
            "machines": ["offshore-pump"],
            "time": 1,
            "out": [[slugify(fl_id), clean_num(offshore_speed_per_s)]],
            "attrs": attrs,
        })

    # 2d. Agricultural Tower recipes (D10 + harvest_spores)
    plant_to_seed: dict[str, str] = {}
    for iname, (_, obj) in item_protos.items():
        if obj.get("plant_result"):
            plant_to_seed[obj["plant_result"]] = iname

    for pid, p_obj in sorted(raw["plant"].items()):
        seed = plant_to_seed[pid]
        growth_s = float(p_obj["growth_ticks"]) / 60.0
        harvest_spores = float((p_obj.get("harvest_emissions") or {}).get("spores", 0.0))
        out_ports = [[slugify(p["name"]), clean_num(float(p["amount"]))] for p in (p_obj.get("minable") or {}).get("results") or []]
        planets = plant_planets.get(pid, {"nauvis", "gleba"})
        attrs: dict[str, Any] = surface_attrs_from_allowed(planets)
        if harvest_spores > 0:
            attrs["harvest_spores"] = clean_num(harvest_spores)
        add_recipe("extraction", {
            "id": f"grow-{slugify(pid)}",
            "name": f"Grow {entity_locale.get(pid, pid)}",
            "machines": ["agricultural-tower"],
            "time": clean_num(growth_s),
            "in": [[slugify(seed), 1]],
            "out": out_ports,
            "attrs": attrs,
        })

    # 2e. Power & Heat recipes (D18, D19, D20, D21)
    water_hc = parse_energy_mj(raw["fluid"]["water"]["heat_capacity"])  # 0.002 MJ/deg
    steam_hc = parse_energy_mj(raw["fluid"]["steam"]["heat_capacity"])  # 0.0002 MJ/deg
    water_t0 = float(raw["fluid"]["water"]["default_temperature"])      # 15 C
    steam_ratio = water_hc / steam_hc                                   # 10

    boiler_obj = raw["boiler"]["boiler"]
    boiler_mw = parse_power_mw(boiler_obj["energy_consumption"])        # 1.8 MW
    boiler_t = float(boiler_obj["target_temperature"])                  # 165 C
    boiler_steam_s = boiler_mw / ((boiler_t - water_t0) * steam_hc)     # 60/s
    boiler_water_s = boiler_steam_s / steam_ratio                       # 6/s
    boiler_surfaces = eval_surface_conditions(boiler_obj.get("surface_conditions"), surface_props)

    add_recipe("power_heat", {
        "id": "boiler-steam-165c",
        "name": "Boil water (165 °C steam)",
        "machines": ["boiler"],
        "time": 1,
        "in": [["water", clean_num(boiler_water_s)]],
        "out": [["steam-165c", clean_num(boiler_steam_s)]],
        "attrs": surface_attrs_from_allowed(boiler_surfaces),
    })

    hx_obj = raw["boiler"]["heat-exchanger"]
    hx_mw = parse_power_mw(hx_obj["energy_consumption"])                # 10 MW
    hx_t = float(hx_obj["target_temperature"])                          # 500 C
    hx_steam_s = hx_mw / ((hx_t - water_t0) * steam_hc)                 # 103.0927835/s
    hx_water_s = hx_steam_s / steam_ratio                               # 10.30927835/s

    add_recipe("power_heat", {
        "id": "heat-exchanger-steam-500c",
        "name": "Heat exchanger (500 °C steam)",
        "machines": ["heat-exchanger"],
        "time": 1,
        "in": [["water", clean_num(hx_water_s)], ["heat", clean_num(hx_mw)]],
        "out": [["steam-500c", clean_num(hx_steam_s)]],
    })

    se_obj = raw["generator"]["steam-engine"]
    se_steam_s = float(se_obj["fluid_usage_per_tick"]) * 60.0           # 30/s
    se_mw = se_steam_s * (float(se_obj["maximum_temperature"]) - water_t0) * steam_hc * float(se_obj.get("effectivity", 1.0))

    add_recipe("power_heat", {
        "id": "steam-engine-165c",
        "name": "Steam engine power (165 °C)",
        "machines": ["steam-engine"],
        "time": 1,
        "in": [["steam-165c", clean_num(se_steam_s)]],
        "attrs": {"gen_mw": clean_num(se_mw)},
    })

    st_obj = raw["generator"]["steam-turbine"]
    st_steam_s = float(st_obj["fluid_usage_per_tick"]) * 60.0           # 60/s
    st_eff = float(st_obj.get("effectivity", 1.0))
    st_mw_500 = st_steam_s * (float(st_obj["maximum_temperature"]) - water_t0) * steam_hc * st_eff
    st_mw_165 = st_steam_s * (boiler_t - water_t0) * steam_hc * st_eff

    add_recipe("power_heat", {
        "id": "steam-turbine-500c",
        "name": "Steam turbine power (500 °C)",
        "machines": ["steam-turbine"],
        "time": 1,
        "in": [["steam-500c", clean_num(st_steam_s)]],
        "attrs": {"gen_mw": clean_num(st_mw_500)},
    })
    add_recipe("power_heat", {
        "id": "steam-turbine-165c",
        "name": "Steam turbine power (165 °C)",
        "machines": ["steam-turbine"],
        "time": 1,
        "in": [["steam-165c", clean_num(st_steam_s)]],
        "attrs": {"gen_mw": clean_num(st_mw_165)},
    })

    nuc_obj = raw["reactor"]["nuclear-reactor"]
    nuc_mw = parse_power_mw(nuc_obj["consumption"])                     # 40 MW
    nuc_cell_mj = parse_energy_mj(raw["item"]["uranium-fuel-cell"]["fuel_value"])  # 8000 MJ
    nuc_burn_s = nuc_cell_mj / nuc_mw                                   # 200 s
    nuc_burnt = raw["item"]["uranium-fuel-cell"]["burnt_result"]

    add_recipe("power_heat", {
        "id": "nuclear-reactor-heat",
        "name": "Nuclear reactor heat",
        "machines": ["nuclear-reactor"],
        "time": clean_num(nuc_burn_s),
        "in": [["uranium-fuel-cell", 1]],
        "out": [
            [slugify(nuc_burnt), 1],
            {"res": "heat", "amount": clean_num(nuc_cell_mj), "attrs": {"is_heat": True}},
        ],
    })

    ht_obj = raw["reactor"]["heating-tower"]
    ht_mw = parse_power_mw(ht_obj["consumption"])                       # 40 MW
    ht_surfaces = eval_surface_conditions(ht_obj.get("surface_conditions"), surface_props)

    add_recipe("power_heat", {
        "id": "heating-tower-heat",
        "name": "Heating tower heat",
        "machines": ["heating-tower"],
        "time": 1,
        "out": [{"res": "heat", "amount": clean_num(ht_mw), "attrs": {"is_heat": True}}],
        "attrs": surface_attrs_from_allowed(ht_surfaces),
    })

    fr_obj = raw["fusion-reactor"]["fusion-reactor"]
    fr_fluid_s = float(fr_obj["max_fluid_usage"]) * 60.0                # 4/s
    plasma_hc = parse_energy_mj(raw["fluid"]["fusion-plasma"]["heat_capacity"])  # 2.5e-5 MJ/deg
    plasma_t0 = float(raw["fluid"]["fusion-plasma"]["default_temperature"])      # 1e6 C
    fr_thermal_mw = fr_fluid_s * plasma_t0 * plasma_hc                  # 100 MW
    fr_cell_mj = parse_energy_mj(raw["item"]["fusion-power-cell"]["fuel_value"]) # 40000 MJ
    fr_burn_s = fr_cell_mj / fr_thermal_mw                              # 400 s
    fr_fluid_per_cell = fr_fluid_s * fr_burn_s                          # 1600

    add_recipe("power_heat", {
        "id": "fusion-reactor-plasma",
        "name": "Fusion plasma",
        "machines": ["fusion-reactor"],
        "time": clean_num(fr_burn_s),
        "in": [["fusion-power-cell", 1], ["fluoroketone-cold", clean_num(fr_fluid_per_cell)]],
        "out": [["fusion-plasma", clean_num(fr_fluid_per_cell)]],
    })

    fg_obj = raw["fusion-generator"]["fusion-generator"]
    fg_fluid_s = float(fg_obj["max_fluid_usage"]) * 60.0                # 2/s
    fg_mw = parse_power_mw(fg_obj["energy_source"]["output_flow_limit"]) # 50 MW

    add_recipe("power_heat", {
        "id": "fusion-generator-power",
        "name": "Fusion power",
        "machines": ["fusion-generator"],
        "time": 1,
        "in": [["fusion-plasma", clean_num(fg_fluid_s)]],
        "out": [["fluoroketone-hot", clean_num(fg_fluid_s)]],
        "attrs": {"gen_mw": clean_num(fg_mw)},
    })

    add_recipe("power_heat", {
        "id": "solar-power",
        "name": "Solar power",
        "machines": ["solar-panel"],
        "time": 1,
        "out": [["power", 1]],
    })

    # 2f. Unified Lab Research recipe (D24)
    lab_in_ports = []
    for pack_id, short_key in SCIENCE_PACK_ORDER:
        lab_in_ports.append({
            "res": pack_id,
            "amount": 1,
            "enabled": f"if(param.research_preset.is_custom, param.pack_{short_key}, param.research_preset.p_{short_key})",
        })
    add_recipe("research", {
        "id": "research",
        "name": "Research",
        "machines": ["lab", "biolab"],
        "time": 60,
        "in": lab_in_ports,
        "out": [["science", 1]],
        "attrs": {"allows_productivity": True, "allows_quality": False},
    })

    # 2g. Passive Spoiling recipes (D3)
    for iname, (_, obj) in sorted(item_protos.items()):
        if obj.get("spoil_result") and obj.get("spoil_ticks"):
            spoil_s = float(obj["spoil_ticks"]) / 60.0
            target = obj["spoil_result"]
            add_recipe("spoilage", {
                "id": f"spoil-{slugify(iname)}",
                "name": f"Spoil {item_locale.get(iname, iname)}",
                "machines": ["spoiling"],
                "time": clean_num(spoil_s),
                "in": [[slugify(iname), 1]],
                "out": [[slugify(target), 1]],
            })

    # ------------------------------------------------------------------
    # 3. RESOURCES (collect all referenced + fuels + template fixed ports, prune unused for V-W-2)
    # ------------------------------------------------------------------
    used_resources: set[str] = {
        "power",
        "heat",
        "steam-165c",
        "steam-500c",
        "nutrients",
        "bioflux",
        "science",
    }
    # Add all chemical fuels (tagged chemical_fuel for the fuel resource_choice)
    chemical_fuels: set[str] = set()
    for iname, (_, obj) in sorted(item_protos.items()):
        if obj.get("fuel_value") and "chemical" in (obj.get("fuel_categories") or []):
            chemical_fuels.add(slugify(iname))
            used_resources.add(slugify(iname))

    for rec_list in shards.values():
        for rec in rec_list:
            for p in rec.get("in") or []:
                if isinstance(p, list):
                    used_resources.add(p[0])
                elif "res" in p:
                    used_resources.add(p["res"])
            for p in rec.get("out") or []:
                if isinstance(p, list):
                    used_resources.add(p[0])
                elif "res" in p:
                    used_resources.add(p["res"])

    resources: list[dict[str, Any]] = []
    emitted_res_ids: set[str] = set()

    def add_resource(entry: dict[str, Any]) -> None:
        rid = entry["id"]
        if rid in emitted_res_ids:
            return
        emitted_res_ids.add(rid)
        resources.append(entry)

    # Items
    for iname, (ptype, obj) in sorted(item_protos.items()):
        rid = slugify(iname)
        if rid not in used_resources:
            report["pruned_resources"].append({"id": rid, "type": ptype, "reason": "unreferenced_item"})
            continue
        tags = []
        attrs: dict[str, Any] = {}
        if rid in chemical_fuels:
            tags.append("chemical_fuel")
        if obj.get("fuel_value"):
            attrs["fuel_mj"] = clean_num(parse_energy_mj(obj["fuel_value"]))
            fem = float(obj.get("fuel_emissions_multiplier", 1.0))
            if fem != 1.0:
                attrs["fuel_emissions_mult"] = clean_num(fem)
        entry: dict[str, Any] = {
            "id": rid,
            "name": item_locale.get(iname, entity_locale.get(iname, iname)),
            "kind": "item",
        }
        if tags:
            entry["tags"] = tags
        if attrs:
            entry["attrs"] = attrs
        add_resource(entry)

    # Fluids (except raw 'steam', which is split into steam-165c & steam-500c)
    for fname, obj in sorted(raw["fluid"].items()):
        if fname == "steam":
            report["pruned_resources"].append({"id": "steam", "type": "fluid", "reason": "split_into_steam_165c_and_steam_500c"})
            continue
        rid = slugify(fname)
        if rid not in used_resources:
            report["pruned_resources"].append({"id": rid, "type": "fluid", "reason": "unreferenced_fluid"})
            continue
        add_resource({
            "id": rid,
            "name": fluid_locale.get(fname, fname),
            "kind": "fluid",
        })

    # Synthetic / split resources
    add_resource({"id": "steam-165c", "name": "Steam (165 °C)", "kind": "fluid"})
    add_resource({"id": "steam-500c", "name": "Steam (500 °C)", "kind": "fluid"})
    add_resource({"id": "heat", "name": "Heat", "kind": "heat"})
    add_resource({"id": "power", "name": "Electric power", "kind": "power"})

    # Apply data overrides if any
    for rid, patch in sorted((overrides.get("resource_overrides") or {}).items()):
        for r in resources:
            if r["id"] == rid:
                r.update(patch)
    for mid, patch in sorted((overrides.get("machine_overrides") or {}).items()):
        for m in machines:
            if m["id"] == mid:
                m.update(patch)
    for rid, patch in sorted((overrides.get("recipe_overrides") or {}).items()):
        for rec_list in shards.values():
            for r in rec_list:
                if r["id"] == rid:
                    r.update(patch)

    # Deterministic sorting
    resources.sort(key=lambda x: x["id"])
    machines.sort(key=lambda x: x["id"])
    for k in shards:
        shards[k].sort(key=lambda x: x["id"])

    # ------------------------------------------------------------------
    # 4. EMIT PACKAGE JSON FILES (strict write scope: JSON only in OUT_DIR)
    # ------------------------------------------------------------------
    clean_json_outputs(OUT_DIR)

    include_list = [
        "waivers.json",
        "resources.json",
        "machines.json",
        "recipes",
    ]
    manifest = json.loads(json.dumps(template))
    manifest["include"] = include_list

    # Populate option_sets.modules tooltips directly from data-raw-dump.json (module.<id>.effect)
    mod_opts = (manifest.get("option_sets") or {}).get("modules", {}).get("options", [])
    raw_modules = raw.get("module") or {}
    for opt in mod_opts:
        key = opt["key"]
        if key not in raw_modules:
            raise ValueError(f"Module option {key!r} not found in raw['module']")
        opt["tooltip"] = build_module_tooltip(raw_modules[key])

    write_json(OUT_DIR / "game.json", manifest)
    write_json(OUT_DIR / "waivers.json", waivers)
    write_json(OUT_DIR / "resources.json", {"resources": resources})
    write_json(OUT_DIR / "machines.json", {"machines": machines})
    for shard_name in sorted(shards.keys()):
        if shards[shard_name]:
            write_json(OUT_DIR / "recipes" / f"{shard_name}.json", {"recipes": shards[shard_name]})

    # ------------------------------------------------------------------
    # 5. REPORT RECONCILIATION
    # ------------------------------------------------------------------
    skip_recipe_reasons = Counter(x["reason"] for x in report["skipped_recipes"])
    skip_machine_reasons = Counter(x["reason"] for x in report["skipped_machines"])
    pruned_res_reasons = Counter(x["reason"] for x in report["pruned_resources"])

    report["counts"] = {
        "raw_recipes_total": len(raw["recipe"]),
        "emitted_recipes_total": sum(len(v) for v in shards.values()),
        "emitted_recipes_by_shard": {k: len(shards[k]) for k in sorted(shards.keys())},
        "skipped_recipes_total": len(report["skipped_recipes"]),
        "skipped_recipes_by_reason": dict(sorted(skip_recipe_reasons.items())),
        "emitted_machines_total": len(machines),
        "skipped_machines_total": len(report["skipped_machines"]),
        "skipped_machines_by_reason": dict(sorted(skip_machine_reasons.items())),
        "emitted_resources_total": len(resources),
        "pruned_resources_total": len(report["pruned_resources"]),
        "pruned_resources_by_reason": dict(sorted(pruned_res_reasons.items())),
    }
    write_json(REPORT_PATH, report)
    return report


if __name__ == "__main__":
    rep = convert()
    c = rep["counts"]
    print(
        f"Factorio 2.1.25 converted: {c['emitted_resources_total']} resources, "
        f"{c['emitted_machines_total']} machines, {c['emitted_recipes_total']} recipes "
        f"(skipped raw recipes: {c['skipped_recipes_total']})."
    )
    print("Shards:", c["emitted_recipes_by_shard"])
