# Mindustry (160.8) — Factory Planner GameData v4 Pack Notes

## 1. Status
- **Current Phase:** Phase 6 — Complete & Verified (ready for in-app testing)
- **Last Verified:** 2026-11-23
  - `gamedata_tool validate packs/mindustry/160.8 --no-icons --werror --json`: **PASS** (`0` errors, `0` warnings)
  - `gamedata_tool validate packs/mindustry/160.8 --werror --json` (with `icons.pak`): **PASS** (`0` errors, `0` warnings, `41` intentional text-only option `V-W-1` waivers)
  - `gamedata_tool eval packs/mindustry/160.8 --cases converters/mindustry/cases --json`: **21/21 PASS**
  - `gamedata_tool check-icons packs/mindustry/160.8 --from .tmp_icons/mindustry/160.8 --werror --json`: **PASS** (`170` present — 100% of resources & machines, `0` missing, `41` waived text-only options, `0` invalid, `0` unreferenced, `pak_stale: false`)
  - `gamedata_tool pack-icons packs/mindustry/160.8 --from .tmp_icons/mindustry/160.8 --verify --json`: **PASS** (`170` icons, byte-verified)
  - `gamedata_tool stats packs/mindustry/160.8 --timing --repeat 5 --json`: **~39–46 ms** median total load (`125` recipes, `80` machines, `87` resources)
  - Determinism check: 2 consecutive runs of `convert.py` produced **byte-identical** SHA-256 hashes across all 9 JSON files.

## 2. Package Metadata
- **Game:** Mindustry
- **Edition / Scope:** Serpulo + Erekir unified pack (Mixtech-compatible) with Project Global picker filters (`planet`: `All (Mixtech)` / `Serpulo` / `Erekir`, and `show_debug`: `bool` default `false`). Covers crafters, separators, extractors (drills, burst drills, beam drills, wall crafters, pumps, water/oil extractors, vent condenser), power generators (fuel, thermal, solar, nuclear, impact, pyrolysis, flux, neoplasia), Erekir heat producers & consumers, unit production chains (factories, reconstructors, assemblers + required wall payload constructor recipes), and packed game sprites (`icons.pak`).
- **Exact Version:** `160.8` (`archash=7445105cd2` from `gradle.properties`)
- **Game Slug / Package Path:** `mindustry` → `packs/mindustry/160.8/`
- **Raw Dump Provenance:** Official Mindustry `160.8` Java source tree unpacked locally at `raw/mindustry/Mindustry-160.8/` (read-only, gitignored).

## 3. Authoritative References
- Local Mindustry `160.8` official Java source tree: `raw/mindustry/Mindustry-160.8/core/src/mindustry/`
  - Content definitions: `content/Items.java`, `content/Liquids.java`, `content/Blocks.java`, `content/UnitTypes.java`, `content/Planets.java`, `content/SerpuloTechTree.java`, `content/ErekirTechTree.java`
  - Simulation formulas: `entities/comp/BuildingComp.java`, `world/Block.java`, `world/meta/{Attribute,StatUnit}.java`, `world/blocks/production/*.java`, `world/blocks/power/*.java`, `world/blocks/heat/HeatProducer.java`, `world/blocks/units/*.java`, `world/blocks/payloads/{BlockProducer,Constructor}.java`, `world/blocks/defense/OverdriveProjector.java`, `world/consumers/*.java`
  - Localization: `core/assets/bundles/bundle.properties`
  - Source sprites: `core/assets-raw/sprites/{items,blocks,units}/`

## 4. Decision Log
- **Phase 1 Confirmed:**
  - Identity & paths: `Mindustry`, exact version `160.8`, `packs/mindustry/160.8/`.
  - Authoritative source: `raw/mindustry/Mindustry-160.8/core/src/mindustry/`.
  - Scope: Serpulo + Erekir unified; include extractors, power generators, heat producers/consumers, unit production chains; exclude incinerators; extract & pack authentic icons (`icons.pak`).
