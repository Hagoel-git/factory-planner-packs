# Factorio (2.1.25) — Factory Planner GameData v4 Pack Notes

## 1. Status
- **Current Phase:** Phase 6 — Complete & Verified (ready for in-app testing)
- **Phase 2 Planning Roadmap:**
  - [x] **Round 1:** Scope, Surface/Planet Picker Filters, Recycling & Special Subsystems (v1 vs Deferred v2+)
  - [x] **Round 2:** Recipe Unification, Multi-Category Crafters & Extractors (including drag-connect UX)
  - [x] **Round 3:** Modules, Beacons, Quality & Productivity Math
  - [x] **Round 4:** Power, Burner Fuels, Steam Temperatures, Heat, Nuclear, Fusion & Solar
  - [x] **Round 5:** Infinite Research Project Globals, Labs & Rocket Silos
  - [x] **Round 6:** Metrics, Canvas UX, Sharding & Icon Plan
  - [x] **Stage 2C:** Consolidated Pack Blueprint sign-off & `template/game.json` smoke-test
- **Last Verified:** 2026-11-24 (updated for rebuilt `gamedata_tool` schema additions: `rate_invariant`, split-sign labels, plain SI `MW` unit, and option tooltips)
  - `gamedata_tool validate packs/factorio/2.1.25 --no-icons --werror --json`: **PASS** (`0` errors, `0` warnings)
  - `gamedata_tool validate packs/factorio/2.1.25 --werror --json` (with `icons.pak`): **PASS** (`0` errors, `0` warnings, `20` intentional text-only option `V-W-1` waivers)
  - `gamedata_tool eval packs/factorio/2.1.25 --cases converters/factorio/cases --json`: **25/25 PASS**
  - `rate_invariant` `--rate min` verification (`gamedata_tool eval --rate min`): `solar-panel` (`0.042 MW`), `nuclear-reactor` (`120 MW` heat, `0.3` cells/min), `heating-tower` (`40 MW` heat, `240` coal/min), `heat-exchanger` (`10 MW` heat, `618.56` water/min → `6185.57` steam/min), `coal-liquefaction` `power_mode=resource` (`0.434 MW` power_in), `steam-turbine` `power_mode=both` (`5.82 MW` power_out, `3600` steam/min) — **all PASS**
  - `gamedata_tool check-icons packs/factorio/2.1.25 --from .tmp_icons/factorio/2.1.25 --werror --json`: **PASS** (`377` present — 100% of resources & machines + all visual option sets, `0` missing, `20` waived text-only options, `0` invalid, `0` unreferenced, `0` case mismatches, `pak_stale: false`)
  - `gamedata_tool pack-icons packs/factorio/2.1.25 --from .tmp_icons/factorio/2.1.25 --verify --json`: **PASS** (`377` icons, `3,148,546` bytes, byte-verified)
  - `gamedata_tool stats packs/factorio/2.1.25 --timing --repeat 5 --json`: **~130–140 ms** median total load (`13` files; `308` resources, `35` machines, `651` recipes)
  - Parameter sweeps verified: `boiler-steam-165c` (`quality` → `30 / 39 / 48 / 57 / 75 /min` pollution), `solar-power` (`solar_location` → all 11 planet surfaces + space orbits), `research` (`research_preset` → all 9 presets + `custom` pack toggles), `electronic-circuit` (`beacon_quality` → `1.5×` to `2.5×`).
  - Determinism check: 2 consecutive runs of `convert.py` produced **byte-identical** SHA-256 hashes across all `13` JSON files.

## 2. Package Metadata
- **Game:** Factorio (Space Age + Quality + Elevated Rails)
- **Exact Version:** `2.1.25`
- **Game Slug / Package Path:** `factorio` → `packs/factorio/2.1.25/`
- **Raw Dump Provenance:** Factorio `2.1.25` CLI `--dump-data`, `--dump-icon-sprites`, and `--dump-prototype-locale` output under `raw/factorio/2.1.25/script-output/` (read-only, gitignored).

