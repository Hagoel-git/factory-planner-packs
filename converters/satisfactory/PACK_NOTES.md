# Satisfactory GameData v4 Pack Notes

## 1. Status

- **Current Phase:** Phase 6 — Handover (complete).
- **Last Verified:** `gamedata_tool 0.1 (schema_version 4)`:
  - `validate --no-icons --werror`: `0` errors, `0` warnings (CI parity).
  - `validate --werror` (with `icons.pak`): `0` errors, `0` warnings.
  - `eval --cases`: `16 / 16` cases PASS.
  - `check-icons --werror` & `pack-icons --verify`: `186 / 186` icons verified in local `icons.pak` (`24` `options/*_mults/*` intentionally waived via `waivers.json`).
  - Determinism: two consecutive runs of `convert.py` produce byte-identical JSON across all 26 files.

---

## 2. Package Metadata

- **Game:** Satisfactory
- **Edition:** Vanilla / Standard (non-FICSMAS)
- **Exact Game Version:** `v1.2.4.0` (from `raw/satisfactory/game_version`)
- **Game Slug / Package Path:** `satisfactory` / `packs/satisfactory/1.2.4.0/`
- **Raw Dump Origin:** `raw/satisfactory/en-US.json` (10,640,180 bytes, UTF-16LE Unreal Engine `Docs.json`, 114 `NativeClass` entries).

---

## 3. Authoritative References

- **Raw Docs Dump:** `raw/satisfactory/en-US.json` (`v1.2.4.0`)
- **Official Wiki:** `https://satisfactory.wiki.gg/`
  - `/wiki/Clock_speed`
  - `/wiki/Production_amplifier`
  - `/wiki/Particle_Accelerator`, `/wiki/Converter`, `/wiki/Quantum_Encoder`
  - `/wiki/Miner`, `/wiki/Oil_Extractor`, `/wiki/Water_Extractor`, `/wiki/Resource_Well_Pressurizer`
  - `/wiki/Coal-Powered_Generator`, `/wiki/Fuel-Powered_Generator`, `/wiki/Nuclear_Power_Plant`, `/wiki/Geothermal_Generator`
  - `/wiki/AWESOME_Sink`
  - `/wiki/Space_Elevator`
- **Icons Source Guide:** `raw/satisfactory/icons` (SFTools public API `https://api.new.satisfactorytools.com`)

---

## 4. Decision Log

- **Phase 1 Scope Confirmation:**
  - Target `satisfactory` / `1.2.4.0` (`packs/satisfactory/1.2.4.0/`).
  - Include all standard + alternate manufacturer recipes (`276` non-FICSMAS automated recipes).
  - Exclude FICSMAS (`28` recipes: `25` with `EV_Christmas` plus `3` Fireworks recipes under `/Events/Christmas/` unlocked by `Ficsmas_Schematic_Fireworks_C`, and `Build_TreeGiftProducer_C`), Equipment Workshop–only (`21`), BuildGun (`542`), `FGCustomizationRecipe` (`106`), unassigned legacy `<NONE>` (`5`), and Alien Power Augmenter (`Build_AlienPowerBuilding_C`).
  - Include Extractors, Power Generators (including Geothermal Generator), AWESOME Sink, and Space Elevator Phase 1–5 deliverable recipes.
- **D1 (A) — Units, Fluid Scale, IDs, Sharding:** `recipe_time: "s"`, `default_rate: "min"`. Fluids (`RF_LIQUID`) and gases (`RF_GAS`) converted from raw `mL` (`1/1000 m³`) to `m³` in the converter (`display_scale: 1`, `display_unit: "m³"`). Clean kebab-case IDs derived deterministically from Unreal `ClassName` (never display names). Sharded into `game.json`, `resources.json`, `machines.json`, and 22 `recipes/<category>.json` files.
- **D2 (A) — AWESOME Sink Modeling:** Per-item sink recipes (`sink-<item-id>` in `recipes/resource-sink.json`, `in: [[item, 1]]`, `out: []`, `attrs: { sink_points }`) for all `120` sinkable solid items referenced by factory recipes (`mResourceSinkPoints > 0`), with `belt_tier` (`mk1`–`mk6`, default `mk6` = `1200/min`).
- **D3 (A + Geothermal) — Resource Wells & Geothermal:**
  - Resource Well Extractor modeled per satellite node with `purity` (`impure`/`normal`/`pure`), `clock` (`1`–`250%`), and `well_nodes` (default `6`, panel) splitting the Pressurizer's `150 MW` across connected satellite extractors for average `power`, and rounding `ceil(node.machines / param.well_nodes)` Pressurizers for `peak_power` and `shards`.
  - Geothermal Generator included with synthetic `geothermal-geyser` resource (`V-NUM-4` requires ≥ 1 port) + `purity` parameter (`100` / `200` / `400 MW` average).
