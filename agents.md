# Agent Instructions & UI/UX Specification: Tesla HomeAssistant Dashboards (Tessie-Inspired)

> **Note:** This file (`agents.md`) contains instructions for AI coding agents (and technical contributors) working on this repository. If you are a human looking to install and use this project, see [`README.md`](./README.md) instead.

This document provides a comprehensive, highly technical visual and structural blueprint for replicating the Tessie mobile application interface within Home Assistant. It acts as an explicit guide for frontend layout mapping, card selection, backend entity pairing, and calculation logic, tailored specifically for a programmer to implement.

## Global Design & Architecture Parameters
* **Target Environment:** Home Assistant Lovelace Dashboard
* **Architecture Layout:** 2 Separate Dashboards (`tesla_overview` and `tesla_analytics`).
* **Navigation Paradigm:** Top-row horizontal tabs across the top viewport boundary of each dashboard.
* **Layout Paradigm:** Mobile-first, fluid column scaling (recommended components: `type: grid`, `type: vertical-stack`, `type: horizontal-stack`, custom `mushroom-cards`, and `apexcharts-card`).
* **Metric System Standardization:** All values must be displayed strictly in metric units:
  * **Distance/Odometer:** `km`
  * **Speed / Charge Rate:** `km/h`
  * **Pressure:** `bar`
  * **Temperature:** `°C` (rendered as `°`)
  * **Energy/Capacity:** `kWh`
  * **Electrical Power:** `kW`, `A`, `V`
  * **Currency:** Hungarian Forint (`Ft`)
  * **Superseded:** this metric-only mandate was the *original* spec. The
    project now also supports a live **Unit System** selector
    (`input_select.tesla_unit_system` — Metric / US Imperial / UK) and a
    **Currency** selector (`input_select.tesla_currency` — HUF/EUR/USD/GBP),
    both editable from the Analytics dashboard's Settings tab. See Section
    8 ("Unit System Selector") further down for the full implementation,
    conversion constants, and a documented remaining limitation (the
    Driving/Charging analytics charts). Energy/Power (`kWh`, `kW`, `A`, `V`)
    are unaffected by the unit selector — those stay fixed regardless of
    region, matching real-world EV convention.

---

### 1. Critical Resource: `/entities-list.txt`

**MANDATORY FIRST STEP** for any Tesla-related task:

```bash
# Always start here
cat entities-list.txt
```

This file is the **single source of truth** for:
- All Tesla Fleet entities currently available in this Home Assistant instance (exact `entity_id`s, domains, friendly names).
- All custom **Helpers** (`input_boolean`, `input_number`, `input_text`, `input_datetime`, `counter`, etc.).
- Template / derived sensors created for statistics.
- Grouping and notes (e.g., "Vehicle Stats", "Charging Controls", "Climate Comfort", "Energy Site", "Safety & Security").

**When you add or modify anything Tesla-related**:
1. Read `/entities-list.txt`.
2. Make your change (new template sensor, automation, script, dashboard card, etc.).
3. **Update `/entities-list.txt`** with the new entity/helper + short description + example use case.
4. Commit both changes together.

This keeps future agents (and humans) productive.

---


### 2. Expected Project Layout

```
├── /configuration.yaml          # Current existing configuration in HomeAssistant
├── /packages/
│   └── tesla/                  # Recommended: split Tesla config here
│       ├── sensors.yaml        # template: + sensor: for derived stats
│       ├── helpers.yaml        # input_* helpers (or in separate helpers/ dir)
│       ├── scripts.yaml        # scripts + button entities if used
│       ├── automations.yaml    # Tesla-specific automations
│       └── dashboard.yaml      # (optional) raw dashboard config or include
├── /dashboards/
│   ├── tesla-overview.yaml      # Main Tesla Lovelace dashboard
│   └── tesla-analytics.yaml     # Analytics Tesla Lovelace dashboard
├── /automations/                # (if using split automations)
├── /entities-list.txt           # ← Master inventory (keep it updated)
├── /secrets.yaml.example        # Template for secrets.yaml (git-ignored); copy + fill in real values
├── /README.md                   # Human-facing setup & usage guide
└── /agents.md                   # This file (AI agent / contributor instructions)
```

If your actual layout differs, note it at the top of this file after reading the real structure.

---

### 3. Naming Conventions

#### Tesla Fleet Native Entities
Use whatever the integration creates. Typical patterns (exact IDs in `/entities-list.txt`):

**Vehicle examples**:
- `sensor.<name>_battery_level`
- `sensor.<name>_battery_range`
- `sensor.<name>_charge_rate`
- `switch.<name>_charge`
- `number.<name>_charge_limit`
- `number.<name>_charge_current`
- `climate.<name>_climate`
- `lock.<name>_lock` / `lock.<name>_charge_cable_lock`
- `cover.<name>_charge_port_door` / `cover.<name>_frunk` / `cover.<name>_trunk`
- `binary_sensor.<name>_online` / `binary_sensor.<name>_plugged_in` / `binary_sensor.<name>_user_present`
- `button.<name>_wake` / `button.<name>_flash_lights` / `button.<name>_honk_horn`
- `device_tracker.<name>_location`
- `select.<name>_seat_heater_*` / `select.<name>_steering_wheel_heater`
- `switch.<name>_sentry_mode`
- `update.<name>_update`

**Energy Site examples** (if present):
- `sensor.<site>_solar_power`, `sensor.<site>_grid_power`, `sensor.<site>_battery_power`
- `switch.<site>_storm_watch`, `switch.<site>_allow_charging_from_grid`
- `number.<site>_backup_reserve`
- `select.<site>_operation_mode`

**Wall Connector**:
- `sensor.<wc>_power`, `sensor.<wc>_state`, etc.

#### Custom Helpers & Templates (you create these)
**Prefix consistently**:
- `tesla_` for global / shared, non-Fleet-passthrough custom sensors/helpers/scripts/automations
- `vehicle_` — **reserved** for the Fleet Sensor Alias layer only (see Technical
  Appendix §5). Never use `vehicle_` for anything else, and never let a user
  name their actual vehicle `vehicle` (`input_text.tesla_car_name`).

**Good examples**:
- `sensor.tesla_estimated_range_km` (template)
- `sensor.tesla_time_to_full_charge` (template)
- `sensor.tesla_daily_energy_used` (long_term_stats or utility meter)
- `input_number.tesla_target_charge_limit` (user slider, 50–100%)
- `input_boolean.tesla_enable_scheduled_charging`
- `input_boolean.tesla_precondition_on_departure`
- `binary_sensor.tesla_is_home` (zone or location template)
- `script.tesla_smart_charge`
- `automation.tesla_notify_low_battery`

**Always set**:
- `friendly_name`
- `unit_of_measurement` + `device_class` + `state_class` (for statistics / energy dashboard)
- `icon` ( mdi:car-electric, mdi:battery-*, mdi:ev-station, etc.)

---

### 4. Workflow for Common Tasks

#### A. Adding / Improving Statistics (most frequent)
1. Read `/entities-list.txt` → find source sensors (battery_level, charge_rate, battery_range, etc.).
2. Create **template sensor(s)** (prefer `trigger` templates for efficiency in modern HA).
3. Calculate useful derived values:
   - Remaining range (ideal + rated)
   - Time-to-X% or time-to-full (accounting for charge power curve)
   - Efficiency (mi/kWh or Wh/km) over last trip / session
   - "Healthy charge window" recommendation
   - Battery precondition status
