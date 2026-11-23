#!/usr/bin/env python3
"""Deterministic converter from Satisfactory raw Docs (en-US.json) to GameData v4."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
RAW_PATH = REPO_ROOT / "raw" / "satisfactory" / "en-US.json"
VERSION_PATH = REPO_ROOT / "raw" / "satisfactory" / "game_version"
TEMPLATE_PATH = REPO_ROOT / "converters" / "satisfactory" / "template" / "game.json"
OVERRIDES_PATH = REPO_ROOT / "converters" / "satisfactory" / "template" / "overrides.json"
WAIVERS_PATH = REPO_ROOT / "converters" / "satisfactory" / "template" / "waivers.json"
REPORT_PATH = REPO_ROOT / "converters" / "satisfactory" / "report.json"

ITEM_NATIVE_CLASSES = {
    "FGResourceDescriptor",
    "FGItemDescriptor",
    "FGEquipmentDescriptor",
    "FGItemDescriptorBiomass",
    "FGConsumableDescriptor",
    "FGAmmoTypeProjectile",
    "FGAmmoTypeSpreadshot",
    "FGAmmoTypeInstantHit",
    "FGItemDescriptorNuclearFuel",
    "FGPowerShardDescriptor",
    "FGItemDescriptorPowerBoosterFuel",
}

FORM_TO_KIND = {
    "RF_SOLID": "item",
    "RF_LIQUID": "fluid",
    "RF_GAS": "gas",
}

PORT_TUPLE_RE = re.compile(
    r'\(\s*ItemClass\s*=\s*"[^"]*\.([A-Za-z0-9_]+_C)\'?"\s*,\s*Amount\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*\)'
)
QUOTED_CLASS_RE = re.compile(r'\.([A-Za-z0-9_]+_C)\'?"')
PRODUCED_IN_TOKEN_RE = re.compile(r'"([^"]+)"')


def slugify(text: str) -> str:
    """Match core_gamedata slugify() specification (guide reference §8.2)."""
    s = text.strip().lower()
    s = s.replace("+", "plus")
    s = re.sub(r"[:./]", "-", s)
    s = re.sub(r"[^a-z0-9\s:._-]", "", s)
    s = re.sub(r"[\s-]+", "-", s)
    return s.strip("-")


def class_to_slug(cls: str, prefixes: tuple[str, ...]) -> str:
    """Convert Unreal ClassName to clean deterministic kebab-case slug."""
    s = cls
    for prefix in prefixes:
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    if s.endswith("_C"):
        s = s[:-2]
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", s)
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1-\2", s)
    s = s.replace("_", "-")
    return slugify(s)


def clean_num(val: float) -> int | float:
    """Round floats cleanly and convert exact whole numbers to int."""
    r = round(float(val), 6)
    if abs(r - round(r)) <= 1e-9:
        return int(round(r))
    return r


def dump_json(path: Path, data: Any) -> None:
    """Write deterministic strict JSON with trailing newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    path.write_text(text, encoding="utf-8")


def register_id(
    base_id: str,
    raw_key: str,
    used: dict[str, str],
    collisions: list[dict[str, str]],
) -> str:
    """Ensure deterministic unique entity IDs and log any collision."""
    if base_id not in used:
        used[base_id] = raw_key
        return base_id
    idx = 2
    while f"{base_id}-{idx}" in used:
        idx += 1
    new_id = f"{base_id}-{idx}"
    used[new_id] = raw_key
    collisions.append({"base_id": base_id, "resolved_id": new_id, "raw_key": raw_key})
    return new_id