## 3. Authoritative References
- **Primary (exact `2.1.25` schema, defaults & engine behavior):**
  - `raw/factorio/2.1.25/prototype-api.json` (`factorio 2.1.25`, API v6, stage `prototype`)
  - `raw/factorio/2.1.25/runtime-api.json` (`factorio 2.1.25`, API v6, stage `runtime`)
  - `raw/factorio/2.1.25/script-output/data-raw-dump.json` + `*-locale.json` (exact `2.1.25` prototype constants & English names)
- **Secondary (gameplay math formulas):**
  - Official Factorio Wiki: `https://wiki.factorio.com/` (recorded in `raw/factorio/2.1.25/factorio-wiki`)
- **In-Game `2.1.25` Spot-Checks (user-confirmed):**
  - Pumpjack rates: `fluorine-vent` `1/s` at 100% yield (`3.9/s` at 300% + 30% Mining Prod), finite `lithium-brine` flat `1/s` (`1.3/s` at +30% Mining Prod), `crude-oil` & `sulfuric-acid-geyser` `10/s` at 100% yield (20% min floor).
  - Fusion reactor electric draw: Legendary `fusion-reactor` draws fixed `10 MW` (does not scale with quality).

## 4. Decision Log
- **Phase 1 Confirmed:**
  - Identity & paths: `Factorio`, exact version `2.1.25`, slug `factorio`, package path `packs/factorio/2.1.25/`.
  - Authoritative references: `prototype-api.json`, `runtime-api.json`, `data-raw-dump.json` (primary), `https://wiki.factorio.com/` (secondary).
- **Phase 2 — Round 1 Confirmed (Scope, Picker Filters, Recycling & Special Subsystems):**
  - **Standard Defaults:** Hard-exclude `parameter-*`, `*-unknown`, 8 hidden debug/creative recipes (`pistol`, 4× `loader`, `infinity-chest`, `infinity-pipe`, `heat-interface`), and hidden `burner-generator` / `electric-energy-interface`. Defer 5-tier item-quality cascades and belt-transit spoilage freshness decay (GameData v4 non-goals).
  - **D1 (A):** Project Global `surface` (`All` [default], `Nauvis`, `Vulcanus`, `Gleba`, `Fulgora`, `Aquilo`, `Space platform`) with authentic icons, acting strictly as a picker filter via `visible_if` / `recipe_visible_if`.
  - **D2 (A):** Include `280` gameplay `*-recycling` recipes (excluding hidden/blueprint/tool/debug items), hidden by default behind Project Global `show_recycling` (`bool`, default `false`); `scrap-recycling` is always visible.
  - **D3 (A):** Passive `"Spoiling"` machine (`0 MW`, `0` pollution) with `10` deterministic `spoil_result` recipes (`iron-bacteria -> iron-ore`, `copper-bacteria -> copper-ore`, and `8` `-> spoilage` items using raw `spoil_ticks / 60`).
  - **D4 (A):** Defer `asteroid-collector` to v2+; treat the 4 asteroid chunks as raw inputs.
  - **D5 (A):** Defer `thruster`, `lightning-rod`, and `lightning-collector` to v2+ (keep `thruster-fuel` and `thruster-oxidizer` recipes in v1).
  - **D6 (B, decoupled from `global.surface` in Round 4):** Per-node `aquilo_heating` `bool` checkbox (visible when `machine.heating_energy > 0`, default `false`) enabling a separate read-only post-solve thermal thaw heat metric (`MW`, SI auto-scaled), clearly distinct from electrical power.
- **Phase 2 — Round 2 Confirmed (Recipe Unification, Multi-Category Crafters & Extractors):**
  - **Standard Defaults:** Planet availability from `planet.<name>.map_gen_settings`; Offshore Pump (`1200/s` base, void energy, 4 tile fluids); Uranium mining consumes `1 sulfuric-acid` per base craft (unaffected by mining prod; `burner-mining-drill` excluded for lack of `input_fluid_box`).
  - **D7 (A):** Keep 1 logical recipe per Factorio multi-category recipe using explicit `"machines": [...]` across all compatible crafters.
  - **D8 (A):** Unified solid ore mining recipes (`8` recipes total, ordered `electric-mining-drill` first so newly dragged nodes avoid Burner fuel surprises; `uranium-ore` Electric/Big only; `tungsten-ore` Big only).
  - **D9 (A, confirmed in-game on `2.1.25`):** `patch_yield` `%` parameter (default `100`, min `20`) shown only on the 3 infinite fluid vents (`crude-oil` `10/s`, `sulfuric-acid-geyser` `10/s`, `fluorine-vent` `1/s` at 100%); hidden on finite `lithium-brine` (flat `1/s`).
  - **D10 (A):** Agricultural Tower models 1 seed → harvest (`50` fruit in `300 s` / `4` wood in `600 s`) scaled by `agri_plots` `int` (`1..48`, default `47`).
  - **D11 (A):** Mining drill resource drain (`big-mining-drill` 50% + quality drain multiplier) does not affect ore/s throughput; omit patch-depletion metric.