4. Expose useful ones to **Energy Dashboard** if they represent home energy impact.
5. Add nice **gauge / statistic / history-graph** cards.
6. Update `/entities-list.txt`.
7. Update `/README.md` if necessary.

#### B. Adding Controls
- **Never call Tesla services directly from dashboard** if possible — go through helpers + scripts for safety + logging.
- Recommended pattern:
  1. `input_number` or `input_boolean` for user intent.
  2. `script` that validates conditions (online? sufficient battery? user present?) then calls the appropriate entity service:
     - `number.set_value` → charge limit / current
     - `switch.turn_on/off` → charge, sentry_mode
     - `climate.set_temperature` + `climate.turn_on`
     - `button.press` for wake / flash / honk
     - `cover.open_cover` / `close_cover`
  3. Optional confirmation + notification on success/failure.
- Add the control to the Tesla dashboard as **button**, **entity**, or **custom:mushroom** card.

#### C. Automations
- Trigger on meaningful Tesla state changes (`plugged_in`, `charging`, `online` → `not_home`, charge start, etc.).
- Use `state_attr()` liberally for rich vehicle data.
- Common patterns:
  - Auto-start charge when solar surplus high + car at home + below target.
  - Precondition cabin 20–40 min before calendar event or "departure time" input.
  - Notify when charge complete or when battery drops below threshold while away.
  - Disable sentry when arriving home.
  - Wake vehicle only when really needed (expensive in battery).

#### D. Dashboards
- One main "Tesla" dashboard (or tab).
- Sections / conditional cards:
  - **Overview** — big battery gauge + range + status pills (online/plugged/charging/sentry)
  - **Charging** — limit slider (input), current power, time remaining, start/stop buttons
  - **Climate** — target temp, seat heaters (multi-select or separate toggles), defrost, precondition script
  - **Stats & History** — graphs for battery, consumption, charge sessions
  - **Location & Security** — map, last seen, lock controls, sentry toggle
  - **Energy Site** (if present) — solar production, home usage, battery flow, storm watch toggle
- Use **conditional** visibility based on `binary_sensor.*_online` and `binary_sensor.*_user_present`.
- Mobile-first design.

---

### 5. Best Practices & Gotchas

#### Tesla Fleet Specific
- The integration does smart polling. Do **not** create automations that constantly wake the car.
- Newer vehicles (late 2023+) require **command signing** (private key + virtual key in Tesla app). Make sure it's set up.
- Some commands (especially charging & climate) only work when online or recently woken.
- Energy site APIs are generous; vehicle commands have more restrictions.
- Monitor Tesla Developer Dashboard for API credit usage ($10/month personal credit usually sufficient).

#### Home Assistant YAML
- Prefer **packages** or `include_dir_list` for organization.
- Use **modern template syntax** (trigger-based where beneficial).
- Add `unique_id` to template entities and helpers so they survive config reloads / moves.
- Document complex Jinja with comments.
- Test templates in **Developer Tools → Template** before committing.

#### Safety & UX
- Charging and climate control have real-world cost → add guards (e.g. "only if battery > 20%").
- For destructive actions (unlock, open frunk) prefer scripts with confirmation.
- Show clear feedback (persistent notification or dashboard toast via `notify`).
- Respect sleep: many automations should check `binary_sensor.*_online` first.

#### Maintenance
- After Tesla or HA updates, re-validate key entities and automations.
- Keep `/entities-list.txt` in sync — it is the contract between the integration and your custom layer.
- Version control everything (including the generated Lovelace dashboard YAML if you export it).

---

### 6. Quick Reference Commands (for the AI / you)

When working on this project, typical first actions:

```bash
# 1. Understand current state
cat entities-list.txt | head -100

# 2. Find existing Tesla package / templates
grep -r "tesla_" packages/ --include="*.yaml" | head -20

# 3. Check a specific entity state (user will run in HA)
# Developer Tools → States → filter "tesla"

# 4. Test a new template
# Developer Tools → Template
```

---

### 7. References

- Official docs: https://www.home-assistant.io/integrations/tesla_fleet/
- Tesla Fleet API: https://developer.tesla.com/
- Useful community resources: Home Assistant Tesla threads, TeslaMate (for comparison), Teslamate → HA export patterns.

---

**Remember**: This project succeeds when the custom layer feels magical but stays simple and well-documented. Start every Tesla task by consulting `/entities-list.txt`.

---

### 8. Replicating the Tessie App Experience (Major Initiative)

The user wants a **beautiful, Tessie-like interface** inside Home Assistant for "Tesla" (Tesla Model X).

#### Philosophy
- One main **Tesla** dashboard with multiple **Views** (tabs) instead of many separate dashboards.
- Each major Tessie screen becomes a View: Overview, Battery, Climate, Tires, Costs & Analytics.
- Heavy use of **Mushroom cards**, `custom:button-card`, `statistics-graph`, and `custom:apexcharts-card` for modern look. Most charts type should be Bar chart. It there are SUM amounts, those shouldn't be displayed together with other data, those should be displayed just as numbers next to or under/above the chart.
- All quick actions go through **scripts** (safer + logged).

## Dashboard 1: Tesla Overview
**Dashboard ID:** `tesla_overview`  
**Navigation Layout:** Top navigation bar featuring 6 distinct tabs (tabs function as views).

### Tab 1: Dashboard (Main Hub View)
Acts as the central cockpit displaying real-time vehicle status and high-frequency operational controls.

#### 1. Header Navigation & Status Row
* **Visual Layout:** Single horizontal row spanning the top window width (`horizontal-stack`).
* **Left Element:** Text title pulling from the vehicle name entity (`sensor.tesla_vehicle_name`, e.g., "Tesla") paired with a tiny down chevron indicator representing a dropdown entity switcher. Immediately next to it, a clickable Notification Bell icon.
* **Right Element:** Battery layout cluster containing a horizontal battery outline filled proportionally to the state of charge (dynamic green/yellow/red fill), text showing exact battery state remaining range (e.g., **164 km**), and an overlaying green lightning plug glyph if connected to a charging cable.

#### 2. Charging Status Card (Conditional Visibility)
* **Logic:** Wrap this entire block inside a Lovelace `conditional` card. Only display when the binary sensor state for charging is active (`true`).
* **Visual Style:** High contrast, bright blue background or light glowing border accent.
* **Row 1 Text:** "Charging >" (Left-aligned) | Time Remaining String (Right-aligned, formatted exactly as: `4h 14m remaining > 13:16`).
* **Row 2 Text:** Detailed electrical metrics string separated by a bold mid-dot (`•`):  
  `[Current Amperage]/[Max Limit Amperage] A • [Voltage] V • [Power Output] kW • [Range Speed] km/hr`  
  *(Example Output: `5/16 A • 230 V • 3 kW • 14 km/hr`)*

#### 3. Quick Action Row
* **Visual Layout:** A single horizontal row (`horizontal-stack`) of exactly 6 uniform, minimalist square button tiles.
* **Icons & Service Calls Mapping:**
  * **Button 1 (Lock/Unlock):** Padlock icon (Dynamic state change: open/closed). Maps to `lock.toggle` on `lock.tesla_doors`.
  * **Button 2 (Climate):** Fan/HVAC blades icon. Maps to `climate.toggle` on `climate.tesla_hvac`.
  * **Button 3 (Frunk):** Front-open vehicle profile silhouette icon. Triggers service to unlatch the front trunk mechanism.
  * **Button 4 (Trunk):** Rear-open vehicle profile silhouette icon. Triggers service to unlatch the rear trunk tailgate.
  * **Button 5 (Flash):** Flashlight / Highbeam signal lines icon. Triggers vehicle exterior light flash service.
  * **Button 6 (More):** Triple horizontal dots (`...`) icon. Opens a frontend sidebar panel or browser-mod popup for secondary actions.