- **D4 (A) — Metrics:** `power` (average MW, `split_sign: true`, tooltip/totals — kept off node cards for clean graphs), `peak_power` (worst-case integer machine count `ceil(max(0, node.machines - 1e-6)) * peak_pwr`, tooltip/totals), `shards` (tooltip/totals), `sloops` (tooltip/totals), `sink_points` (pts/min via `is_rate: true`, body/tooltip/totals on AWESOME Sink), plus `completion_time_min` and `completion_time_h` (`aggregate: "max"`, body/tooltip on Space Elevator).
- **D5 (A) — Exponent & Icons:** Per-machine `machine.power_exp` (`1.321929` from `en-US.json`). Downloaded 183 64×64 PNGs via SFTools API (`Desc_*_C` lookup for buildings/belts, `Build_GeneratorGeoThermal_C` fallback for `geothermal-geyser`) plus 3 locally generated 64×64 badge PNGs for `node_purity` (`impure`/`normal`/`pure`) into `.tmp_icons/satisfactory/1.2.4.0/` and packed local `icons.pak` (`186` icons; git remains text-only). The `24` `options/*_mults/*` project-global options are intentionally icon-less and waived via `template/waivers.json` → `packs/satisfactory/1.2.4.0/waivers.json`.
- **Phase 2 Refinements (User-Verified In-Game):**
  - `peak_power` (plus `shards` and `sloops`) uses `ceil(max(0, node.machines - 1e-6))` across all power-consuming profiles (`ceil(max(0, node.machines / param.well_nodes - 1e-6))` on Resource Wells) with a `1e-6` LP-epsilon guard.
  - Packager (`sf_packager`) is exempt from `global.recipe_cost_mult` (`input_amount: "port.amount * port.chance"`), preventing fluid/canister duplication.
  - **UI & Globals Refinements:** Moved all node parameters (`clock`, `somersloops`, `purity`, `well_nodes`, `belt_tier`) to `ui.placement: "panel"` and removed `power` from node `body` display so graph cards only show high-signal outputs (`sink_points` on Sinks, `completion_time` on Space Elevator). Converted all 3 Satisfactory 1.2 globals (`space_elevator_cost_mult`, `recipe_cost_mult`, `power_consumption_mult`) to `enum` dropdowns matching exact in-game presets (`option_sets`: `space_elevator_cost_mults`, `recipe_cost_mults`, `power_consumption_mults`). Updated `sf_sink` `power` to `value: "ceil(max(0, node.machines - 1e-6)) * pwr"` so active physical Sinks draw `30 MW` per Sink regardless of `belt_tier` utilization.

---

## 5. Formulas & Sources Table