- **Phase 2 — Round 3 Confirmed (Modules, Beacons, Quality & Productivity Math):**
  - **Standard Defaults:** Module/beacon eligibility from `data-raw-dump.json` (`allowed_effects`, `effect_receiver`, `allow_productivity`, `allow_quality`); `EffectReceiver` `-80%` floors & `+300%` crafting productivity cap; innate `+50%` productivity on Foundry/EM Plant/Biochamber applies to all their recipes; catalyst `ignored_by_productivity` (defaulting to `ignored_by_stats`); `independent_probability`, `shared_probability` (`max - min`), and `extra_count_fraction` expected-value mapping.
  - **D12 (A):** Building `quality` `enum` (`normal`..`legendary`, official `quality/` icons) scaling machine speed/throughput by `1 + 0.3 × level` (`1.0 / 1.3 / 1.6 / 1.9 / 2.5`).
  - **D13 (A):** Compact `modules` `option_set` (12 module items) + `module_quality` `enum` scaling positive/beneficial module stats by `1 + 0.3 × level` (penalties unscaled via split positive/negative module attrs).
  - **D14 (B):** Include Quality Modules 1–3 (gated by `machine.allows_quality && recipe.allows_quality`) for their `-5%` speed penalty and tooltip `quality_chance` (`%`) readout (including Speed Module negative quality penalty via beacons).
  - **D15 (A):** Exact raw 100-entry `beacon_profile` table (`n * beacon_eff * lookup('beacon_profile', n - 1)`) with `beacon_count` (`0..32`), `beacon_modules` (2 slots), `beacon_quality` (`1.5 + 0.2 × level`), and independent `beacon_module_quality`.
  - **D16 (A):** Exclude beacon electrical power draw from per-node `power`.
- **Phase 2 — Round 4 Confirmed (Power, Burner Fuels, Steam, Heat, Nuclear, Fusion & Solar):**
  - **Standard Defaults:** `chemical` fuel `resource_choice` (16 fuels, default `coal`); single-fuel burners bound directly (`biochamber` → `nutrients`, `captive-biter-spawner` → `bioflux`, `nuclear-reactor` → `uranium-fuel-cell` + `depleted-uranium-fuel-cell`, `fusion-reactor` → `fusion-power-cell`); water/steam 1:10 expansion, `boiler`, `heat-exchanger`, `steam-engine`, `steam-turbine`, `heating-tower` (`250%` efficiency), `nuclear-reactor` (`reactor_neighbors` `0..4`).
  - **D17 (A):** Include electric idle `drain` (`energy_usage / 30` on electric `CraftingMachinePrototype`s; `0` auto-drain on drills/labs) in per-machine electric power.
  - **D18 (A):** Split steam into `steam-165c` and `steam-500c`; `steam-turbine` supports both (`5.82 MW` vs `1.80 MW`); port-bound `steam_temp_165` (`coal-liquefaction`) and `steam_temp_500` (`steam-condensation`).
  - **D19 (A, updated with `rate_invariant`):** Thermal heat modeled as solver resource `heat` (`kind: "heat"`, `display_unit: "MW"`, `rate_invariant: true`) linking `nuclear-reactor` & `heating-tower` to `heat-exchanger` with consistent MW display and SI auto-scaling across all rate units.
  - **D20 (A, confirmed in-game on `2.1.25`):** `fusion-reactor` (fixed `10 MW` electric draw, unscaled by quality) + `fusion-generator` (`fusion_neighbors` labeled `"Reactor neighbors"` `0..5` on generator only so reactor↔generator mismatch is impossible while conserving fluoroketone 1:1 across qualities).
  - **D21 (A, decoupled from `global.surface`):** `solar-panel` outputs typed `power` (`MW`) with always-visible per-node `solar_location` `enum` (5 planet surfaces + 6 space orbits, default Nauvis surface `42 kW`).
  - **D22 (A):** Project Global `power_mode` (`Metric only` [default], `Resource (solver)`, `Both`) toggling `xin:power_in` / `xout:power_out` and `metrics.power.enabled` (with `native_power_out = true` on `fa_solar`).