def parse_ports(
    raw_str: str,
    item_by_cls: dict[str, dict[str, Any]],
    recipe_id: str,
    direction: str,
    merged_ports_log: list[dict[str, Any]],
) -> list[list[Any]]:
    """Parse Unreal ingredient/product string preserving port order; merge exact duplicates."""
    matches = PORT_TUPLE_RE.findall(raw_str or "")
    if not matches and raw_str and raw_str.strip() not in ("", "()"):
        raise ValueError(f"Failed to parse {direction} ports for {recipe_id}: {raw_str!r}")
    ports: list[list[Any]] = []
    seen_idx: dict[str, int] = {}
    for cls, amt_str in matches:
        item = item_by_cls.get(cls)
        if not item:
            raise KeyError(f"Unknown item ClassName {cls!r} in {recipe_id} ({direction})")
        res_id = item["id"]
        amt = float(amt_str)
        if item["is_fluid"]:
            amt /= 1000.0
        amt_clean = clean_num(amt)
        if res_id in seen_idx:
            prev_idx = seen_idx[res_id]
            prev_amt = ports[prev_idx][1]
            ports[prev_idx][1] = clean_num(prev_amt + amt_clean)
            merged_ports_log.append(
                {
                    "recipe": recipe_id,
                    "dir": direction,
                    "resource": res_id,
                    "merged_amount": amt_clean,
                }
            )
        else:
            seen_idx[res_id] = len(ports)
            ports.append([res_id, amt_clean])
    return ports