#### 4. Location Strip Card
* **Visual Layout:** Slim, rounded full-width banner card positioned directly below the quick actions.
* **Contents:** A blue navigation map arrow icon paired with the current geolocated street-level address string variable text (e.g., "123 Main St"). Clicking this card executes a URL redirection to Google Maps using real-time coordinates.

#### 5. Information Overview Grid
* **Visual Layout:** A balanced 2-column square card matrix layout (`type: grid`, `columns: 2`). Each tile displays an identity icon in the top corner, a large primary center title, and secondary state helper strings below.

| Card Name | Left Side (Main Text Readout) | Right Side (Icon / Context Label) |
| :--- | :--- | :--- |
| **Climate** | `29°` | Fan/HVAC Status / Clock Icon |
| **Battery** | `189 km` | Battery Fill Capacity Gauge Icon |
| **Schedule** | `09:25` | Steering Wheel + Departure Clock Icon |
| **Tires** | `Optimal` | Green Checkmark Verification Badge Icon |
| **Drives** | Time context: `20 minutes ago` | Map Navigation Path Arrow Symbol |
| **Charges** | Time context: `14 hours ago` | Lightning Bolt Cable Connector Symbol |
| **Idles** | Time context: `17 minutes ago` | Parking Monogram "P" Shield Icon |
| **Activity** | Operational State: `Charging` | Continuous Timeline Activity Loop Icon |
| **Automation**| State Toggle Status: `Off` | Magic Wand Execution Toggle Icon |
| **Profiler** | State Toggle Status: `Off` | Speedometer Performance Tracking Icon |

#### 6. Vehicle Specifications Footer
* **Visual Layout:** Centered, low-contrast small font Markdown text card aligned at the screen base.
* **Left Column Parameters:** Model Name (`Tesla Model X`), VIN Number (`5YJ12345678901234`), License Plate ID (`XXYY-123`).
* **Right Column Parameters:** Active OS Firmware version (`2026.14.6`), True Lifetime Odometer reading (`201,205 km`), Error Alert counter text (`13 recent alerts`).

---

### Tab 2: Controls
Dedicated interaction pane containing deeper hardware control parameters using standard switch and slider entities.
* **Window Venting Matrix:** Dual button stack configuration (`Vent Windows` / `Close Windows`).
* **Sentry Mode Switch:** High-visibility toggle switch bound straight to `switch.tesla_sentry_mode`.
* **Media Playback Controls:** Graphic display of current song title string, interactive volume horizontal slider, and playback track selection buttons.
* **Valet Mode & Speed Limit Constraints:** Secure toggle and numeric text entry sliders for clamping maximum allowable vehicle velocity.

---

### Tab 3: Climate
Replicates the comprehensive climate control loop, environmental metrics, and top-down cabin heating zones.

#### 1. Environmental Readings Header
* **Visual Layout:** Wide title block element. Left text title reads: "Climate" | Right text displays outdoor ambient tracking sensor levels (e.g., `23°`) flanked by a corresponding weather state badge (e.g., sun/cloud icon).
* **Hero Numeric Readout:** Center-aligned prominent heavy text block displaying interior cabin temperature: `INTERIOR 29°`.

#### 2. Spatial Seat Heating Matrix Map
* **Visual Layout:** Custom visual layout mimicking the overhead seating blueprint of a 6-seat cabin configuration.
* **Seating Elements:** 6 distinct seat buttons. Each button features an explicit seat outline graphic with three integrated vertical wavy heating paths overlayed.
* **State Logic Behavior:** Tapping an individual seat shifts its state cyclical value through 4 steps: `0 (Off/Greyed Lines)` -> `1 (Low/1 Red Line)` -> `2 (Medium/2 Red Lines)` -> `3 (High/3 Red Lines)`.
* **Steering Wheel Heat:** A separate standalone steering wheel icon centered at the top of the map grid to directly toggle steering wheel rim thermal execution status.

#### 3. Core Temperature Setpoint Adjuster
* **Visual Layout:** Large centered horizontal linear stepper block between the cabin layout and auxiliary buttons.
* **Elements:** Left arrow button (`<`), center heavy numerical temperature setpoint indicator text (`22.0°`), and right arrow button (`>`). Pressing arrows triggers a service call to shift target climate entities up or down by `0.5°C` increments.

#### 4. Auxiliary Climate Action Grid
* **Visual Layout:** 2-row, 3-column structural button array. Active states must illuminate the card background with a distinct accent color.
  * **Dog Mode:** Paw Icon (Holds cabin cooling while parked, displaying an explanatory safety note on the center screen).
  * **Camp Mode:** Tent Icon (Maintains continuous power routing and climate control while vehicle is parked).
  * **Bio Defense:** Biohazard Safety Icon (Forces max positive pressure HEPA filtration loop).
  * **Climate Switch:** Simple Fan Icon (Master HVAC state toggle).
  * **Defrost Switch:** Windshield grid lines icon (Triggers max front/rear glass defogging heaters).
  * **Cabin Protection:** Shield icon with internal thermal lines (Toggles automated background anti-overheat safety thresholds).

---

### Tab 4: Battery
Monitors deep state indicators, capacity buffers, and current limit configurations.

#### 1. Primary Battery Gauge Element
* **Visual Layout:** Large wide landscape card housing a single thick horizontal bar tracking present capacity (e.g., `46%`).

#### 2. High-Density Telemetry Table
* **Visual Layout:** Balanced 2-column key-value lookup display.

| Parameter Name | Target Mapping Sensor / String Structure |
| :--- | :--- |
| **LEVEL** | `46%` |
| **RANGE** | `189 km (164 km)` *(Displays rated expected estimate vs raw unadjusted baseline buffer value)* |
| **DRAIN** | `0.00%` |
| **ENERGY** | `44.90 / 100.00 kWh` |
| **TEMPERATURE** | `33.0 - 36.5°C` *(Tracks absolute cell variance minimum to maximum temperature peaks)* |
| **AMPERAGE** | `7.9 A` |
| **VOLTAGE** | `363.6 V` |
| **ENERGY USED** | `63,329.10 kWh` *(Lifetime absolute pack throughput integration calculation)* |

#### 3. Charge Limit Interactive Configurator
* **Header Label String:** `"CHARGE LIMIT 247 KM • 60%"`
* **UI Input Element:** Interlocking slider control element mapping straight onto the system's target limit configuration value helper (`input_number` helper configuration bounded between 50% and 100%).

#### 4. Action Base Row
* **Visual Layout:** 2-column wide horizontal button pairing split across the baseline row.
* **Left Button:** Context-aware lightning bolt icon command text. Displays `Stop charging` if an active connection is drawing load, else switches dynamically to `Start charging`.
* **Right Button:** Eject lock symbol icon command text labeled `Unlock port`.

---

### Tab 5: Tires
Displays real-time rolling pressure monitoring system values alongside historic line logs.

#### 1. Target Value Header Notice
* **Visual Layout:** Minimal thin notification banner layout reading: `💡 Recommended cold pressure: 2.9 bar`.

