# 🚗 Tesla Dashboard for Home Assistant

A beautiful, **Tessie-app-inspired** Tesla dashboard for [Home Assistant](https://www.home-assistant.io/), built entirely with YAML, custom Lovelace cards, and optional [TeslaMate](https://github.com/teslamate-org/teslamate) integration for deep historical analytics.

This README is written for **everyone**, including people who have never touched Home Assistant's YAML files before. Follow it step by step and you'll have a working setup.

> Looking for the technical UI/UX spec used to build this (for AI coding agents / contributors)? See [`agents.md`](./agents.md).

---

## ✨ What you get

Two ready-made Lovelace dashboards, wired directly to your Tesla's native entities, styled to look and feel like the Tessie mobile app:

### 🧭 Tesla Overview dashboard
Six tabs covering everyday use of the car:
- **Dashboard** — the main cockpit: header with vehicle name + battery/range readout, a conditional "Charging" status card (time remaining, amps/volts/kW), a 6-button quick-action row (lock, climate, frunk, trunk, flash lights, more), a tap-to-open location strip, and an info grid (climate, battery, schedule, tires, drives, charges, idles, activity, automation, profiler) plus a vehicle specs footer (model, VIN, plate, firmware, odometer, alerts).
- **Controls** — window venting, sentry mode toggle, media playback, valet mode & speed limit.
- **Climate** — interior/exterior temperature readout, a seat-heater map for all 6 seats + steering wheel heater, a temperature stepper, and quick toggles for Dog Mode, Camp Mode, Bio Defense, Climate, Defrost, and Cabin Overheat Protection.
- **Battery** — battery level gauge, detailed telemetry table (range, drain, energy, pack temperature, amperage, voltage, lifetime energy used), a charge-limit slider, and start/stop charging + unlock charge port buttons.
- **Tires** — real-time pressure readout for all 4 wheels plus a historical pressure graph with color-coded safe/warning zones.
- **Cost Projections** — monthly/annual/5-year charging cost breakdown by network (home, Supercharger, other).

### 📊 Tesla Analytics dashboard
Four tabs for historical insight and configuration:
- **History** — a unified, chronological timeline of every drive, charge, and idle/standby session, each with time, location, distance/energy, battery % change, and cost — tap a drive for a detail popup with an interactive route map and speed/altitude chart.
- **Driving** — distance, real energy used, electric cost, duration, speed, drive count, and **real energy efficiency (Wh/km)** computed from actual battery-drop telemetry (not a fixed estimate), plus efficiency-vs-speed and efficiency-vs-temperature charts.
- **Charging** — charging session breakdowns and power/current charts.
- **Analytics** — a date-range selector (7 days / 30 days / 1 year / all time) driving KPI summary rows and a full suite of charts: cost comparison vs. a gas car, efficiency vs. speed, driving-time heatmaps, charging source breakdown, charging power curves, phantom-drain analysis, and macro vehicle-state (driving/charging/idling/sleeping) breakdowns.
- **Settings** — pick your **currency** (HUF/EUR/USD/GBP — all cost figures across both dashboards update instantly), set your electricity rate, fuel-comparison baseline, and edit your **Saved Location Rates** (Home / Solar-Off-Peak / Work — name, rate, hours, active days, season) directly from the dashboard, no YAML editing required.

### ⚙️ Plus
- A currency selector and per-location rate cards (editable straight from the Settings tab) so all cost/savings figures are shown and calculated in your own currency and tariffs — no more hardcoded Forints.
- Optional integration with **TeslaMate** for long-term trip/charge history and Grafana-powered stats.
- Everything displayed in **metric units** (km, km/h, bar, °C, kWh, kW/A/V) with your choice of **currency** — defaults to Hungarian Forint (HUF) but switchable in Settings.
- A fully documented entity inventory (`entities-list.txt`) so you always know which sensors/helpers power which card.
- A `scripts/rename_tesla_prefix.py` maintenance tool to safely rename the `tesla_` entity prefix project-wide (e.g. for a second vehicle) — see the Maintenance section below.

---

## 📋 Prerequisites

Before you start, make sure you have:

1. **A running Home Assistant instance** (Home Assistant OS, Supervised, Container, or Core — any install method works, but instructions below assume **Home Assistant OS/Supervised** since that gives you the Add-on store).
2. **A Tesla account** with the vehicle you want to track.
3. **The [Tesla Fleet integration](https://www.home-assistant.io/integrations/tesla_fleet/)** set up in Home Assistant (`Settings → Devices & Services → Add Integration → Tesla Fleet`). This is what actually talks to your car.
4. (Optional but recommended) A machine/server capable of running **Docker**, if you want the TeslaMate historical/analytics backend.

---

## 🧩 Step 1 — Install the required Home Assistant Add-ons

These add-ons let you edit files and access a terminal directly from the Home Assistant web UI — no need for a separate computer or SSH client.

Go to **Settings → Add-ons → Add-on Store** and install:

| Add-on | Why you need it |
| :--- | :--- |
| **File editor** (or **Studio Code Server**) | Lets you edit `configuration.yaml` and other YAML files from your browser. |
| **Terminal & SSH** | Gives you a command-line console inside Home Assistant (needed to copy files, run `git`, restart services, etc.). |
| **Samba share** *(optional)* | Lets you drag-and-drop files into the `/config` folder from your computer's file explorer instead of using the terminal. |

After installing, **start** each add-on and enable **"Show in sidebar"** so you can access them easily.

> 💡 If you're on Home Assistant Container/Core (no Supervisor), you don't have an Add-on Store — just use whatever tools you already use to edit files and access the server's shell (e.g. `docker exec`, `scp`, VS Code Remote, etc.).

---

## 🧩 Step 2 — Install HACS (Home Assistant Community Store)

Several dashboard cards used here are custom community cards, not built into Home Assistant. You install them via **HACS**.

1. Follow the official HACS installation guide: https://hacs.xyz/docs/use/download/download/
2. After installing, restart Home Assistant, then go to **Settings → Devices & Services → HACS** to finish the setup wizard (you'll need to log in with GitHub).

### Install these HACS frontend cards

Open **HACS → Frontend**, search for each of the following, and click **Download**:

| Card | Purpose |
| :--- | :--- |
| **Mushroom** | Modern, compact cards used throughout the dashboard (buttons, entities, gauges). |
| **apexcharts-card** | All the history/analytics graphs (battery, efficiency, charging power, heatmaps). |
| **button-card** | Custom seat-heater / quick-action buttons. |
| **card-mod** | Custom styling/theming tweaks used on some cards. |
| **browser_mod** *(optional)* | Powers popups like the "Drive Detail" modal on the Analytics dashboard. |

After downloading each card, **restart Home Assistant** once (Settings → System → Restart) so the new resources are registered.

---

## 🧩 Step 3 — Copy this repository into your Home Assistant `config` folder

Using the **Terminal & SSH** add-on (or Samba/File editor), copy the contents of this repository into your Home Assistant `/config` directory (the same folder that contains your existing `configuration.yaml`).

```bash
# Example using the Terminal & SSH add-on
cd /config
git clone https://github.com/eabris/homeassistant-tesla-dash.git tesla-dash-src

# Copy the relevant folders/files into your live config
cp -r tesla-dash-src/packages ./
cp -r tesla-dash-src/dashboards ./
cp -r tesla-dash-src/themes ./
cp -r tesla-dash-src/scripts ./
cp tesla-dash-src/entities-list.txt ./
```

> ⚠️ **Don't blindly overwrite your existing `configuration.yaml`!** Instead, open both files side by side (in File editor) and merge in the relevant sections shown in Step 4 below — you likely already have settings of your own you don't want to lose.

---

## 🧩 Step 4 — Wire everything up in `configuration.yaml`

Open your Home Assistant `configuration.yaml` (via the File editor add-on) and make sure it includes the following (merge with what you already have, don't duplicate keys like `automation:` if they already exist):

```yaml
# Load the Tesla-specific automations & scripts
automation: !include packages/tesla/automations.yaml
script: !include packages/tesla/scripts.yaml

# Register the two Tesla dashboards in the sidebar
lovelace:
  mode: storage
  dashboards:
    tesla-dashboard:
      mode: yaml
      title: Tesla Overview
      icon: mdi:car-electric
      show_in_sidebar: true
      filename: dashboards/tesla-overview.yaml
    tesla-analytics:
      mode: yaml
      title: Tesla Analytics
      icon: mdi:chart-line
      show_in_sidebar: true
      filename: dashboards/tesla-analytics.yaml
```

Then **restart Home Assistant** (Settings → System → Restart). If there are YAML errors, the File editor add-on (or **Settings → System → Logs**) will tell you exactly what line is wrong.

---

## 🧩 Step 5 — Check your entities

This repo assumes your Tesla entities exist under names like `sensor.tesla_battery_level`, `lock.tesla_doors`, etc. (created automatically by the Tesla Fleet integration).

1. Open `entities-list.txt` in this repo — it's the master inventory of every entity, helper, and template sensor this project expects.
2. In Home Assistant, go to **Developer Tools → States** and search for `tesla` to confirm your actual entity IDs match.
3. If your vehicle has a different name/prefix (e.g. `sensor.my_model_y_battery_level` instead of `sensor.tesla_...`), you'll need to either:
   - Rename the entities in Home Assistant (**Settings → Devices & Services → Entities**, click each one → Settings → change Entity ID), **or**
   - Adjust the templates in `packages/tesla/` and the dashboard YAML files to match your actual entity IDs.

---

## 🧩 Step 6 (Optional) — Set up TeslaMate for deep history & analytics

[TeslaMate](https://github.com/teslamate-org/teslamate) records long-term trip, charge, and idle history in its own database, and this repo's Analytics dashboard can pull from it via Grafana/MQTT for richer charts.

This requires **Docker** and **Docker Compose** on a machine that can stay on 24/7 (a Raspberry Pi, NAS, mini-PC, or the same server running Home Assistant Container).

1. Copy `.env_sample` to `.env` and fill in secure passwords/keys:
   ```bash
   cp .env_sample .env
   nano .env   # or open in File editor
   ```
   - `DB_PASSWORD`, `MQTT_PASSWORD`, `GRAFANA_PASSWORD` — set your own strong passwords.
   - `ENCRYPTION_KEY` — generate one with `openssl rand -hex 16`.
2. Start the stack:
   ```bash
   docker compose up -d
   ```
3. Open TeslaMate's setup wizard at `http://<your-server-ip>:4000` and log in with your Tesla account to start logging vehicle data.
4. Open Grafana at `http://<your-server-ip>:3000` (login: `admin` / the `GRAFANA_PASSWORD` you set) to explore the pre-built dashboards.
5. In Home Assistant, add the **MQTT integration** (`Settings → Devices & Services → Add Integration → MQTT`) pointing at the Mosquitto broker started by the compose file (`localhost:1883` or your Docker host's IP), using the `teslamate` / `MQTT_PASSWORD` credentials — this lets TeslaMate data flow into Home Assistant sensors too.

> This step is entirely optional — the core Tesla Overview/Analytics dashboards work fine using only the native Tesla Fleet integration.

---

## 📁 Project Layout

```
├── /configuration.yaml          # Your Home Assistant configuration
├── /packages/
│   └── tesla/                   # Tesla-specific sensors, helpers, scripts, automations
├── /dashboards/
│   ├── tesla-overview.yaml       # Main Tesla Lovelace dashboard
│   └── tesla-analytics.yaml      # Analytics Tesla Lovelace dashboard
├── /themes/                      # Custom Lovelace themes
├── /scripts/                     # Maintenance/cleanup Python scripts
├── /entities-list.txt            # Master inventory of every Tesla entity/helper (keep updated!)
├── /docker-compose.yml           # Optional TeslaMate + Grafana + MQTT stack
├── /.env_sample                  # Template for TeslaMate secrets (copy to .env)
├── /README.md                    # This file — human setup guide
└── /agents.md                    # Technical spec / instructions for AI coding agents
```

---

## 🔧 Maintenance

### Currency & Saved Location Rates

Go to **Tesla Analytics → Settings** to:
- Pick your **currency** (HUF, EUR, USD, GBP) — every cost figure across both dashboards (electricity cost, fuel comparison, savings, projections, history) switches instantly.
- Set your **default electricity rate** and **fuel comparison** baseline (ICE efficiency + fuel price) used in the actual cost calculations.
- Edit the **Saved Location Rates** cards (Home / Solar-Off-Peak / Work) — name, rate, hours, active days, season — directly from entity rows on the dashboard.

> ⚠️ Note: the Saved Location Rate cards are currently **informational/manual**
> — actual cost math on the dashboards still uses the single flat **Default
> Electricity Rate**, not automatic time-of-use or per-location rate
> switching. Use them to document your tariffs for now; smarter rate-aware
> calculations may come in a future update.

### Renaming the `tesla_` entity prefix

All entities/helpers in this project use a consistent lowercase `tesla_...`
prefix (e.g. `sensor.tesla_odometer`, `unique_id: tesla_driving_time_today_raw_v1`).
If you get a second car, or just want a different naming scheme, use:

```bash
# Preview changes only (safe, default — nothing is written):
python3 scripts/rename_tesla_prefix.py --new-prefix modely

# Apply the changes (originals are backed up first):
python3 scripts/rename_tesla_prefix.py --new-prefix modely --apply
```

It only touches lowercase `tesla_` machine identifiers (entity IDs, unique
IDs, automation IDs) — capitalized "Tesla" text in friendly names/comments is
left alone by default (pass `--include-labels` to rename those too). Run
`python3 scripts/rename_tesla_prefix.py --help` for full details.

> ❓ **"If I rename the prefix after a month of use, do I lose my logged
> stats?"** Short answer: **the raw history isn't deleted, but you lose
> continuity** — renaming an entity's ID makes Home Assistant treat it as a
> brand-new entity:
> - Its history/graphs and long-term statistics (used by Statistics Graph
>   cards, the Energy dashboard, and `apexcharts-card` history) start empty.
>   The old data still exists in the database under the old (now orphaned)
>   entity ID until it's purged by your normal retention settings, but it
>   won't show up merged into the renamed entity.
> - `utility_meter` helpers (the daily/weekly/monthly accumulators) reset
>   their current cycle to 0 if you rename them.
> - The lifetime real-efficiency accumulator
>   (`input_number.tesla_drive_energy_consumed_total_kwh`) restores from its
>   configured default (`0`) after a rename — the previously accumulated
>   total is not automatically carried over.
> - Old orphaned entities will show as `unavailable`; clean them up with
>   `scripts/cleanup_legacy_entities.py`.
>
> **If continuity matters to you:** before renaming, note the current value
> of `input_number.tesla_drive_energy_consumed_total_kwh` (Developer Tools →
> States), then manually set it back on the newly-named entity after
> restarting Home Assistant. Everything else (daily/weekly/monthly totals,
> charts) will simply start accumulating fresh under the new name.

---

## 🛠️ Troubleshooting

| Problem | Fix |
| :--- | :--- |
| Dashboard shows "Custom element doesn't exist" | You're missing a HACS card — revisit Step 2 and make sure you restarted Home Assistant after installing. |
| Entities show as `unavailable` | Check that the Tesla Fleet integration is connected and your car is online (Tesla vehicles sleep to save battery). |
| YAML errors after restart | Check **Settings → System → Logs**, or validate YAML in the File editor — usually an indentation issue. |
| Entity names don't match dashboard | See Step 5 — either rename your entities or edit the dashboard/template YAML to match. |
| TeslaMate can't connect to Tesla | Make sure you completed its browser-based Tesla login wizard at `http://<server-ip>:4000`. |

---

## 🙋 Getting Help

- Home Assistant Tesla Fleet docs: https://www.home-assistant.io/integrations/tesla_fleet/
- HACS docs: https://hacs.xyz/
- TeslaMate docs: https://docs.teslamate.org/
- For contributing to this repo or understanding the design spec in depth, read [`agents.md`](./agents.md).