- **Phase 2 Confirmed (D1–D5 + Visibility + Tile Productivity):**
  - **D1 (A-ish):** Include `debugOnly` recipes (`slag-centrifuge`, `heat-reactor`, `rtg-generator-fissile-matter`) hidden from the picker via `profile.visible_if` / `profile.recipe_visible_if` controlled by Project Global `show_debug` (default `false`); add Project Global `planet` (`all` / `serpulo` / `erekir`, default `all`) filtering both machines and recipes in the picker; skip infinite `sandboxOnly` sources/voids and unused `dormant-cyst`.
  - **D2 (A):** Model Erekir Heat as a solver `resource` (`id: "heat"`, `kind: "heat"`) for automatic heater chaining; model Power as a `split_sign: true` metric (`u/s`) with a synthetic `power-marker` output (`1/s`) only on 0-port generators (`solar-panel`, `solar-panel-large`, `thermal-generator`).
  - **D3 (A) + Tile Productivity Node Options:** Node options for `overdrive` (`enum`), `boosted` (`bool` toggling conditional booster `extra_ports`), `ore_tiles_*` / `pump_tiles_*` (`int` steppers sized per machine footprint), `pump_floor` (`enum` `0.5x`/`1.0x`/`1.5x`), and `tile_preset` (`enum` of all real Mindustry `160.8` floors/walls) + `tile_efficiency` (`Custom / Mixed Tiles...` numeric `%`) across `AttributeCrafter`, `WallCrafter`, `SolidPump`, `Fracker`, and `ThermalGenerator`. Defer standalone overdrive projector/dome upkeep nodes.
  - **D4 (A):** Include `constructor` recipes for the 3 large wall payloads required by Erekir `UnitAssembler`s (`beryllium-wall-large`, `tungsten-wall-large`, `carbide-wall-large`), include `+210 u/s` `basic-assembler-module` power on Tier 1 assembler recipes (`conquer`, `disrupt`, `collaris`), and expose map-rule Project Globals (`solar_mult`, `unit_build_speed`, `unit_cost_mult`).
  - **D5 (A):** `units` = `tick` @ `60` tps, `default_rate: "s"`; `power` + `footprint` (`tiles²`) metrics (`display: ["tooltip", "totals"]`); clean canvas (all node parameters `ui.placement: "panel"`); sharded into `resources.json`, `machines.json`, `waivers.json`, `recipes/{crafting,extraction,heat,power,units}.json`; exclude explosive `blast-compound` from combustion/steam generators.
- **Post-test refinements (2026-11-23):**
  - Unified repetitive per-machine extraction and solar recipes into single multi-machine recipes with machine selection: `mine-<ore>` (9 floor ores), `bore-<ore>` (4 wall ores), `crush-sand` (2 wall crafters), `pump-<liquid>` (5 liquids across 4 pumps), and `solar-power` (both solar panels). Moved machine-specific mandatory liquids (e.g. `impact-drill` water, `eruption-drill` / `large-plasma-bore` / `large-cliff-crusher` / `reinforced-pump` hydrogen) to `xin:liquid` `extra_ports`.
  - Replaced `1/s` `power-marker` with canonical `power` resource (`kind: "power"`, `display_unit: "u"`) outputting exact generated power on `solar-power` & `thermal-generator`, and added Project Global `power_mode` (`metric` [default] / `resource` / `both`) controlling `xin:power_in`, `xout:power_out`, and `metrics.power.enabled` across all profiles via inherited `let.net_power` and `let.native_power_out`.
  - Added authentic icons for both `heat` (`raw/mindustry/heat-unit.png`) and `power` (official `Iconc.power` `\ue810` glyph rendered from `core/assets/fonts/icon.ttf` in `Pal.accent #ffd37f`), bringing resource & machine icon coverage to 100% (`87/87` resources, `80/80` machines).
  - Rewrote all UI `"tooltip"` strings to plain player-friendly language (keeping Java source file/line citations strictly in `"notes"` and this document).

## 5. Formulas & Sources Table