#### 2. Real-Time Wheel Matrix Layout
* **Visual Layout:** 2x2 grid card arrangement corresponding to physical wheelbase coordinates.
* **Card Details:** Green checkmark badge icon representing a healthy safety flag status alongside the exact location identity and numerical pressure sensor readouts:
  * **FRONT LEFT:** `3.02 bar` | **FRONT RIGHT:** `3.02 bar`
  * **REAR LEFT:** `3.00 bar` | **REAR RIGHT:** `3.02 bar`

#### 3. Multi-Band Historical Graph Component
* **Component Framework Suggestion:** `type: custom:apexcharts-card` plotting continuous rolling multi-week timeline records.
* **Y-Axis Background Zones (Horizontal Color Striping):**
  * **Zone 1 (Critical High):** Values `> 3.5 bar` -> Red fill overlay area labeled explicitly: `>3.5 BAR • UNSAFE`.
  * **Zone 2 (Warning Elevated):** Values `3.1 bar to 3.5 bar` -> Muted yellow/light-olive fill area labeled: `&gt;3.1 BAR • HARSHER RIDE & WEAR`.
  * **Zone 3 (Target Zone):** Values `2.5 bar to 3.1 bar` -> Solid deep-green translucent area overlay labeled: `OPTIMAL`.
  * **Zone 4 (Warning Low):** Values `1.9 bar to 2.5 bar` -> Orange tint warning block overlay labeled: `<2.5 BAR • REDUCED HANDLING & EFFICIENCY`.
  * **Zone 5 (Critical Low):** Values `< 1.9 bar` -> Red fill area block overlay labeled: `<1.9 BAR • UNSAFE`.
* **Data Series Line:** Plot actual wheel pressure data points as a continuous smooth trend line flowing across the time axis within the optimal green band coordinates.

---

### Tab 6: Cost Projections
Calculates financial predictions based on energy ingestion telemetry.

* **Visual Layout:** 3 stacked structural summary rows (Monthly, Annual, 5 Years). Each row holds 3 columns segmenting resource expenditures across three distinct energy destination streams.

| Temporal Scope Horizon | Home Network Ingestion Cost | Supercharger Network Cost | Other Networks Cost |
| :--- | :--- | :--- | :--- |
| **MONTHLY** | `Ft41,583` | `Ft0` | `Ft0` |
| **ANNUAL** | `Ft498,996` | `Ft0` | `Ft0` |
| **5 YEARS** | `Ft2,494,980` | `Ft0` | `Ft0` |

---
---

## Dashboard 2: Tesla Analytics
**Dashboard ID:** `tesla_analytics`  
**Navigation Layout:** Top navigation bar containing 2 tabs (`History` and `Analytics`).

### Tab 1: History (Unified Lifecycle Stream Logs)
Acts as a unified scrolling timeline database ledger. All lifecycle events (Drives, Charges, and Idles) are combined chronologically under bold, uppercase daily header blocks.

#### 1. Unified Timeline Stream Elements Layout
* **Drive Entry Row Pattern:** Displays a standard map pointer icon. Left column features active time bounds (`07:14 – 07:56`) and named route tracking text endpoints (`Home ➔ Work`). Center column displays transit distance metrics (`23.4 km`) and elapsed duration (`42 min`). Right column lists absolute battery capacity delta drop parameters in parentheses (`82% ➔ 71% (-11%)`) and average consumption efficiency rates (`176 Wh/km`).
* **Charge Entry Row Pattern:** Displays a lightning bolt wire connection symbol icon. Left column features active plug-in time bounds (`22:15 – 06:30`) and assigned location classification labels (`Home (123 Main St)`). Center column displays total bulk energy pushed into cells (`34.50 kWh`) and total connection duration (`8h 15m`). Right column lists state capacity percentage jumps (`46% ➔ 90% (+44%)`) and final calculated session billing costs in Hungarian Forints (`Ft2,070`).
* **Idle / Standby Entry Row Pattern:** Displays a parking "P" monogram or sleep "Zzz" icon. Left column features stationary time boundaries (`07:56 – 16:45`) and geolocated location descriptions (`Work (456 Office Ave)`). Center column tracks total stationary duration (`8h 49m`) and active standby profile flags (`Sentry Active` or `Asleep`). Right column captures battery tracking shifts (`71% ➔ 69% (-2%)`) and absolute lost electrical capacity (`1.50 kWh lost`).

#### 2. Sub-View: Individual Drive Detail Panel
* **Logic:** Triggered as a modal popup via a `browser-mod` configuration call when a user taps any drive log row from the timeline stream.
* **Header Row:** Features an explicit back navigation chevron (`< Back to History`), centered main route titles, and the calendar execution date stamp.
* **Integrated Interactive Map Component:** Embedded Home Assistant native `map` panel pulling structural database coordinate array points from `device_tracker` historical recorders. Renders a solid blue layout path vector line tracking route history, anchoring a green origin node dot and a red cross-line destination pin symbol.
* **Trip Metrics Summary Grid Matrix:** A 4-column by 2-row high-density key-value grid component directly tracking static segment attributes.

| Metric Box | Primary Main Text String | Metric Box | Primary Main Text String |
| :--- | :--- | :--- | :--- |
| **Distance** | `23.40 km` | **Energy Used** | `4.12 kWh` |
| **Duration** | `42m 12s` | **Avg Efficiency** | `176 Wh/km` |
| **Avg Speed** | `33.2 km/h` | **Battery Start/End**| `82.0% / 71.0%` |
| **Max Speed** | `92.0 km/h` | **Odometer Span** | `201,205 ➔ 201,228 km` |

* **Telemetry Profile Chart:** `custom:apexcharts-card` combining dual coordinate parameters over a shared duration horizontal X-axis. Y-axis Left Scale draws a solid blue trend line charting vehicle speed tracking levels (`km/h`). Y-axis Right Scale charts topographic terrain altitude variation using a shaded light grey fill area graph (`meters`).

---

### Tab 2: Analytics (Deep Metrics Sub-Panel Options)
Aggregates dynamic tracking profiles. All charts below respond dynamically to the active **Temporal Range Selector Bar** (`7 Days`, `30 Days` [Default Active], `1 Year`, `All Time`).

#### 1. Cumulative KPI Summary Component Row
A 4-column horizontal card grid matrix directly highlighting macroscopic system utilization variables based on selected category views.
* **Drives Profile view:** `Total Distance: 1,426 km` | `Total Duration: 28h 45m` | `Total Energy Spent: 263.8 kWh` | `Avg Efficiency: 185 Wh/km`
* **Charges Profile view:** `Total Grid Energy: 412.6 kWh` | `Total Cost Spent: Ft24,756` | `Est ICE Cost Baseline: Ft68,420` | `Net Savings Realized: Ft43,664`
* **Idles Profile view:** `Total Stationary Time: 512h 24m` | `Total Phantom Energy Loss: 34.2 kWh` | `Avg Standby Parasitic Speed: 66.7 Wh/h` | `Sentry Mode Uptime: 112h 10m`
* **Activity Profile view:** `Total Evaluation Window: 720h 00m` | `Moving Transit Time: 38h 12m` | `Active Charging Time: 42h 18m` | `Standby/Sleep Inactive Time: 639h 30m`

#### 2. Advanced Diagnostic Visualization Stack
A vertical sequence of advanced graphical monitoring panels using `apexcharts-card` to render charts organized by analysis module.