- **Phase 2 — Round 5 Confirmed (Infinite Research Project Globals, Labs & Rocket Silos):**
  - **Standard Defaults:** `mining_productivity` (uncapped `+10%`/lvl), `research_productivity` (uncapped `+10%`/lvl), `research_speed` levels 0–6 (multiplicative with lab modules/beacons); `lab` (`1×`, `60 kW`, 2 slots, `100%` drain) and `biolab` (`2×`, `300 kW`, 4 slots, `50%` drain, Nauvis-only, `8/min` pollution, no quality modules).
  - **D23 (A):** Expose all 8 infinite recipe-productivity techs (`steel`, `lds`, `plastic`, `processing-unit`, `rocket-fuel`, `rocket-part`, `scrap-recycling`, `asteroid`) as `int` Project Globals (`0..30`, grouped under `"Recipe Productivity"`), capped at `+300%` total recipe productivity.
  - **D24 (A):** 1 unified `"Research"` recipe (`lab` / `biolab` → `science` / eSPM) with `research_preset` `enum` + `Custom...` revealing `research_cycle_time` and 12 science-pack `bool` toggles.
  - **D25 (A):** Keep raw `rocket-part` recipe in `rocket-silo` (`50` parts = 1 rocket).
- **Phase 2 — Round 6 & Blueprint Sign-Off Confirmed:**
  - **D26 (B, updated for new schema fields):** 6 metrics: `power` (Electric power, `MW`, `split_sign`), `aquilo_heating` (Aquilo thaw heat, plain `MW` for SI auto-scaling, whole-building `value`), `pollution` (`/min`, `split_sign`, `positive_label: "Emitted"`, `negative_label: "Absorbed"`), `spores` (`/min`), `modules_count` (whole-building `value`), `quality_chance` (`%`, tooltip-only).
  - **D27 (A):** Place ONLY `modules` (`slot_row`, auto-hidden on 0-slot machines) on node `"body"`; all other parameters in `"panel"`.
  - **D28 (A):** Per-node `aquilo_heating` `bool` checkbox (`panel`) activating read-only `aquilo_heating` metric.
  - **D29 (A):** `units.default_rate: "s"` (`recipe_time: "s"`).
  - **Sign-Off & Post-Handover Refinements (2026-11-24):**
    - `"Reactor neighbors"` label on `fa_fusion_generator`; per-tree harvest spore emissions (`15` spores/harvest on Yumako & Jellystem → `3 * agri_plots / min`, `0` on Nauvis trees) added to Agricultural Tower's `4/min`; confirmed pollution scaling `base * energy_mult * pol_mult * fuel_emissions_mult` (including Biochamber negative pollution) and Boiler quality pollution scaling (`30 × q_mult / min` → `30 / 39 / 48 / 57 / 75`). Note on `agricultural-tower` power: `0.1 MW/tower` reflects active `energy_usage` (`100 kW`; crane also peaks `100 kW` while moving, `0 kW` idle waiting for growth).
    - Upgraded pack for GameData v4 schema additions: `rate_invariant: true` on `resource_kinds.power` (`MW`) and `resource_kinds.heat` (`MW`, changed from `MJ`), `positive_label: "Emitted"` / `negative_label: "Absorbed"` on `metrics.pollution`, plain `"MW"` on `metrics.aquilo_heating` for SI auto-scaling, dynamically generated `option_sets.modules` `"tooltip"` strings from `data-raw-dump.json` (`module.<id>.effect`), and concise `"tooltip"` strings on `option_sets.qualities`.