| Profile / Entity | Equation | Authoritative Source (`160.8`) |
|---|---|---|
| Time & rate base | `60 ticks/s`; raw liquid & power fields `× 60` for `/s` | `world/meta/StatUnit.java`, `world/blocks/production/GenericCrafter.java:70`, `world/blocks/power/PowerGenerator.java:82` |
| Picker visibility (`mindustry_base`) | `visible_if`: `(global.show_debug \|\| !machine.is_debug) && (global.planet == 'all' \|\| machine.planet == 'both' \|\| machine.planet == global.planet)`; matching `recipe_visible_if` | `content/SerpuloTechTree.java`, `content/ErekirTechTree.java`, `content/Blocks.java` |
| Overdrive (`od`) | `none=1.0`, `projector=1.5`, `projector-phase=1.5+0.75=2.25`, `dome=2.5`; scales speed, continuous liquids, and both power draw & generation; `canOverdrive=false` on `HeatProducer` & `HeaterGenerator` | `world/blocks/defense/OverdriveProjector.java:30-31,40,121`, `content/Blocks.java:1946-1961`, `entities/comp/BuildingComp.java:delta,edelta`, `world/blocks/power/PowerGraph.java:100,112`, `world/blocks/heat/HeatProducer.java:23`, `world/blocks/power/HeaterGenerator.java:22` |
| `mindustry_crafter` | `craft_time = recipe.time / (machine.speed * od)`; `power = machine.power * recipe.power_mult * od`; `footprint = ceil(max(0, node.machines - 1e-6)) * size^2` | `world/blocks/production/GenericCrafter.java:240-333`, `world/blocks/power/ConsumeGenerator.java:100-148` |
| Separators | Output port `chance = weight / sum(weights)` | `world/blocks/production/Separator.java:41-46,142-156` |
| `mindustry_attribute_crafter` | `tile_eff = (baseEfficiency + min(maxBoost, boostScale * attrsum))`; `craft_time = recipe.time / (od * tile_eff)`; `silicon-crucible` (`scales_yield=true`): `output_amount = port.amount * tile_eff`; `cultivator` water (`fixed_rate=true`): `18 * od / s` | `world/blocks/production/AttributeCrafter.java:15-27,91-111`, `content/Blocks.java:1086-1103,2963-2981`, `world/consumers/ConsumeLiquid.java:31` |
| `mindustry_heat_crafter` | `heat_eff = min(heat_pct / 100, maxEfficiency)` (`maxEfficiency=1` on all 5 vanilla blocks); `craft_time = recipe.time / (od * heat_eff)`; `xin:heat = (heat_req * heat_eff) * craft_time`; `power = machine.power * od` | `world/blocks/production/HeatCrafter.java:14-18,88-91`, `world/consumers/ConsumePower.java:46`, `content/Blocks.java` |
| `mindustry_flux_reactor` | Inherits `mindustry_heat_crafter`; `power = machine.power * heat_eff * od` (`-18000 * heat_eff * od`) | `world/blocks/power/VariableReactor.java:82,131-143`, `content/Blocks.java:2781-2787` |
| `mindustry_drill` (`Drill`, `BurstDrill`, `BeamDrill`) | `Drill`: `getDrillTime = (drillTime + 50 * hardness) / mult`, water boost `= liquidBoostIntensity^2` (`1.6^2=2.56`, `1.8^2=3.24`); `BurstDrill`/`BeamDrill`: `getDrillTime = drillTime / mult`, linear boost (`1.75`/`2.0`/`2.5`); `craft_time = time / (od * tiles * boost)`; mandatory & booster liquids fixed at `rate * od / s` | `world/blocks/production/Drill.java:28,170-188,301-305`, `BurstDrill.java:39,53-65,94-99`, `BeamDrill.java:44,216-254`, `world/consumers/ConsumeLiquid.java:31` |
| `mindustry_wall_crafter` | `craft_time = (drillTime / size) / (od * tile_eff * boost)`; `large-cliff-crusher` graphite boost `1.6x` at `0.75 * od / s`, hydrogen `1.0 * od / s` | `world/blocks/production/WallCrafter.java:45-47,81,141-215`, `content/Blocks.java:3010-3030` |
| `mindustry_pump` | `output_amount = (pumpAmount * 60) * tiles * floor_mult`; `reinforced-pump` hydrogen fixed at `1.5 * od / s` | `world/blocks/production/Pump.java:146-163`, `content/Blocks.java` liquid floors (`1.0`, `1.5`, `0.5`) |
| `mindustry_solid_pump` | `output_amount = (pumpAmount * 60) * tile_eff`; `oil-extractor` sand (`1 * od / s`) & water (`9 * od / s`) fixed | `world/blocks/production/SolidPump.java:124-127,153-159`, `world/blocks/production/Fracker.java:32-38` |
| `mindustry_solar` / `mindustry_thermal` | Solar: `power = machine.power * global.solar_mult * od`; Thermal: `power = -108 * tile_eff * od` (`tile_eff = sumAttribute(heat)`) | `world/blocks/power/SolarGenerator.java:28-33`, `world/blocks/power/ThermalGenerator.java:88`, `content/Blocks.java` |
| `thorium-reactor` / `impact-reactor` | Thorium steady-state cooled (`heat=0`): `1 thorium / 6 s`, `cryofluid = heating/coolantPower * 60 = 2.4/s`, `power = -900/s`; Impact net `power = -(130 - 25) * 60 = -6300/s`, `1 blast-compound / (140/60) s`, `15 cryofluid/s` | `world/blocks/power/NuclearReactor.java:116-134`, `world/blocks/power/ImpactReactor.java:49-53,100`, `content/Blocks.java:2635-2663` |
| `mindustry_unit` & `constructor` | Units: `craft_time = recipe.time / (od * global.unit_build_speed)`, resource inputs `× global.unit_cost_mult` (Reconstructor input unit `no_cost_scale=true`), Tier 1 assembler `+210 u/s` module power; Constructor: `buildTime = sum(amount * item.cost) * buildCostMultiplier`, `speed = 0.6` | `world/blocks/units/{UnitFactory,Reconstructor,UnitAssembler,UnitAssemblerModule}.java`, `world/blocks/payloads/BlockProducer.java:50,122`, `world/Block.java:1453-1464` |