##### Module A: Driving Analytics Graphics
* **Chart A (Financial Comparison & Net Energy Savings):** Stacked or side-by-side vertical bar column groups. Series 1 columns show hypothetical baseline combustion fuel costs (dark grey/crimson bars) derived from system comparison settings. Series 2 columns show actual EV charging costs (bright blue bars) calculated from location rate profiles. A bright green line graph is overlayed to track cumulative net savings (`Ft`).
* **Chart B (Efficiency vs Speed Optimization Curve):** Horizontal X-axis splits logging velocities into 10 km/h speed buckets (spanning from 0 to 140 km/h). Vertical Y-axis tracks consumption indicators in `Wh/km`. Renders individual raw data scatter points alongside a smooth polynomial regression line, tracking the vehicle's optimal efficiency speed bands.
* **Chart C (Volumetric Driving Activity Matrix):** Heatmap panel tracking vehicle utilization patterns. Y-axis displays day name rows (`Mon` to `Sun`); X-axis charts 24 hourly horizontal block bins. Color intensity transitions from light neutral tints to dense primary blue to highlight peak driving times during the week.
* **Chart D (Speed Distribution Profile Histogram):** Area Curve Chart. X-axis logs velocity bins in 10 km/h increments; Y-axis measures the exact percentage allocation share of total running duration. Displays a smooth bell-shaped area curve highlighting the vehicle's historical split between stop-and-go urban transit and high-speed highway cruising.

##### Module B: Charging Analytics Graphics
* **Chart E (Charge Location & Type Distribution):** Clear circular donut chart tracking share allocation segments. Home charging is represented by a deep blue segment, Superchargers by a vibrant red segment, and work/other networks by a light grey/green segment. Legend formatting: `Home • 321.8 kWh (78%)`.
* **Chart F (Energy Added vs Financial Expenditure):** Dual-axis chart. Horizontal X-axis tracks temporal date blocks. Vertical Y-axis Left Scale measures total bulk energy delivered via vertical columns (`kWh`). Y-axis Right Scale uses a dark grey or green step-line graph to plot financial transaction tracking metrics (`Ft`).
* **Chart G (Charging Power Performance Curve):** Horizontal X-axis tracks battery state of charge increments from 0% to 100%; vertical Y-axis monitors continuous instantaneous power delivery metrics in `kW`. Plots data points alongside an automated running-average trendline to visualize thermal throttling characteristics.
* **Chart H (Monthly Charging Source Efficiency Matrix):** Stacked Column Chart. Horizontal X-axis indexes successive calendar months (`Jan` to `Dec`); vertical Y-axis tracks absolute monthly volumetric energy values in `kWh`. Each month's single column bar is divided into color-coded stacked segments mapping energy source contribution types over time.

##### Module C: Idles & Standby Drain Graphics
* **Chart I (Stationary State Allocation):** Donut chart breakdown tracking total parked vehicle states. Core tracking segments include: Deep Sleep (shaded forest green), Awake/Idle (shaded ochre yellow), and Sentry Mode active tracking (shaded crimson red). Legend matches state tags to raw duration and percentage breakdowns: `Sentry Mode • 112.2 h (21.9%)`.
* **Chart J (Standby Drain Rate vs Ambient Temperature):** Scatterplot layout chart. Horizontal X-axis tracks outside ambient temperature values (°C); vertical Y-axis monitors the continuous parasitic background power drain velocity in `Wh/h`. Plots data points alongside a central regression line.
* **Chart K (Historical Daily Phantom Drain Accumulation):** Stacked Column Chart. Horizontal X-axis indexes daily date blocks; vertical Y-axis tracks cumulative lost energy per day in `kWh`. Individual column bars are split into color-coded stacked blocks indicating the underlying cause of energy loss: Sentry Mode overhead draw (red), system awake/polling overhead (yellow), and baseline chemical leakage (green).

##### Module D: Macro Activity Tracking Graphics
* **Chart L (Macro Vehicle State Allocation):** Donut chart tracking overall vehicle utilization. Splits the total timeline into 4 core lifecycle segments: Driving (bright blue), Charging (electric cyan), Idling/Awake (ochre yellow), and Sleeping (soft muted green). Legend shows state tags alongside absolute hours and precise percentages: `Sleeping • 525.6 h (73.0%)`.
* **Chart M (Hourly State Profiles Over Weekdays):** A 7-row by 24-column heatmap matrix tracking vehicle state profiles. The Y-axis indexes the days of the week (`Mon` to `Sun`) and the X-axis indexes 24 hourly blocks (`00:00` to `23:00`). Grid intersections change color to represent the dominant operational state during that specific hour: blue blocks for driving commutes, cyan for scheduled charging window execution, and muted green/grey for deep sleep cycles.
* **Chart N (Daily Cross-Section State Composition):** Stacked Column Chart. Horizontal X-axis tracks rolling daily dates; vertical Y-axis is fixed to a 24-hour limit scale. Every daily column bar is scaled to fill the full 24-hour vertical layout. Bars are divided into stacked color blocks showing that day's state breakdown: Driving (blue), Charging (cyan), Idling (yellow), and Sleeping (green).
* **Chart O (Historic State of Charge Envelope):** Linear chronological time chart tracking long-term battery usage cycles. A single continuous blue trend line plots the battery state of charge from 0% to 100%, capturing sudden vertical charging spikes alongside slow, gradual drainage lines from driving or standby drain.

---
---

## Global System Settings Specification
This section maps the structural interface forms required to handle backend financial equations, regional timezones, variable multi-tariff utility schedules, and internal comparative profiling parameters.

### 1. Electric Costs Configuration Panel
* **UI Layout:** A clean vertical menu configuration tracking standard electrical source types.
* **Saved Locations Row Block:** Left card text info reads: *"Charging at home, work and more. Add a saved location to define rates and track costs."* Right side contains a primary execution selector button labeled: `Manage saved locations`.
* **Supercharging Status Handlers:** Block text reads: *"Supercharging. Tessie automatically syncs Supercharging costs with your Tesla account."* Accompanied by two horizontal action buttons: `Select` and `Resync`.
* **Fallback Universal Rate Row:** Label text reads: *"Default. Set a default rate when no other rate is found."* Features an interactive numeric entry box showing the fallback parameter rate value (e.g., `Ft60.00 / kWh`), mapping entries back to a central global utility entity helper: `input_number.tesla_default_electricity_cost`.

### 2. Location-Specific Rate & Schedule Customizer (Edit "Home" Location)
* **UI Layout:** Configuration form card interface containing two sub-navigation tabs labeled **Settings** and **Costs** (with **Costs** active by default). This form handles flat rates, per-minute structures, and dynamic time-of-use schedule rules.
* **Per kWh Input:** Numeric tracking box field matching flat-rate energy delivery pricing structures. Default initial state value text: `60.0`.
* **Per minute Input:** Data text block targeting infrastructure segments that calculate billing dynamically based on exact connection uptime windows. Default state: `0.00`.
* **Per session Input:** Standard base-fee access calculation tracking set baseline connection service fees. Default state: `0.00`.
* **Rate Schedules Manager:** Contains an action button tagged `[Add]` designed to initialize new custom multi-tariff rules or calendar date ranges. Below it, a timezone selection dropdown row is pinned to the target region profile identifier string: `Europe/Budapest`.
* **Schedule Rule Visual Block Card 1 (Peak / Standard Baseline Track):**
  * Display Rate Value Info Header: `Ft60.00 / kWh`
  * Active Runtime Time Constraints Block: `00:00 – 00:00` (Represents full 24-hour continuous rolling coverage loop).
  * Weekly Active Days Target Matrix: List mapping explicit daily tracking variables (`Mon Tue Wed Thu Fri Sat Sun`).
  * Active Yearly Target Track Windows: Complete multi-month seasonal execution wrapper profile (`Jan – Dec`).