## 5. Formulas & Sources Table

| Profile / Entity | Equation | Authoritative Source (`2.1.25`) |
|---|---|---|
| Picker visibility (`fa_base`) | `visible_if`: `global.surface == 'all' \|\| machine.on_<surface>`; `recipe_visible_if`: `(global.show_recycling \|\| !recipe.is_auto_recycling) && surface_match` | `data-raw-dump.json` (`planet`, `surface`, `surface_conditions`, `map_gen_settings`), `prototype-api.json` (`RecipePrototype.surface_conditions`) |
| Quality scaling (`qualities`) | `level ∈ {0, 1, 2, 3, 5}`; `q_mult = 1 + 0.3 * level` (`1.0, 1.3, 1.6, 1.9, 2.5`); beacon dist eff `= 1.5 + 0.2 * level` (`1.5, 1.7, 1.9, 2.1, 2.5`) | `data-raw-dump.json` (`quality`, `beacon`), `prototype-api.json` (`QualityPrototype.default_multiplier`, `BeaconPrototype`), `runtime-api.json` (`LuaEntityPrototype.get_*`) |
| Beacons (`beacon_profile`) | `bmul = if(n > 0, n * beacon_eff * lookup('beacon_profile', n - 1), 0)` using exact raw 100-entry `profile` array; transmits speed, consumption, pollution, and negative quality penalty | `data-raw-dump.json` (`beacon.profile`), `prototype-api.json` (`BeaconPrototype.profile`), `https://wiki.factorio.com/Beacon` |
| Module effects (`fa_crafter`, `fa_miner`, `fa_lab`) | Beneficial effects (`speed > 0`, `prod > 0`, `qual > 0`, `cons < 0`) scale by `mq_mult` (`bmq_mult` in beacons); penalties stay `1×`. `speed_mult = max(0.2, 1 + s)`, `energy_mult = max(0.2, 1 + e)`, `pol_mult = max(0.2, 1 + pol)` | `data-raw-dump.json` (`module`), `prototype-api.json` (`ModulePrototype.*_quality_multiplier`, `EffectReceiver`, `Effect`) |
| Crafting throughput, productivity & catalysts (`fa_crafter`) | `craft_time = recipe.time / (machine.speed * q_mult * speed_mult)`; `prod = 1 + clamp(machine.base_prod + mod_prod + tech_prod, 0, recipe.max_prod)` (`max_prod = 3.0`); `output_amount = (port.catalyst + (port.amount - port.catalyst) * prod) * port.chance` (`catalyst = min(amount, ignored_by_productivity)`, defaulting to `ignored_by_stats`) | `data-raw-dump.json` (`recipe`, `assembling-machine`, `furnace`, `rocket-silo`), `prototype-api.json` (`RecipePrototype`, `ItemProductPrototype`, `EffectReceiver`), `https://wiki.factorio.com/Electromagnetic_plant` |
| Electric power, idle drain & `power_mode` (`fa_base`, `fa_crafter`) | Electric crafters: `net_power = machine.power * energy_mult + machine.drain` (`drain = energy_usage / 30` when omitted); drills/labs: `0` auto-drain. When `power_mode != 'metric'`, `xin:power_in = net_power * craft_time`, `xout:power_out = -net_power * craft_time` (skipped when `native_power_out`) | `prototype-api.json` (`CraftingMachinePrototype.energy_source`, `ElectricEnergySource.drain`, `Effect.consumption`), `data-raw-dump.json` |
| Burner fuels (`fa_crafter`, `fa_miner`, `fa_boiler`, `fa_reactor`) | `fuel_amount = burner_power_mw * craft_time / (machine.burner_eff * fuel_mj)` (`chemical` 16 fuels, `nutrients` 2 MJ, `bioflux` 6 MJ, `uranium-fuel-cell` 8 GJ, `fusion-power-cell` 40 GJ) | `data-raw-dump.json` (`item`/`capsule` `fuel_value`, `fuel_categories`, `burnt_result`), `prototype-api.json` (`BurnerEnergySource`) |
| Pollution & Aquilo thaw heat (`fa_base`..`fa_reactor`) | `pol_rate = machine.pollution * energy_mult * pol_mult * fuel_emissions_mult` (scales negative Biochamber pollution too); Boiler/Heating Tower scale pollution by `q_mult` (`30 / 39 / 48 / 57 / 75 /min` on Boiler); `aquilo_heating = ceil(max(0, node.machines - 1e-6)) * machine.heating_energy` | `data-raw-dump.json` (`emissions_per_minute`, `heating_energy`), `prototype-api.json` (`Effect.pollution`), `https://wiki.factorio.com/Pollution` |
| Mining & Pumpjacks (`fa_miner`) | `craft_time = recipe.time / (machine.speed * speed_mult)` (no quality speed scaling); `prod = 1 + max(0, mod_prod + global.mining_productivity * 0.1)` (uncapped); `output = amount * chance * yield_mult * prod` (`yield_mult = patch_yield / 100` on infinite `crude-oil` 10/s, `sulfuric-acid-geyser` 10/s, `fluorine-vent` 1/s; `1` on finite `lithium-brine` flat 1/s — confirmed in-game on `2.1.25`). Uranium `1 sulfuric-acid` unaffected by prod | `data-raw-dump.json` (`mining-drill`, `resource`), `prototype-api.json` (`MiningDrillPrototype`, `ResourceEntityPrototype`), user in-game verification (`2.1.25`), `https://wiki.factorio.com/Mining` |
| Offshore pump (`fa_offshore`) | `1200 * q_mult / s` (`pumping_speed = 20/tick * 60`), void energy (`0 MW`) | `data-raw-dump.json` (`offshore-pump`, `tile`), `prototype-api.json` (`OffshorePumpPrototype`), `runtime-api.json` (`get_pumping_speed`) |
| Agriculture (`fa_agriculture`) | `craft_time = (growth_ticks / 60) / param.agri_plots` (default `47`, max `48`); `power = 0.1 MW` active (`0 kW` idle waiting for growth; crane peak `100 kW` while moving); `spores = 4 + harvest_spores * agri_plots * 60 / recipe.time` (`15` spores/harvest on Yumako & Jellystem → `4 + 3 * agri_plots / min`; `0` on Nauvis trees) | `data-raw-dump.json` (`agricultural-tower`, `plant`), `prototype-api.json` (`AgriculturalTowerPrototype`, `PlantPrototype`), `https://wiki.factorio.com/Agricultural_tower` |
| Boilers, Heat Exchangers & Steam Generators (`fa_boiler`, `fa_generator`) | `water` (`2 kJ/°C`, 15°C) → `steam` (`0.2 kJ/°C`, `1:10` expansion). Boiler: `1.8 * q_mult MW` fuel + `6 * q_mult` water/s → `60 * q_mult` `steam-165c`/s (`30 * q_mult / min` pollution). Heat Exchanger: `10 * q_mult MW` heat + `10.30928 * q_mult` water/s → `103.0928 * q_mult` `steam-500c`/s. Steam Engine: `30 * q_mult` `steam-165c`/s → `-0.9 * q_mult MW`. Steam Turbine: `60 * q_mult` `steam-500c`/s → `-5.82 * q_mult MW` (`165°C` → `-1.80 * q_mult MW`) | `data-raw-dump.json` (`boiler`, `generator`, `fluid`), `prototype-api.json` (`BoilerPrototype`, `GeneratorPrototype`), `https://wiki.factorio.com/Quality` |
| Nuclear Reactor & Heating Tower (`fa_reactor`) | Nuclear Reactor: `1` fuel cell / `(200 / q_mult)` s → `1` depleted cell + `40 * q_mult * (1 + reactor_neighbors) MW` heat (`8000 MJ` base). Heating Tower: `40 * q_mult MW` heat at `effectivity = 2.5` (`16 * q_mult MW` chemical fuel), `100 * q_mult / min` pollution | `data-raw-dump.json` (`reactor`), `prototype-api.json` (`ReactorPrototype`, `BurnerEnergySource`), `https://wiki.factorio.com/Nuclear_reactor`, `https://wiki.factorio.com/Heating_tower` |
| Fusion Reactor & Generator (`fa_fusion_reactor`, `fa_fusion_generator`) | Fusion Reactor: `1` cell / `(400 / q_mult)` s + `4 * q_mult / s` `fluoroketone-cold` → `4 * q_mult / s` `fusion-plasma`, fixed `10 MW` electric draw (unscaled by quality, confirmed in-game on `2.1.25`). Fusion Generator: `-50 * q_mult MW`, consumes `2 * q_mult / (1 + fusion_neighbors) / s` plasma → equal `fluoroketone-hot/s` (1:1 fluoroketone conservation) | `data-raw-dump.json` (`fusion-reactor`, `fusion-generator`, `fusion-plasma`), `prototype-api.json`, user in-game verification (`2.1.25`), `https://wiki.factorio.com/Fusion_reactor` |
| Solar Panel (`fa_solar`) | `out:0` (`power`, `MW`) = `-net_power = 0.06 * q_mult * solar_location.solar_mult` (planets `0.7 * solar-power / 100`; space `solar_power_in_space / 100`, default `0.01` at edge); `native_power_out = true` | `data-raw-dump.json` (`solar-panel`, `planet`, `space-location`), `prototype-api.json` (`SpaceLocationPrototype.solar_power_in_space`), `https://wiki.factorio.com/Solar_panel` |
| Labs (`fa_lab`) | `craft_time = base_cycle / (machine.speed * q_mult * (1 + global.research_speed.bonus) * speed_mult)`; `input = amount * machine.science_drain` (`1.0` Lab, `0.5` Biolab); `output = amount * (1 + max(0, mod_prod + global.research_productivity * 0.1))` (uncapped); `requires: pack_count > 0` | `data-raw-dump.json` (`lab`, `technology`), `prototype-api.json` (`LabPrototype`), `https://wiki.factorio.com/Lab` |
| Spoiling (`fa_spoiling`) | `craft_time = spoil_ticks / 60`; 1:1 `spoil_result` conversion; `0 MW`, `0` pollution | `data-raw-dump.json` (`item`/`capsule` `spoil_ticks`, `spoil_result`), `prototype-api.json` (`ItemPrototype`) |