def main() -> None:
    raw_version = VERSION_PATH.read_text(encoding="utf-8").strip().lstrip("v")
    template = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    overrides = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))

    pkg_ver = template["game"]["data_version"]
    out_dir = REPO_ROOT / "packs" / "satisfactory" / pkg_ver

    raw_bytes = RAW_PATH.read_bytes()
    raw_docs = json.loads(raw_bytes.decode("utf-16"))
    by_nc: dict[str, list[dict[str, Any]]] = {
        entry["NativeClass"].split(".")[-1].rstrip("'"): entry.get("Classes", [])
        for entry in raw_docs
    }

    collisions: list[dict[str, str]] = []
    merged_ports: list[dict[str, Any]] = []
    skipped_counts: Counter[str] = Counter()
    skipped_samples: dict[str, list[dict[str, str]]] = defaultdict(list)

    def record_skip(reason: str, cls: str, name: str) -> None:
        skipped_counts[reason] += 1
        if len(skipped_samples[reason]) < 15:
            skipped_samples[reason].append({"class": cls, "name": name})

    # 1. Index all item descriptors (without emitting unused ones yet)
    item_by_cls: dict[str, dict[str, Any]] = {}
    used_resource_ids: dict[str, str] = {}
    for nc in sorted(ITEM_NATIVE_CLASSES):
        for c in by_nc.get(nc, []):
            cls = c["ClassName"]
            form = c.get("mForm", "RF_SOLID")
            kind = FORM_TO_KIND.get(form)
            if not kind:
                record_skip("invalid_resource_form", cls, c.get("mDisplayName", ""))
                continue
            rid = register_id(
                class_to_slug(cls, ("Desc_", "BP_")),
                cls,
                used_resource_ids,
                collisions,
            )
            item_by_cls[cls] = {
                "id": rid,
                "name": c.get("mDisplayName", rid),
                "kind": kind,
                "is_fluid": kind in ("fluid", "gas"),
                "energy": float(c.get("mEnergyValue") or 0.0),
                "sink_points": int(float(c.get("mResourceSinkPoints") or 0)),
                "class_name": cls,
                "native_class": nc,
            }

    # Add synthetic resources from overrides
    synthetic_resources: dict[str, dict[str, Any]] = {}
    for sr in overrides.get("synthetic_resources", []):
        sid = register_id(sr["id"], f"synthetic:{sr['id']}", used_resource_ids, collisions)
        sr_copy = dict(sr)
        sr_copy["id"] = sid
        synthetic_resources[sid] = sr_copy

    # 2. Index and emit machines
    used_machine_ids: dict[str, str] = {}
    machines: list[dict[str, Any]] = []
    machine_class_map: dict[str, str] = {}
    machine_overrides = overrides.get("machine_attr_overrides", {})

    def add_machine(cls: str, entry: dict[str, Any]) -> None:
        mid = entry["id"]
        register_id(mid, cls, used_machine_ids, collisions)
        machines.append(entry)
        machine_class_map[mid] = cls

    auto_producer_classes: dict[str, str] = {}  # raw ClassName -> profile

    # Manufacturers (fixed power)
    for c in by_nc.get("FGBuildableManufacturer", []):
        cls = c["ClassName"]
        mid = class_to_slug(cls, ("Build_",))
        profile = "sf_packager" if cls == "Build_Packager_C" else "sf_production"
        auto_producer_classes[cls] = profile
        can_boost = c.get("mCanChangeProductionBoost") == "True"
        slots = int(float(c.get("mProductionShardSlotSize") or 0)) if can_boost else 0
        if cls in machine_overrides and "somersloop_slots" in machine_overrides[cls]:
            slots = int(machine_overrides[cls]["somersloop_slots"])
        add_machine(
            cls,
            {
                "id": mid,
                "name": c["mDisplayName"],
                "profile": profile,
                "categories": [mid],
                "speed": clean_num(float(c.get("mManufacturingSpeed") or 1.0)),
                "attrs": {
                    "power": clean_num(float(c.get("mPowerConsumption") or 0.0)),
                    "power_exp": clean_num(float(c.get("mPowerConsumptionExponent") or 1.321929)),
                    "somersloop_slots": slots,
                },
            },
        )

    # Manufacturers (variable power)
    for c in by_nc.get("FGBuildableManufacturerVariablePower", []):
        cls = c["ClassName"]
        mid = class_to_slug(cls, ("Build_",))
        profile = "sf_variable_power"
        auto_producer_classes[cls] = profile
        can_boost = c.get("mCanChangeProductionBoost") == "True"
        slots = int(float(c.get("mProductionShardSlotSize") or 0)) if can_boost else 0
        add_machine(
            cls,
            {
                "id": mid,
                "name": c["mDisplayName"],
                "profile": profile,
                "categories": [mid],
                "speed": clean_num(float(c.get("mManufacturingSpeed") or 1.0)),
                "attrs": {
                    "power": 0,
                    "power_exp": clean_num(float(c.get("mPowerConsumptionExponent") or 1.321929)),
                    "somersloop_slots": slots,
                },
            },
        )

    # Resource extractors (Miners Mk.1-3 + Oil Extractor)
    oil_pump_raw = None
    for c in by_nc.get("FGBuildableResourceExtractor", []):
        cls = c["ClassName"]
        mid = class_to_slug(cls, ("Build_",))
        cycle = float(c.get("mExtractCycleTime") or 1.0)
        is_miner = cls.startswith("Build_Miner")
        cat = "miner" if is_miner else mid
        if not is_miner:
            oil_pump_raw = c
        add_machine(
            cls,
            {
                "id": mid,
                "name": c["mDisplayName"],
                "profile": "sf_extractor",
                "categories": [cat],
                "speed": clean_num(1.0 / cycle),
                "attrs": {
                    "power": clean_num(float(c.get("mPowerConsumption") or 0.0)),
                    "power_exp": clean_num(float(c.get("mPowerConsumptionExponent") or 1.321929)),
                },
            },
        )

    # Water Extractor
    water_pump_raw = None
    for c in by_nc.get("FGBuildableWaterPump", []):
        cls = c["ClassName"]
        mid = class_to_slug(cls, ("Build_",))
        cycle = float(c.get("mExtractCycleTime") or 1.0)
        water_pump_raw = c
        add_machine(
            cls,
            {
                "id": mid,
                "name": c["mDisplayName"],
                "profile": "sf_water_extractor",
                "categories": [mid],
                "speed": clean_num(1.0 / cycle),
                "attrs": {
                    "power": clean_num(float(c.get("mPowerConsumption") or 0.0)),
                    "power_exp": clean_num(float(c.get("mPowerConsumptionExponent") or 1.321929)),
                },
            },
        )

    # Resource Well Pressurizer + Extractor
    pressurizers = by_nc.get("FGBuildableFrackingActivator", [])
    pressurizer = pressurizers[0]
    record_skip(
        "merged_into_resource_well_extractor",
        pressurizer["ClassName"],
        pressurizer["mDisplayName"],
    )
    fracking_raw = None
    for c in by_nc.get("FGBuildableFrackingExtractor", []):
        cls = c["ClassName"]
        mid = class_to_slug(cls, ("Build_",))
        cycle = float(c.get("mExtractCycleTime") or 1.0)
        fracking_raw = c
        add_machine(
            cls,
            {
                "id": mid,
                "name": c["mDisplayName"],
                "profile": "sf_resource_well",
                "categories": [mid],
                "speed": clean_num(1.0 / cycle),
                "attrs": {
                    "power": clean_num(float(pressurizer.get("mPowerConsumption") or 0.0)),
                    "power_exp": clean_num(float(pressurizer.get("mPowerConsumptionExponent") or 1.321929)),
                },
            },
        )

    # Fuel & Nuclear Generators
    gen_records: list[dict[str, Any]] = []
    for nc in ("FGBuildableGeneratorFuel", "FGBuildableGeneratorNuclear"):
        for c in by_nc.get(nc, []):
            cls = c["ClassName"]
            mid = class_to_slug(cls, ("Build_",))
            gen_records.append(c)
            add_machine(
                cls,
                {
                    "id": mid,
                    "name": c["mDisplayName"],
                    "profile": "sf_generator",
                    "categories": [mid],
                    "speed": 1,
                    "attrs": {
                        "power": clean_num(float(c.get("mPowerProduction") or 0.0)),
                    },
                },
            )

    # Geothermal Generator
    for c in by_nc.get("FGBuildableGeneratorGeoThermal", []):
        cls = c["ClassName"]
        mid = class_to_slug(cls, ("Build_",))
        add_machine(
            cls,
            {
                "id": mid,
                "name": c["mDisplayName"],
                "profile": "sf_geothermal",
                "categories": [mid],
                "speed": 1,
                "attrs": {
                    "power": clean_num(float(c.get("mVariablePowerProductionFactor") or 200.0)),
                },
            },
        )

    # AWESOME Sink
    for c in by_nc.get("FGBuildableResourceSink", []):
        cls = c["ClassName"]
        mid = class_to_slug(cls, ("Build_",))
        add_machine(
            cls,
            {
                "id": mid,
                "name": c["mDisplayName"],
                "profile": "sf_sink",
                "categories": [mid],
                "speed": 1,
                "attrs": {
                    "power": clean_num(float(c.get("mPowerConsumption") or 30.0)),
                },
            },
        )

    # Space Elevator
    for c in by_nc.get("FGBuildableSpaceElevator", []):
        cls = c["ClassName"]
        mid = class_to_slug(cls, ("Build_",))
        add_machine(
            cls,
            {
                "id": mid,
                "name": c["mDisplayName"],
                "profile": "sf_space_elevator",
                "categories": [mid],
                "speed": 1,
                "attrs": {},
            },
        )

    # Log excluded specialty buildings
    for c in by_nc.get("FGBuildableFactorySimpleProducer", []):
        record_skip("ficsmas_excluded_building", c["ClassName"], c.get("mDisplayName", ""))
    for c in by_nc.get("FGBuildablePowerBooster", []):
        record_skip("unsupported_global_percentage_booster", c["ClassName"], c.get("mDisplayName", ""))

    # 3. Build recipes by category shard
    used_recipe_ids: dict[str, str] = {}
    recipes_by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)

    # Collect event-gated recipes from FGSchematic (catches FICSMAS recipes missing mRelevantEvents on FGRecipe)
    event_schematic_recipes: set[str] = set()
    for s in by_nc.get("FGSchematic", []):
        if s.get("mRelevantEvents"):
            event_schematic_recipes.update(QUOTED_CLASS_RE.findall(str(s.get("mUnlocks", ""))))

    # 3a. Automated FGRecipe entries
    for r in by_nc.get("FGRecipe", []):
        rcls = r["ClassName"]
        rname = r.get("mDisplayName", rcls)
        if r.get("mRelevantEvents") or rcls in event_schematic_recipes or "/Events/" in r.get("FullName", ""):
            record_skip("ficsmas_event_recipe", rcls, rname)
            continue
        tokens = [t.split(".")[-1] for t in PRODUCED_IN_TOKEN_RE.findall(r.get("mProducedIn", ""))]
        prods = [t for t in tokens if t in auto_producer_classes]
        if not prods:
            if not tokens:
                record_skip("no_producer_legacy_recipe", rcls, rname)
            elif any("BuildGun" in t for t in tokens):
                record_skip("buildgun_building_recipe", rcls, rname)
            elif any("Workshop" in t or "WorkShop" in t for t in tokens):
                record_skip("workshop_only_recipe", rcls, rname)
            elif any("WorkBench" in t for t in tokens):
                record_skip("workbench_only_recipe", rcls, rname)
            else:
                record_skip("other_non_automated_recipe", rcls, rname)
            continue
        if len(prods) > 1:
            raise RuntimeError(f"Expected single automated producer for {rcls}, got {prods}")

        prod_cls = prods[0]
        cat = class_to_slug(prod_cls, ("Build_",))
        rid = register_id(class_to_slug(rcls, ("Recipe_",)), rcls, used_recipe_ids, collisions)
        dur = float(r.get("mManufactoringDuration") or 0.0)
        if dur <= 0:
            record_skip("non_positive_duration", rcls, rname)
            continue

        in_ports = parse_ports(r.get("mIngredients", ""), item_by_cls, rid, "in", merged_ports)
        out_ports = parse_ports(r.get("mProduct", ""), item_by_cls, rid, "out", merged_ports)
        if not in_ports and not out_ports:
            record_skip("empty_ports", rcls, rname)
            continue

        rec_obj: dict[str, Any] = {
            "id": rid,
            "name": rname,
            "category": cat,
            "time": clean_num(dur),
            "in": in_ports,
            "out": out_ports,
        }
        if auto_producer_classes[prod_cls] == "sf_variable_power":
            rec_obj["attrs"] = {
                "min_power": clean_num(float(r.get("mVariablePowerConsumptionConstant") or 0.0)),
                "power_span": clean_num(float(r.get("mVariablePowerConsumptionFactor") or 0.0)),
            }
        recipes_by_cat[cat].append(rec_obj)

    for c in by_nc.get("FGCustomizationRecipe", []):
        record_skip("customization_recipe", c["ClassName"], c.get("mDisplayName", ""))

    # 3b. Extractor synthetic recipes
    for c in by_nc.get("FGResourceDescriptor", []):
        if c.get("mForm") != "RF_SOLID":
            continue
        item = item_by_cls[c["ClassName"]]
        rid = register_id(f"extract-{item['id']}", f"extract:{c['ClassName']}", used_recipe_ids, collisions)
        recipes_by_cat["miner"].append(
            {
                "id": rid,
                "name": f"Extract {item['name']}",
                "category": "miner",
                "time": 1,
                "in": [],
                "out": [[item["id"], 1]],
            }
        )

    if oil_pump_raw:
        amt = clean_num(float(oil_pump_raw.get("mItemsPerCycle") or 2000) / 1000.0)
        for cls in QUOTED_CLASS_RE.findall(oil_pump_raw.get("mAllowedResources", "")):
            item = item_by_cls[cls]
            rid = register_id(f"extract-{item['id']}", f"oil:{cls}", used_recipe_ids, collisions)
            recipes_by_cat["oil-pump"].append(
                {
                    "id": rid,
                    "name": f"Extract {item['name']}",
                    "category": "oil-pump",
                    "time": 1,
                    "in": [],
                    "out": [[item["id"], amt]],
                }
            )

    if water_pump_raw:
        amt = clean_num(float(water_pump_raw.get("mItemsPerCycle") or 2000) / 1000.0)
        item = item_by_cls["Desc_Water_C"]
        rid = register_id(f"extract-{item['id']}", "water:Desc_Water_C", used_recipe_ids, collisions)
        recipes_by_cat["water-pump"].append(
            {
                "id": rid,
                "name": f"Extract {item['name']}",
                "category": "water-pump",
                "time": 1,
                "in": [],
                "out": [[item["id"], amt]],
            }
        )

    if fracking_raw:
        amt = clean_num(float(fracking_raw.get("mItemsPerCycle") or 1000) / 1000.0)
        for cls in QUOTED_CLASS_RE.findall(fracking_raw.get("mAllowedResources", "")):
            item = item_by_cls[cls]
            rid = register_id(f"extract-well-{item['id']}", f"well:{cls}", used_recipe_ids, collisions)
            recipes_by_cat["fracking-extractor"].append(
                {
                    "id": rid,
                    "name": f"Extract {item['name']} (Resource Well)",
                    "category": "fracking-extractor",
                    "time": 1,
                    "in": [],
                    "out": [[item["id"], amt]],
                }
            )

    # 3c. Generator synthetic recipes
    gen_short_names = {
        "Build_GeneratorBiomass_Automated_C": "biomass",
        "Build_GeneratorCoal_C": "coal",
        "Build_GeneratorFuel_C": "fuel",
        "Build_GeneratorNuclear_C": "nuclear",
    }
    for g in gen_records:
        gcls = g["ClassName"]
        cat = class_to_slug(gcls, ("Build_",))
        gshort = gen_short_names[gcls]
        power_mw = float(g.get("mPowerProduction") or 0.0)
        fuel_load = float(g.get("mFuelLoadAmount") or 1.0)
        req_supp = g.get("mRequiresSupplementalResource") == "True"
        supp_ratio = float(g.get("mSupplementalToPowerRatio") or 0.0)

        for f in g.get("mFuel", []):
            fcls = f["mFuelClass"]
            fitem = item_by_cls[fcls]
            burn_time = (fitem["energy"] * fuel_load) / power_mw
            fuel_amt = fuel_load / 1000.0 if fitem["is_fluid"] else fuel_load
            in_ports: list[list[Any]] = [[fitem["id"], clean_num(fuel_amt)]]

            supp_cls = f.get("mSupplementalResourceClass", "")
            if req_supp and supp_cls:
                sitem = item_by_cls[supp_cls]
                supp_ml = power_mw * supp_ratio * burn_time
                supp_amt = supp_ml / 1000.0 if sitem["is_fluid"] else supp_ml
                in_ports.append([sitem["id"], clean_num(supp_amt)])

            out_ports: list[list[Any]] = []
            byp_cls = f.get("mByproduct", "")
            byp_amt_str = f.get("mByproductAmount", "")
            if byp_cls and byp_amt_str:
                bitem = item_by_cls[byp_cls]
                bamt = float(byp_amt_str)
                if bitem["is_fluid"]:
                    bamt /= 1000.0
                out_ports.append([bitem["id"], clean_num(bamt)])

            rid = register_id(
                f"burn-{gshort}-{fitem['id']}",
                f"gen:{gcls}:{fcls}",
                used_recipe_ids,
                collisions,
            )
            recipes_by_cat[cat].append(
                {
                    "id": rid,
                    "name": f"Burn {fitem['name']} ({g['mDisplayName']})",
                    "category": cat,
                    "time": clean_num(burn_time),
                    "in": in_ports,
                    "out": out_ports,
                }
            )

    # Geothermal synthetic recipe
    geo_rid = register_id("geothermal-power", "geo:power", used_recipe_ids, collisions)
    recipes_by_cat["generator-geo-thermal"].append(
        {
            "id": geo_rid,
            "name": "Geothermal Power",
            "category": "generator-geo-thermal",
            "time": 1,
            "in": [],
            "out": [["geothermal-geyser", 1]],
        }
    )

    # 3d. Space Elevator Phase 1-5 recipes
    for phase in overrides.get("space_elevator_phases", []):
        pid = register_id(phase["id"], f"se:{phase['id']}", used_recipe_ids, collisions)
        se_in = [[item_by_cls[cls]["id"], clean_num(amt)] for cls, amt in phase["in"]]
        recipes_by_cat["space-elevator"].append(
            {
                "id": pid,
                "name": phase["name"],
                "category": "space-elevator",
                "time": clean_num(phase["time"]),
                "in": se_in,
                "out": [],
                "notes": phase.get("notes", ""),
            }
        )

    # 3e. Collect all resources referenced so far, then add AWESOME Sink recipes for sinkable solid items
    referenced_res_ids: set[str] = set()
    for cat_recipes in recipes_by_cat.values():
        for rec in cat_recipes:
            for p in rec["in"] + rec["out"]:
                referenced_res_ids.add(p[0])

    item_by_id = {v["id"]: v for v in item_by_cls.values()}
    for rid in sorted(referenced_res_ids):
        if rid not in item_by_id:
            continue
        item = item_by_id[rid]
        if item["kind"] == "item" and item["sink_points"] > 0:
            srid = register_id(f"sink-{rid}", f"sink:{item['class_name']}", used_recipe_ids, collisions)
            recipes_by_cat["resource-sink"].append(
                {
                    "id": srid,
                    "name": f"Sink: {item['name']}",
                    "category": "resource-sink",
                    "time": 1,
                    "attrs": {"sink_points": item["sink_points"]},
                    "in": [[rid, 1]],
                    "out": [],
                }
            )

    # Recompute final referenced resources (all in/out across every recipe shard)
    final_referenced: set[str] = set()
    for cat_recipes in recipes_by_cat.values():
        for rec in cat_recipes:
            for p in rec["in"] + rec["out"]:
                final_referenced.add(p[0])

    # 4. Build final sorted resources list (pruning unreferenced resources for V-W-2)
    resources: list[dict[str, Any]] = []
    resource_class_map: dict[str, str] = {}
    for cls, item in item_by_cls.items():
        if item["id"] not in final_referenced:
            record_skip("unused_item_pruned", cls, item["name"])
            continue
        resources.append(
            {
                "id": item["id"],
                "name": item["name"],
                "kind": item["kind"],
                "attrs": {"is_fluid": item["is_fluid"]},
            }
        )
        resource_class_map[item["id"]] = cls

    for sid, sr in sorted(synthetic_resources.items()):
        if sid in final_referenced:
            resources.append(sr)

    resources.sort(key=lambda x: x["id"])
    machines.sort(key=lambda x: x["id"])
    for cat in recipes_by_cat:
        recipes_by_cat[cat].sort(key=lambda x: x["id"])

    # 5. Scoped cleanup & write ONLY JSON files inside out_dir (never touch icons.pak)
    out_dir.mkdir(parents=True, exist_ok=True)
    for existing in out_dir.rglob("*.json"):
        existing.unlink()

    manifest = dict(template)
    manifest["game"] = dict(template["game"])
    manifest["game"]["data_version"] = raw_version
    includes = ["resources.json", "machines.json", "recipes"]

    waivers_data = None
    if WAIVERS_PATH.exists():
        raw_waivers = WAIVERS_PATH.read_text(encoding="utf-8").strip()
        if raw_waivers:
            waivers_data = json.loads(raw_waivers)
            includes.append("waivers.json")

    manifest["include"] = includes

    dump_json(out_dir / "game.json", manifest)
    dump_json(out_dir / "resources.json", {"resources": resources})
    dump_json(out_dir / "machines.json", {"machines": machines})
    if waivers_data is not None:
        dump_json(out_dir / "waivers.json", waivers_data)

    recipe_count_by_cat: dict[str, int] = {}
    for cat in sorted(recipes_by_cat):
        recs = recipes_by_cat[cat]
        recipe_count_by_cat[cat] = len(recs)
        dump_json(out_dir / "recipes" / f"{cat}.json", {"recipes": recs})

    total_recipes = sum(recipe_count_by_cat.values())

    report = {
        "game_id": manifest["game"]["id"],
        "data_version": raw_version,
        "raw_counts": {
            "FGRecipe": len(by_nc.get("FGRecipe", [])),
            "FGCustomizationRecipe": len(by_nc.get("FGCustomizationRecipe", [])),
            "item_descriptors_total": len(item_by_cls),
        },
        "emitted_counts": {
            "resources": len(resources),
            "machines": len(machines),
            "recipes_total": total_recipes,
            "recipes_by_category": recipe_count_by_cat,
        },
        "reconciliation": {
            "FGRecipe_total": len(by_nc.get("FGRecipe", [])),
            "FGRecipe_automated_emitted": sum(
                recipe_count_by_cat[class_to_slug(c, ("Build_",))] for c in auto_producer_classes
            ),
            "FGRecipe_skipped": sum(
                skipped_counts[k]
                for k in (
                    "ficsmas_event_recipe",
                    "no_producer_legacy_recipe",
                    "buildgun_building_recipe",
                    "workshop_only_recipe",
                    "workbench_only_recipe",
                    "other_non_automated_recipe",
                    "non_positive_duration",
                    "empty_ports",
                )
            ),
        },
        "skipped_counts": dict(sorted(skipped_counts.items())),
        "skipped_samples": dict(sorted(skipped_samples.items())),
        "id_collisions": collisions,
        "merged_duplicate_ports": merged_ports,
        "icon_class_map": {
            "resources": dict(sorted(resource_class_map.items())),
            "machines": dict(sorted(machine_class_map.items())),
        },
    }
    dump_json(REPORT_PATH, report)
    print(
        f"Generated packs/satisfactory/{pkg_ver}: "
        f"{len(resources)} resources, {len(machines)} machines, {total_recipes} recipes "
        f"across {len(recipe_count_by_cat)} shards."
    )


if __name__ == "__main__":
    main()