* **Schedule Rule Visual Block Card 2 (Solar / Off-Peak Custom Track Optimization):**
  * Display Rate Value Info Header: `Ft0.00 / kWh` (Represents free solar overproduction or special off-peak windows).
  * Active Runtime Time Constraints Block: Midday track execution tracking hours `10:00 – 14:00`.
  * Weekly Active Days Target Matrix: List mapping active daily tracking variables (`Mon Tue Wed Thu Fri Sat Sun`).
  * Active Yearly Target Track Windows: Summer/Solar season profile bounds tracking tracker elements (`May – Sep`).
* **Footer Action Controls Row:**
  * **Update Charging History Button:** Secondary outlined action item button that loops backward across long-term stored historical records, reapplying current pricing rule modifications retroactively.
  * **Save Button:** High-visibility primary blue accent call-to-action button to commit configuration modifications into persistent memory storage files.

### 3. Fuel Comparison Profiler
* **UI Layout:** A dedicated vertical variable configuration card designed to manage parameters for generating side-by-side cost comparisons with internal combustion engine (ICE) vehicles.
* **Header Text Summary Box:** Text reads: *"Fuel costs. Instantly compare your driving and charging costs to any gas vehicle"*
* **Efficiency Type Selector:** Dropdown options box toggle element configured to default metric tracking style target value: `L/100km`.
* **Fuel Consumption Rate Input:** Precision double floating-point numeric entry field to establish the target baseline efficiency parameter. Initial default value: `6.50`. Maps straight onto backend helper configuration entity (`input_number.comparison_ice_efficiency`).
* **Cost Per Litre Price Input:** Integer input configuration tracking field to match dynamic fuel pricing structures. Initial value parameter text mapping entry state: `595.00`. Maps straight onto tracking entity variable identifier asset (`input_number.comparison_fuel_price_per_liter`).

---
---

## Technical Appendix for Programmer Implementation

### 1. Database Recording Requirements
Ensure the Home Assistant database recorder configuration (`configuration.yaml`) does not purge historical state tracking data for these critical telemetry assets for at least 365 days:
* Geolocation coordinate array structures (`device_tracker.tesla_location`)
* Exact odometer tracking steps (`sensor.tesla_odometer`)
* Absolute lifetime energy integration meters (`sensor.tesla_total_energy_used`)
* Standby state configuration flags (`sensor.tesla_sentry_mode_status`, `sensor.tesla_operational_state`)
* Ambient and interior cabin temperature values (`sensor.tesla_outside_temp`, `sensor.tesla_inside_temp`)

### 2. Core Operational & Financial Comparison Formulas
Deploy these explicit mathematical calculations within automated template sensors (`templates.yaml`) to drive the analytics dashboard metrics:

$$\text{Equivalent Gas Cost (Ft)} = \left( \frac{\text{Total Distance Driven in km}}{100} \right) \times \text{ICE Efficiency (L/100km)} \times \text{Cost per Litre (Ft/L)}$$

$$\text{Net Financial Savings (Ft)} = \text{Equivalent Gas Cost} - \text{Calculated EV Charging Cost}$$

$$\text{Instantaneous Drain Rate (Wh/h)} = \frac{\text{Energy Ingested or Lost in Watt-Hours}}{\text{Exact Elapsed Duration in Decimal Hours}}$$

$$\text{Vehicle Fleet Utilization Rate (\%)} = \left( \frac{\text{Total Driving Hours} + \text{Total Active Charging Hours}}{\text{Total Elapsed Window Timeline Hours}} \right) \times 100$$

### 3. ApexCharts Base Component Template Code Snippet
To maintain layout and visual consistency across all analytics charts, use this base layout configuration block inside your custom dashboard cards definitions:

type: custom:apexcharts-card
graph_span: 30d
header:
  show: true
  show_states: true
  colorize_states: true
apex_config:
  chart:
    height: 280
    foreColor: '#7F7F7F'
    toolbar:
      show: false
  stroke:
    curve: smooth
    width: 2
  grid:
    borderColor: '#2D2D2D'
    strokeDashArray: 4

### 4. Entity Prefix Naming & Renaming (`scripts/rename_tesla_prefix.py`)

**Why there is no YAML "global variable" for the `tesla_` prefix:** Plain YAML
has no string-interpolation feature — there's no way to define a value once
and splice it into the middle of another string (e.g. `${prefix}_odometer`).
YAML anchors (`&x` / `*x`) only substitute a whole scalar/mapping/list, not a
fragment of text inside a string. Home Assistant also does not evaluate Jinja
templates in `unique_id:`, `name:` (as a YAML key), or automation `id:`
fields — those are static and read once at config load. So the `tesla_`
prefix used across `configuration.yaml`, `packages/tesla/*.yaml`,
`dashboards/*.yaml`, and `entities-list.txt` cannot be centralized in the
YAML itself; it's a plain text convention.

**Naming convention this repo relies on:** machine identifiers always use
lowercase `tesla_...` (`unique_id: tesla_driving_time_today_raw_v1`,
`sensor.tesla_odometer`, automation `id:` fields, utility_meter/input_number
keys), while human-readable text uses capitalized `Tesla ...` (friendly
`name:` strings, markdown, comments, brand references like "Tesla Fleet
integration"). Any tooling that mass-renames the prefix must respect this
distinction to avoid corrupting prose.

**The rename tool:** `scripts/rename_tesla_prefix.py` performs a scoped
find/replace across the known project files, matching only the lowercase
`tesla_` token pattern by default (word-boundary anchored), with an opt-in
`--include-labels` flag to also rewrite the capitalized `Tesla` word in
friendly names. It's dry-run by default (prints a unified diff, changes
nothing) and only writes changes with `--apply`, after backing up originals
to `.backups/rename_tesla_prefix_<timestamp>/`. See the script's module
docstring and `README.md`'s Maintenance section for usage.

**Home Assistant side-effects of an entity_id/unique_id rename** (relevant
when advising a user who wants to run this after already collecting weeks of
history — see README FAQ for the user-facing version):
* The Recorder's `states` table history is keyed by `entity_id`. Renaming an
  entity means Home Assistant treats it as a **new** entity — old history
  rows are **not deleted** (they remain in the DB until the normal purge
  retention period), but they stay attached to the old, now-orphaned
  `entity_id` and won't show up in the new entity's history/graphs.
* Long-term statistics (`statistics` / `statistics_short_term` tables, used
  by Statistics Graph cards, the Energy dashboard, and any `apexcharts-card`
  `statistics:` series) are also keyed by `entity_id`/`statistic_id`. These
  do **not** migrate — the renamed entity starts with an empty statistics
  history.
* `utility_meter` helpers (daily/weekly/monthly accumulators like
  `tesla_daily_drive_energy`) store their current-cycle running total as
  their own entity state, restored via Recorder on restart. If you rename the
  utility_meter entity itself, its accumulated cycle value resets to 0 (it's
  effectively a new entity). If you only rename its `source:` entity, the
  meter loses its data source until you update `source:` to match.
* YAML-defined `input_number` helpers (e.g.
  `input_number.tesla_drive_energy_consumed_total_kwh`, the lifetime real-
  energy accumulator) restore their last value via Recorder's restore-state
  cache, keyed by `entity_id`. Renaming it means the new entity starts fresh
  at its configured `initial:` value — the previously accumulated total is
  orphaned unless manually copied over.