| Profile / Entity | Formula / Values | Authoritative Source & Version |
|---|---|---|
| `sf_production` (`craft_time`) | `recipe.time / (machine.speed * (param.clock / 100))` | `en-US.json` (`v1.2.4.0`); `satisfactory.wiki.gg/wiki/Clock_speed` |
| `sf_production` (`input_amount`) | Solid: `max(1, round(port.amount * global.recipe_cost_mult)) * port.chance`<br>Fluid/Gas: `max(0.001, round(port.amount * 1000 * global.recipe_cost_mult) / 1000) * port.chance` | Satisfactory 1.2 Game Modes (`Recipe Parts Cost Multiplier`, `v1.2.4.0`); `satisfactory.wiki.gg/` |
| `sf_packager` (`input_amount`) | `port.amount * port.chance` (exempt from `recipe_cost_mult`) | In-game verification (`Satisfactory v1.2.4.0`) |
| `sf_production` (`output_amount`) | `port.amount * port.chance * (1 + param.somersloops / machine.somersloop_slots)` | `satisfactory.wiki.gg/wiki/Production_amplifier` (`v1.2.4.0`) |
| `sf_production` (`power`, `peak_power`) | `pwr = machine.power * amp^2 * c^machine.power_exp * global.power_consumption_mult`<br>`power = pwr * node.machines`; `peak_power = ceil(max(0, node.machines - 1e-6)) * pwr` | `en-US.json` (`v1.2.4.0`); `satisfactory.wiki.gg/wiki/Clock_speed`, `/wiki/Production_amplifier` |
| `sf_production` (`shards`, `sloops`) | `ceil(max(0, node.machines - 1e-6)) * clamp(ceil((param.clock - 100) / 50), 0, 3)`; `ceil(max(0, node.machines - 1e-6)) * param.somersloops` | `satisfactory.wiki.gg/wiki/Clock_speed`, `/wiki/Production_amplifier` (`v1.2.4.0`) |
| `sf_variable_power` (`power`, `peak_power`) | `scale = amp^2 * c^machine.power_exp * global.power_consumption_mult`<br>`power = (recipe.min_power + recipe.power_span / 2) * scale * node.machines`<br>`peak_power = ceil(max(0, node.machines - 1e-6)) * (recipe.min_power + recipe.power_span) * scale` | `en-US.json` (`mVariablePowerConsumptionConstant`, `mVariablePowerConsumptionFactor`, `v1.2.4.0`); `satisfactory.wiki.gg/wiki/Particle_Accelerator`, `/wiki/Converter`, `/wiki/Quantum_Encoder` |
| `sf_extractor` (`craft_time`, `power`, `peak_power`) | `recipe.time / (machine.speed * param.purity.mult * c)`; `pwr = machine.power * c^machine.power_exp * global.power_consumption_mult`; `peak_power = ceil(max(0, node.machines - 1e-6)) * pwr` | `en-US.json` (`mExtractCycleTime`, `mItemsPerCycle`, `v1.2.4.0`); `satisfactory.wiki.gg/wiki/Miner`, `/wiki/Oil_Extractor` |
| `sf_water_extractor` | `recipe.time / (machine.speed * c)`; `pwr = machine.power * c^machine.power_exp * global.power_consumption_mult`; `peak_power = ceil(max(0, node.machines - 1e-6)) * pwr` | `en-US.json` (`Build_WaterPump_C`, `v1.2.4.0`); `satisfactory.wiki.gg/wiki/Water_Extractor` |
| `sf_resource_well` | `recipe.time / (machine.speed * param.purity.mult * c)`; `pwr_pressurizer = 150 * c^machine.power_exp * global.power_consumption_mult`; `power = (pwr_pressurizer / param.well_nodes) * node.machines`; `peak_power = ceil(max(0, node.machines / param.well_nodes - 1e-6)) * pwr_pressurizer`; `shards = ceil(max(0, node.machines / param.well_nodes - 1e-6)) * shards_per_pressurizer` | `en-US.json` (`Build_FrackingSmasher_C` 150 MW, `Build_FrackingExtractor_C`, `v1.2.4.0`); `satisfactory.wiki.gg/wiki/Resource_Well_Pressurizer` |
| `sf_generator` | `craft_time = recipe.time / (machine.speed * c)`; `power = -machine.power * c` (linear for Biomass, Coal, Fuel, and Nuclear) | `en-US.json` (`mPowerProduction`, `mEnergyValue`, `mFuelLoadAmount`, `mSupplementalToPowerRatio`, `mFuel[]`, `v1.2.4.0`); `satisfactory.wiki.gg/wiki/Clock_speed`, `/wiki/Nuclear_Power_Plant` |
| `sf_geothermal` | `power = -200 * param.purity.mult` (Impure 100 MW, Normal 200 MW, Pure 400 MW average) | `en-US.json` (`Build_GeneratorGeoThermal_C`, `mVariablePowerProductionFactor = 200`, `v1.2.4.0`); `satisfactory.wiki.gg/wiki/Geothermal_Generator` |
| `sf_sink` | `craft_time = 60 / param.belt_tier.rate_per_min`; `pwr = 30 * global.power_consumption_mult`; `power = peak_power = ceil(max(0, node.machines - 1e-6)) * pwr`; `sink_points = recipe.sink_points` per craft | `en-US.json` (`Build_ResourceSink_C`, `FGBuildableConveyorBelt.mSpeed / 2`, `mResourceSinkPoints`, `v1.2.4.0`); `satisfactory.wiki.gg/wiki/AWESOME_Sink` |
| `sf_space_elevator` | `input_amount = max(1, round(port.amount * global.space_elevator_cost_mult))`<br>`completion_time_min = 1 / (node.crafts * 60)`<br>`completion_time_h = 1 / (node.crafts * 3600)` | `satisfactory.wiki.gg/wiki/Space_Elevator` (`v1.2.4.0`); Satisfactory 1.2 `Space Elevator Deliverable Cost Multiplier` |