## 6. Dependencies
- **Data converter (`convert.py`):** Python 3 standard library only (`collections`, `json`, `math`, `pathlib`, `re`, `typing`).
- **Icon stager (`build_icons.py`):** Python 3 standard library only (`json`, `pathlib`, `shutil`, `struct`). No third-party packages, no `.venv/`, no ImageMagick required (all Factorio `2.1.25` sprites are natively valid square PNGs ≤ 64×64).

## 7. Rerun Commands
```bash
# 1. Regenerate GameData v4 JSON + report.json (deterministic)
python3 converters/factorio/convert/convert.py

# 2. Validate JSON & schema (CI / no-icons mode)
gamedata_tool validate packs/factorio/2.1.25 --no-icons --werror

# 3. Run all 25 hand-verified eval regression cases
gamedata_tool eval packs/factorio/2.1.25 --cases converters/factorio/cases

# 4. Measure entity counts and load timing
gamedata_tool stats packs/factorio/2.1.25 --timing --repeat 5

# 5. Stage authentic 2.1.25 icons and pack icons.pak (local release step)
python3 converters/factorio/convert/build_icons.py
gamedata_tool check-icons packs/factorio/2.1.25 --from .tmp_icons/factorio/2.1.25
gamedata_tool pack-icons  packs/factorio/2.1.25 --from .tmp_icons/factorio/2.1.25 --verify
gamedata_tool check-icons packs/factorio/2.1.25 --from .tmp_icons/factorio/2.1.25 --werror
gamedata_tool validate    packs/factorio/2.1.25 --werror
```