* Old (now-unreferenced) entities remain in the Entity Registry showing
  `unavailable`. Clean them up with the existing
  `scripts/cleanup_legacy_entities.py` (set `LEGACY_PREFIX` to the old
  prefix) after confirming the new prefix is working.

**Recommended safe rename procedure:** before running with `--apply`, note
down the current value of any lifetime accumulators you care about (chiefly
`input_number.tesla_drive_energy_consumed_total_kwh` — Developer Tools →
States) so you can manually restore them via
`input_number.set_value` on the newly-named entity right after restarting HA,
if continuity matters more than a fresh start.

### 5. Fleet Sensor Alias Layer (`vehicle_*` prefix) — vehicle-name-agnostic design

**What it is:** `configuration.yaml` defines ~29 template entities named
`sensor.vehicle_*` / `binary_sensor.vehicle_*` (e.g. `sensor.vehicle_odometer`,
`sensor.vehicle_battery_level`, `binary_sensor.vehicle_status`). These are
pure pass-through aliases — each one reads `input_text.tesla_car_name` and
dynamically looks up `sensor.<car>_odometer`, `sensor.<car>_battery_level`,
etc. from the *real* Tesla Fleet integration entity for whatever the user's
vehicle is actually named. All dashboards (`dashboards/*.yaml`) and
automations (`packages/tesla/automations.yaml`) that need a raw Fleet
attribute (odometer, battery level/range, charge rate/power/voltage/current,
charging state, inside/outside temp, shift state, speed, time to full charge,
tyre pressures + warnings, charge cable) read the `vehicle_*` alias, **never**
the literal `sensor.tesla_*` Fleet entity directly. This is what lets a user
rename their car (`input_text.tesla_car_name`) to anything — `tesla`, `x`,
`0`, `42`, `my_model_y` — without touching a single dashboard/automation file.

**Why the prefix is `vehicle_` and not `tesla_`:** this project originally
named the alias layer `sensor.tesla_*` (matching the repo's own default
`tesla_` convention). That broke the day a user's actual vehicle device was
also named "tesla" — the alias `sensor.tesla_odometer` ended up dynamically
constructing and reading `sensor.tesla_odometer` (itself), a self-reference
that gets stuck permanently on `unknown`/`unavailable`. `vehicle_` was chosen
as a fixed, structurally-separate namespace precisely so the alias's own
entity_id can never collide with the entity_id it dynamically builds from
`input_text.tesla_car_name` — **unless the user names their car exactly
`vehicle`**, which is the one remaining reserved word. A guard automation,
`tesla_reserved_car_name_guard` in `packages/tesla/automations.yaml`, fires a
`persistent_notification` if `input_text.tesla_car_name` is ever set to
`vehicle`, so this edge case fails loudly instead of silently.

**Rules for future agents when touching this layer:**
* Never let the alias layer's own fixed prefix equal a value the alias reads
  from user input. If you ever rename the alias namespace again (e.g. away
  from `vehicle_`), update `tesla_reserved_car_name_guard`'s condition to
  match the new reserved word, and update the README (Step 5) and
  `entities-list.txt` header note accordingly — all three must stay in sync.
* When adding a new raw Fleet attribute to the dashboards, add a matching
  `sensor.vehicle_*`/`binary_sensor.vehicle_*` alias in `configuration.yaml`
  first, reference the alias everywhere (not the literal `tesla_*` Fleet
  entity), and document the new alias in `entities-list.txt` under the
  "vehicle_ prefix" note near the top of that file.
* Downstream custom/derived sensors that are NOT raw Fleet pass-throughs
  (e.g. `sensor.tesla_daily_distance`, `sensor.tesla_efficiency_kwh_km`,
  `binary_sensor.tesla_driving_active`) correctly keep the `tesla_` prefix —
  only the raw alias layer uses `vehicle_`. Don't rename those.
* This is documented for end-users in `README.md` under "Step 5 — Check your
  entities" (section: *"Your vehicle's name/prefix can be anything"*) and in
  `entities-list.txt`'s header comment. Keep those three docs (`agents.md`,
  `README.md`, `entities-list.txt`) consistent whenever this layer changes —
  update all of them together, in the same commit, per the standard workflow
  in Section 1 of this file.

### 6. Writable Fleet Control Aliases (`vehicle_*` select/number domains)

**What it is:** the read-only `sensor.vehicle_*` / `binary_sensor.vehicle_*`
pattern above (Section 5) doesn't work for dashboard *controls* that need to
both display AND set a value — e.g. the Battery tab's Charge Limit slider
(`custom:mushroom-number-card`) or the Climate tab's steering wheel heater
button (`custom:button-card`). Those stock/HACS Lovelace cards can't
template their `entity:` key with Jinja/JS (unlike a button-card's `label:`,
which can), so a hardcoded `number.tesla_charge_limit` breaks the moment the
vehicle isn't literally named "tesla" — defeating the whole point of the
alias layer.

**The fix:** `configuration.yaml` also defines a small number of **writable**
template entities under `template: - select:` / `template: - number:` (not
just `- sensor:` / `- binary_sensor:`), currently:
* `number.vehicle_charge_limit` → forwards to `number.<car>_charge_limit`
* `number.vehicle_charge_current` → forwards to `number.<car>_charge_current`
* `select.vehicle_steering_wheel_heater` → forwards to `select.<car>_steering_wheel_heater`

Each one templates `state:` (and `min`/`max`/`step`/`options` where relevant)
for reads exactly like the sensor aliases, but additionally defines a
`set_value:` (for `number:`) or `select_option:` (for `select:`) action block
that re-dispatches the write to the real dynamic entity, e.g.:
```yaml
set_value:
  - action: number.set_value
    target:
      entity_id: >
        {% set car = states('input_text.tesla_car_name') %}
        number.{{ car }}_charge_limit
    data:
      value: "{{ value }}"
```
Dashboards then point `entity:` at the alias (`number.vehicle_charge_limit`),
which is safe to hardcode since it's a fixed, rename-proof name — same as the
read-only aliases.

**When to use this vs. the Section 5 pattern:** only add a writable
select/number alias when a *stock or HACS card* needs a static `entity:` for
a control (not just a label/state readout). If a `custom:button-card`'s
`label:`/`tap_action:` can already read the dynamic entity via
`states['domain.' + car + '_suffix']` (as most action buttons in this project
do, calling a `script.tesla_*` which itself resolves the car name), you don't
need a new alias — only the card's own `entity:` binding (used for the
default more-info popup / built-in color state) might still point at a
placeholder, which is a much lower-severity, cosmetic-only gap.

**Known remaining gap:** `media-control` (the Media Player card) and similar
stock cards with many templated attributes (play state, volume, track) don't
have a writable alias yet — building a full `template: media_player:` proxy
is significantly more complex (many attributes/services to forward) and was
deemed out of scope during the last audit pass. Its `entity:` still hardcodes
`media_player.tesla_media_player` with a `⚠️ update if car is renamed`
comment. Ask the user before investing in a full media_player template proxy.

### 7. Smart Charging Automation (anti-flapping off-peak window)

**What it is:** `input_boolean.tesla_enable_smart_charging` used to be a dead
toggle (no automation consumed it). It now drives two real automations in
`packages/tesla/automations.yaml`:
* `tesla_smart_charge_start` — starts charging once per day, either exactly
  at `input_datetime.tesla_smart_charge_window_start`, or immediately if the
  cable gets plugged in while already inside the window. Conditions: smart
  charging enabled, cable plugged in, not already charging, battery below
  `input_number.tesla_target_charge_limit`, and current time inside the
  configured window (overnight wrap, e.g. 23:00→06:00, handled via explicit
  `strptime`/time comparison — not just string comparison).