---

## 6. Dependencies

- Python 3 standard library only (`json`, `re`, `struct`, `zlib`, `pathlib`, `urllib.request`, `concurrent.futures`, `collections`). No `.venv` or third-party packages required.

---

## 7. Rerun Commands

```bash
# 1. Regenerate GameData v4 JSON from raw/satisfactory/en-US.json
python3 converters/satisfactory/convert/convert.py

# 2. Strict schema validation (no icons, matches CI)
gamedata_tool validate packs/satisfactory/1.2.4.0 --no-icons --werror --timing

# 3. Regression eval suite (16 hand-checked cases)
gamedata_tool eval packs/satisfactory/1.2.4.0 --cases converters/satisfactory/cases

# 4. Stats & load timing benchmark
gamedata_tool stats packs/satisfactory/1.2.4.0 --timing --repeat 5

# 5. Optional local icon fetch & pack (never commit .tmp_icons/ or icons.pak)
python3 converters/satisfactory/convert/fetch_icons.py
gamedata_tool check-icons packs/satisfactory/1.2.4.0 --from .tmp_icons/satisfactory/1.2.4.0 --werror
gamedata_tool pack-icons  packs/satisfactory/1.2.4.0 --from .tmp_icons/satisfactory/1.2.4.0 --verify
gamedata_tool validate    packs/satisfactory/1.2.4.0 --werror
```

---

## 8. Coverage, Skipped Records & Open Issues

### Entity & Recipe Reconciliation (`report.json` ↔ `gamedata_tool stats`)

- **Resources emitted:** `153` (`152` from `en-US.json` + `1` synthetic `geothermal-geyser`; `43` unreferenced raw descriptors pruned for `V-W-2`).
- **Machines emitted:** `24` (8 fixed-power manufacturers, 3 variable-power manufacturers, 3 miners, 1 oil extractor, 1 water extractor, 1 resource well extractor absorbing Pressurizer power, 4 fuel/nuclear generators, 1 geothermal generator, 1 AWESOME Sink, 1 Space Elevator).
- **Recipes emitted:** `434` across `22` category shards:
  - `276` automated `FGRecipe` entries
  - `10` Miner recipes + `1` Oil Extractor + `1` Water Extractor + `3` Resource Well Extractor recipes (`15` extraction recipes)
  - `17` Fuel/Nuclear generator recipes + `1` Geothermal synthetic recipe (`18` generator recipes)
  - `5` Space Elevator Phase 1–5 recipes
  - `120` AWESOME Sink recipes (every referenced sinkable solid item)
- **`FGRecipe` reconciliation (`872` raw total):** `276` emitted + `596` skipped (`542` BuildGun, `28` FICSMAS/event including `3` Fireworks recipes lacking `mRelevantEvents`, `21` Workshop-only, `5` unassigned legacy `<NONE>`).
- **Other skipped raw records:** `106` `FGCustomizationRecipe`, `1` `Build_TreeGiftProducer_C` (FICSMAS Gift Tree), `1` `Build_FrackingSmasher_C` (merged into Resource Well Extractor), `1` `Build_AlienPowerBuilding_C` (Alien Power Augmenter — global percentage grid boost cannot be represented linearly in per-node LP).
- **ID collisions:** `0`. **Merged duplicate ports:** `0`.

### Known Limitations / Open Notes

- **Smelter Somersloop Slot Override:** `en-US.json` (`v1.2.4.0`) reports `mProductionShardSlotSize = 0` on `Build_SmelterMk1_C` while setting `mCanChangeProductionBoost = True` and `mProductionShardBoostMultiplier = 1.0`. Overridden to `1` slot in `template/overrides.json` per `satisfactory.wiki.gg/wiki/Smelter`.
- **Geothermal Generator (`V-NUM-4`):** Uses synthetic `geothermal-geyser` output port (`out: [["geothermal-geyser", 1]]`) so standalone nodes report `-100 / -200 / -400 MW` without needing upstream inputs.
- **Alien Power Augmenter (`Build_AlienPowerBuilding_C`):** Excluded because a flat `+10%` / `+30%` global power-grid percentage multiplier across the whole factory is non-linear in GameData v4.
- **Recipe Parts Cost Multiplier Quirks:** `sf_production` and `sf_variable_power` apply `round` to solid inputs (`≥ 1`) and mL-precision rounding to fluids/gases (`≥ 0.001 m³`), while `sf_packager` skips `recipe_cost_mult`.