## 8. Coverage, Skipped Records, Deferred Subsystems (v2+) & Open Issues
- **Reconciliation (`report.json` ↔ `gamedata_tool stats`):**
  - **Resources (`308` emitted):** `283` gameplay items (incl. `science` and all 16 chemical fuels), `21` non-steam gameplay fluids, `2` split steam fluids (`steam-165c`, `steam-500c`), `1` `heat` (`MW`, `rate_invariant: true`), `1` `power` (`MW`, `rate_invariant: true`). Pruned (`71` accounted): `1` raw unsplit `steam`, `11` unreferenced fluids (`fluid-unknown` + `parameter-0..9`), `59` unreferenced items (`parameter-0..9`, `item-unknown`, `no-item`, `empty-module-slot`, hidden creative/debug entities, free blueprint/wire/remote tools, built-in vehicle guns).
  - **Machines (`35` emitted + `8` accounted skips):** `17` crafters/furnaces/`rocket-silo`, `4` mining drills/`pumpjack`, `1` `offshore-pump`, `1` `agricultural-tower`, `2` `boiler`/`heat-exchanger`, `2` `steam-engine`/`steam-turbine`, `2` `nuclear-reactor`/`heating-tower`, `2` `fusion-reactor`/`fusion-generator`, `1` `solar-panel`, `2` `lab`/`biolab`, `1` passive `spoiling`. Skipped (`8`): `3` hidden (`burner-generator`, `electric-energy-interface`, `hidden-electric-energy-interface`), `1` `asteroid-collector` (deferred), `1` `thruster` (deferred), `3` `lightning-attractor`s (deferred).
  - **Recipes (`651` emitted across `9` shards):**
    - Raw Factorio recipes (`662` total = `611` emitted + `51` skipped): `331` standard gameplay recipes (incl. `scrap-recycling`) + `280` gated gameplay `*-recycling` recipes; skipped: `10` `parameter-*`, `9` hidden debug/creative (`recipe-unknown`, `pistol`, 4× `loader`, `infinity-chest`, `infinity-pipe`, `heat-interface`), `31` hidden/blueprint/tool `*-recycling`, `1` `pistol-recycling`.
    - Synthesized gameplay recipes (`40` total): `19` extraction (`8` solid mining, `4` fluid wells, `4` offshore pumps, `3` agriculture), `10` power/heat (`boiler`, `heat-exchanger`, `steam-engine`, 2× `steam-turbine`, `nuclear-reactor`, `heating-tower`, `fusion-reactor`, `fusion-generator`, `solar-panel`), `1` unified `research` (`lab`/`biolab`), `10` passive `spoil-*` (`spoil_result`).
    - Shard breakdown: `crafting` (`184`), `smelting` (`5`), `chemistry_oil` (`16`), `space_age` (`125`), `extraction` (`19`), `power_heat` (`10`), `research` (`1`), `spoilage` (`10`), `recycling` (`281`).
  - **Icon Provenance (`397` referenced):** **377 authentic Factorio `2.1.25` PNGs** (`308/308` resources, `35/35` machines, `34` visual dropdown/slot options: `12` `modules`, `5` `qualities`, `6` `surfaces`, `11` `solar_locations`) + **20 waived text-only options** (`options/power_modes/*` [3], `options/research_speeds/*` [7], `options/research_presets/*` [9], `options/surfaces/all` [1]) + **0 fabricated icons**.