* `tesla_smart_charge_stop` — fires once per day at
  `input_datetime.tesla_smart_charge_window_end`; if still charging (target
  not reached in time), stops it so the rest isn't paid at peak rate.

**Anti-flapping design (explicit user requirement):** both automations use a
fixed daily `time` trigger — no polling loop, no `state`-trigger on battery
level, no repeated re-evaluation. That means **at most one start action and
one stop action per day**, satisfying the requirement that charging must not
switch on/off frequently (bad for the contactor/relay hardware). The vehicle
plugging in mid-window is the only second trigger on the start side, and it's
still gated by "not already charging" so it can't fire twice.

**Defense in depth:** before calling `script.tesla_charge_start`, the start
automation also pushes `input_number.tesla_target_charge_limit` into the
vehicle's real `number.<car>_charge_limit` via `number.set_value`. This means
the car's own onboard BMS — not this automation — is what actually caps
charging at the target %; the automation doesn't need to poll and manually
stop charging when the target is reached. `tesla_smart_charge_stop` only
exists to handle the case where the window closes *before* the target is hit.

**New helpers:** `input_datetime.tesla_smart_charge_window_start` (default
23:00:00) and `input_datetime.tesla_smart_charge_window_end` (default
06:00:00), both time-only (no date component). Exposed on the Analytics
dashboard's Settings tab (🌙 Smart Charging section) alongside the enable
toggle and target charge limit slider, so users configure this entirely via
UI — no Developer Tools needed. Deliberately new dedicated helpers rather
than parsing the existing free-text Saved Location Rate schedule strings
(e.g. `input_text.tesla_rate_home_hours`), which use human-typed en-dash
ranges too fragile to parse reliably for automation triggers.

### 8. Unit System Selector (`input_select.tesla_unit_system`)

**What it is:** a Settings-tab dropdown (Analytics → Settings → 📏 Unit
System) with three presets, not a plain Metric/Imperial toggle — because
real-world "Imperial" usage is inconsistent (US drivers use mi + °F + psi
together; UK/Ireland drivers commonly use mi + mph but *keep* °C and bar).
This mirrors the options on a real Tesla's own touchscreen, which lets you
set distance/speed, temperature, and pressure independently:
* `"Metric (km, °C, bar)"` (default)
* `"US Imperial (mi, °F, psi)"`
* `"UK (mi, °C, bar)"`

Four label-only sensors derive from it (`sensor.tesla_unit_distance`,
`_speed`, `_pressure`, `_temperature`) — these only hold the unit *string*;
they don't do any math. Energy/power/current (kWh/kW/A/V) are **not**
affected by this selector at all — that's universal across all EVs
regardless of region, so there was nothing to convert.

**Critical scope limitation — the underlying entities are NEVER
converted, only dashboard display is:** every `unit_of_measurement: "km"`
/ `"km/h"` / `"bar"` / `"°C"` you see on `sensor.vehicle_*` template
entities in `configuration.yaml` (Section 5's alias layer) is a permanent,
hardcoded static value — it does **not** read `input_select.tesla_unit_system`
and never will. This is intentional, not an oversight: these sensors have
`device_class`/`state_class` set for Home Assistant's Long-Term Statistics
(Energy dashboard, `statistics-graph` cards, history). Dynamically
templating a stats-tracked sensor's `unit_of_measurement` at runtime
triggers HA's "unit of measurement changed" repair/migration warnings and
can disrupt recorded statistics. So: **Developer Tools → States**, native
Logbook/History entries, and any plain `history-graph`/`statistics-graph`
card added outside the two custom dashboards will always show km/bar/°C,
regardless of the unit selector. Only the specific dashboard cards listed
below actually convert for display — everywhere else in Home Assistant,
these entities are metric-only by design. This distinction is documented
for the end user directly in the Settings tab's Unit System card text.

**Why this couldn't reuse the currency-selector pattern:** the currency
selector (`input_select.tesla_currency` + `sensor.tesla_currency_symbol`)
does **no math** — it only swaps a displayed symbol, because the user is
expected to type their electricity/fuel rates directly in their chosen
currency. Units are fundamentally different: the Tesla Fleet integration's
native sensors always report km/bar/°C, so switching to mi/psi/°F requires
actually multiplying the stored value, not just relabeling it. Conversion
constants used everywhere below: `km → mi` = `×0.621371` (same factor for
km/h → mph), `bar → psi` = `×14.5038`, `°C → °F` = `×9/5 + 32`.

**Where the conversion math actually lives:** inline in each individual
dashboard card, reading `input_select.tesla_unit_system` directly — via JS
(`states['input_select.tesla_unit_system']?.state` in `custom:button-card`
labels), Jinja (`states('input_select.tesla_unit_system')` in `markdown`
cards), or `transform:` (which has `hass` access, in `apexcharts-card`
series) — **not** through a shared conversion sensor. This is deliberately
duplicated rather than centralized, because a single generic "converted
value" sensor can't exist per quantity (there's no way to template a
generic input parameter into a HA template sensor); every displayed number
needed its own small inline conversion, matching whatever card type reads
it. Converted so far: the Overview dashboard's header battery/range readout,
Charging Status row 2, Info Grid Climate/Battery cards, footer odometer,
Battery tab RANGE row, Climate tab interior/outdoor temp + target-temp
stepper (display only — the actual `climate.set_temperature` step logic in
`script.tesla_climate_temp_up/down` stays hardcoded to 0.5°C internally,
since that's what the vehicle's API expects; only the *readout* converts),
and the Tires tab (banner + 4 wheel cards + historical pressure chart).
Also converted: the Analytics dashboard's History tab Today/This
Week/This Month distance figures.

**Known, documented limitation (flagged to the user, not silently
skipped):** the Analytics dashboard's **Driving** and **Charging** tabs
(14 `apexcharts-card` blocks pulling long-term statistics) still always
plot in km / km/h / Wh-per-km regardless of this selector. Converting those
properly would need per-series `transform:` conversion **and** duplicating
each chart's static `yaxis` min/max + axis title (which apexcharts-card
can't template), the same way the Tires-tab historical pressure chart was
handled below — i.e. wrapping each chart in a `type: conditional` pair. That
was judged too large/risky to do untested across 14 charts in one pass;
tackle it as a following, focused task if the user wants it, using the
Tires-tab chart (`dashboards/tesla-overview.yaml`, "Historical Pressure
Chart") as the reference pattern for how to pair `conditional` cards with a
`transform:`-adjusted series and matching axis bounds.

**Recommended tire pressure is now user-configurable, not hardcoded:** the
Tires tab's "Recommended cold pressure" banner used to hardcode `2.9 bar`
(`42 psi`) as a guess. Tesla's Fleet API does **not** expose a
manufacturer-recommended pressure — only each wheel's live reading — and
the correct value depends on wheel size (varies per vehicle/wheel combo,
printed on the driver's door placard), so it can't be derived from any
sensor. Fixed via `input_number.tesla_recommended_tire_pressure` (always
stored in bar; converted to psi for display via the same unit-system logic
as everywhere else), editable on the Analytics Settings tab ("🛞
Recommended Cold Tire Pressure"). Default 2.9 bar preserved as a
placeholder until the user enters their actual placard value.