## 6. Dependencies
- **Data converter (`convert.py`):** Python 3 standard library only (`ast`, `collections`, `json`, `math`, `operator`, `pathlib`, `re`, `sys`).
- **Icon pipeline (`build_icons.py`):** Python 3 standard library + system ImageMagick (`magick`, already installed at `/usr/bin/magick`). No `.venv` or third-party Python packages used.

## 7. Rerun Commands
```bash
# 1. Regenerate GameData v4 JSON + report.json (deterministic)
python3 converters/mindustry/convert/convert.py

# 2. Validate JSON & schema (CI / no-icons mode)
gamedata_tool validate packs/mindustry/160.8 --no-icons --werror

# 3. Run all 17 hand-verified eval regression cases
gamedata_tool eval packs/mindustry/160.8 --cases converters/mindustry/cases

# 4. Measure entity counts and load timing
gamedata_tool stats packs/mindustry/160.8 --timing --repeat 5

# 5. Extract/composite/resize authentic icons and pack icons.pak (local release step)
python3 converters/mindustry/convert/build_icons.py
gamedata_tool check-icons packs/mindustry/160.8 --from .tmp_icons/mindustry/160.8
gamedata_tool pack-icons  packs/mindustry/160.8 --from .tmp_icons/mindustry/160.8 --verify
gamedata_tool check-icons packs/mindustry/160.8 --from .tmp_icons/mindustry/160.8 --werror
gamedata_tool validate    packs/mindustry/160.8 --werror
```

## 8. Coverage, Skipped Records & Open Issues
- **Reconciliation (`report.json` ↔ `stats`):**
  - **Resources (87 emitted):** 21 items (of 22 raw; `dormant-cyst` pruned — 0 producers/consumers), 7 liquids, 4 gases, 50 buildable units (of 62 raw; 12 core/drone/neoplasm/dummy units pruned), 3 wall payloads (`beryllium-wall-large`, `tungsten-wall-large`, `carbide-wall-large`), 1 `heat`, 1 `power`.
  - **Blocks (426 raw top-level = 80 emitted machines + 346 accounted skips):**
    - `1` `large-constructor` (`constructor_no_unit_chain_payloads`)
    - `2` incinerators (`excluded_incinerator`: `incinerator`, `slag-incinerator`)
    - `1` `basic-assembler-module` (`folded_into_tier1_assembler_power`)
    - `2` overdrive blocks (`modeled_as_overdrive_param`: `overdrive-projector`, `overdrive-dome`)
    - `11` sandbox/editor blocks (`excluded_sandbox_block` + `excluded_sandbox_or_editor`: `*-source`, `*-void`, `heat-source`, `thruster`, `target-dummy`, `shield-projector`, `large-shield-projector`)
    - `329` non-production blocks (terrain floors/ores/walls/vents/props, defense walls/turrets, conveyors/conduits/payload belts, logic, storage, cores, campaign pads)
  - **Recipes (125 emitted across 5 shards):** `crafting` (26), `extraction` (22: 9 `mine-*`, 4 `bore-*`, 5 `pump-*`, `crush-sand`, `water-extractor`, `oil-extractor`, `vent-condenser`), `heat` (5), `power` (19, incl. unified `solar-power`), `units` (53). Skipped: `2` explosive fuel combinations (`combustion-generator:blast-compound`, `steam-generator:blast-compound` — trigger `ConsumeItemExplode`).
  - **Icon Provenance (211 referenced):** **170 authentic game icons** (`87/87` resources incl. `raw/mindustry/heat-unit.png` and `Iconc.power` `\ue810` from `icon.ttf` in `Pal.accent`, `80/80` multi-layer composited machines, `3` `overdrive_tiers` options) + **41 waived text-only dropdown options** (`planets/*`, `power_modes/*`, `pump_floors/*`, `tile_presets/*`, `overdrive_tiers/none`) + **0 fabricated icons**.
- **Known Limitations / Deferred Mechanics:**
  - Standalone `overdrive-projector` / `overdrive-dome` upkeep nodes deferred (modeled via per-node `overdrive` parameter).
  - `thorium-reactor` models safe steady-state cooled operation (`heat = 0`, 0 heat output); intentional undercooling for Mixtech heat output is non-linear/meltdown-prone and deferred.
  - Erekir ambient `Attribute.heat.env() = 0.8` (`Planets.java:72`) is not auto-added for Serpulo heat-attribute blocks placed in Mixtech; users can enter any custom mixed/ambient efficiency `%` via `tile_preset = Custom / Mixed Tiles...`.
  - Because Erekir `heat` is modeled as a solver resource at `/s` scale, switching the project display rate unit away from `/s` (e.g. to `/min`) scales displayed Heat numbers by 60×.