- **Known Limitations / Deferred Subsystems (v2+):**
  - 5-tier item-quality probability cascades and belt-transit spoilage freshness decay (GameData v4 non-goals).
  - `module_quality` scales the sum of beneficial module stats by `1 + 0.3 × level` (exact for Speed 1–3, Efficiency 1–3, Productivity 3, Quality 1–3, and Legendary Prod 1–2; differs by `0.2%–0.8%` from Factorio's per-module `1%` floor on Uncommon/Rare/Epic Prod 1 & Prod 2).
  - `agricultural-tower` electrical draw (`0.1 MW`) represents conservative active draw (`energy_usage = 100 kW`; crane also peaks `100 kW` while moving, `0 kW` idle while waiting for growth).
  - Deferred entities/mechanics (v2+): `asteroid-collector` (route-dependent spawn rates; chunks are raw inputs), `thruster` (nonlinear fill curve; `thruster-fuel`/`thruster-oxidizer` recipes are included), `lightning-rod` / `lightning-collector` (stochastic Fulgora strikes), beacon electrical power draw, full rocket-launch animation/active energy spike (`50` `rocket-part`s = 1 rocket), ore patch depletion rate, and heat-pipe/inserter/belt heat losses on Aquilo (only building `heating_energy` is summed in `Aquilo thaw heat`).
