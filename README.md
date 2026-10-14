# Energy Manager — 0.0.1 beta

Custom integration for Home Assistant to coordinate rooftop solar, home battery charging and household electrical loads with **one centralized arbiter**.

**This version controls real devices.** Turn off existing OpenEVSE, boiler and towel-heater automations **before** enabling Energy Manager. Never test high-current loads without appropriate electrical protections. Energy Manager is not a safety device.

## Supported in v0.0.1

- Native Home Assistant integration with onboarding and options UI (`Settings → Devices & services → Add integration → Energy Manager`).
- Manage loads: **add/edit/delete/reprioritize** any number of basic on/off switch loads, with measured or estimated consumption.
- **Optional per-load schedules and conditions**: start/end daily times (also across midnight), selected weekdays, forced ON/OFF or solar AUTO both inside and outside the window, an optional Home Assistant entity-state condition, and dependency on boiler completion. Manual ON/OFF always overrides these automatic rules.
- Three manual modes **auto/on/off** for *every* configured load using HA Select entities (including EVSE). Force ON overrides solar restrictions and can draw from grid; Force OFF immediately switches the device off.
- Solar-first budgeting: **battery charging has priority**. Solar export (positive PCC) only; battery discharge (negative battery power) is deducted. Battery charging is **not counted** as free surplus.
- Add measured running controllable loads back to the budget **once** when allocating, preventing self-induced switch oscillations. Controlled load priority is a numeric setting in the integration options.
- Hysteresis: 3-minute stable surplus before turning on, 5-minute deficit before turning off, and configurable minimum on/off periods. OpenEVSE starts only when available solar power covers at least 6A, with a default 690W per amp (three phases), plus safety margin; it adjusts 1A at a time with a minimum interval.
- **Boiler** opportunistically preheats with solar; if still unfinished at **15:30**, runs from grid until the thermostat signals completion, or until **16:00**. At or after 16:00, it stays OFF until the next day unless manually forced ON. The thermostat is detected by `sensor.boiler_power` returning below 100W for 3 minutes after heating (>35% nominal) was observed, or 8 minutes with no power draw since starting (assumes already warm). Do not disable the physical thermostat.
- **Towel warmer** can run after boiler completion using surplus; in the default **16:00–20:00** period it can run from grid even without solar. The latter is configurable in Options → Schedule. Outside its time window, it is automatically OFF from 20:00 until the next day (unless forced ON).
- Direct `rest_command.evse_set_amp`, `rest_command.evse_start`, `rest_command.evse_stop` execution: disabling legacy automations does not disable EVSE controls. The `input_boolean.wallbox` and `input_number.corrente_wallbox` helpers are maintained for state visibility.
- Notifications using `notify.send_message` only to `notify.iphone_di_alessio` by default.
- Dedicated sensors for **net available surplus**, **reclaimable managed capacity**, **last decision**, and **boiler cycle status**.
- Persistent modes, current limit, last switching times and boiler completion date across Home Assistant restarts.

## Per-load scheduling — universal controls

In **Configure → Add load** or **Configure → Select load to edit**, each load has these optional controls:

| Setting | Meaning |
|---|---|
| Enable schedule | Apply the time plan to this load |
| Start / end | Local recurring time window; e.g. 16:00–20:00 or 22:00–06:00 |
| Inside / outside | `auto`: solar surplus; `on`: force ON including grid power; `off`: force OFF |
| Weekdays | Comma-separated values: `0`=Monday, `1`=Tuesday, …, `6`=Sunday |
| Require boiler complete | Automatic operations are blocked until the boiler has finished its daily heating cycle |
| Condition entity / required state | Optional sensor, switch or binary sensor; automatic control is allowed only while its state matches (`on`, `off`, etc.) |

**Precedence:** manual Force OFF / Force ON > mandatory daily boiler cutoff (except manual Force ON) > conditional state / weekday and schedule > stable solar allocation. A schedule's forced ON is a deliberate request to use grid power; it has priority over solar-only opportunistic loads. A missing condition entity fails closed.

Example: for a towel heater that may run 16:00–20:00 without the sun *only after the boiler is hot*, edit the `Termoarredo` load, enable its schedule, select start `16:00`, end `20:00`, inside `on`, outside `off`, and **Require boiler complete**. To allow additional sunny heating earlier, set outside to `auto` instead.

Boiler-specific `15:30–16:00` fallback and `16:00` hard automatic cutoff continue to apply regardless of optional per-load times. To override the cutoff, deliberately set the boiler's manual selector to Force ON.

## Install manually

1. Copy `custom_components/energy_manager/` to your Home Assistant `/config/custom_components/energy_manager/` directory.
2. Restart Home Assistant.
3. Ensure `rest_command.evse_start`, `.evse_stop`, `.evse_set_amp` exist, and that they work **independently** of the old automations. Check all entity IDs in the initial setup.
4. **Disable old automations** controlling the same loads, especially "Wallbox controllo automatico" and the previous boiler/termoarredo solar controller. Keep necessary REST command definitions; only disable the old automations.
5. Add Energy Manager from Settings → Devices & services and select/configure your sensors and switches.
6. Confirm the power signs: **PCC >0 means export**, **battery >0 means charging**. If reversed, fix upstream in Home Assistant before enabling live operations.
7. In integration options configure schedule, loads/priorities, EVSE actions and thresholds. In Entities the selectors are named `Energy Manager <load> modalità`.

**If an old `input_boolean.wallbox` is ON but the physical EVSE was stopped outside HA, first reset the helper to OFF**; it is a software state, not guaranteed actual EVSE feedback. After installation, confirm the REST commands really start/stop OpenEVSE and check the reported `sensor.wallbox_power`.

## Defaults (adjust in options)

| Load | Typical power | Priority | Mode |
|---|---:|---:|---|
| Boiler | 1200 W | 1 | auto |
| OpenEVSE (6–16 A) | 4140W at 6A | 2 | auto |
| Towel warmer | 500 W | 3 | auto |

Battery charge has precedence over **all** managed loads by formula, not as a switch that Energy Manager controls. Scheduled 15:30–16:00 boiler heating and 16:00–20:00 towel warmer heating, and manual `on` modes, are treated as mandatory reservations regardless of dynamic numeric ordering.

### Existing settings assumed for your HA instance

- `sensor.fotovoltaico_pcc_total_power` (positive export)
- `sensor.fotovoltaico_battery_power` (positive battery charging)
- `switch.boiler`, `sensor.boiler_power`
- `switch.prese_lavanderia`
- `input_boolean.wallbox`, `sensor.wallbox_power`
- `input_number.corrente_wallbox`, `input_number.wallbox_kw_per_amp`
- `rest_command.evse_start`, `rest_command.evse_stop`, `rest_command.evse_set_amp`
- `notify.iphone_di_alessio`

Some names above are **assumptions inherited from earlier configurations**; verify them in Developer Tools → States. In particular, an input_boolean is a helper; direct REST actions are necessary to control the real wallbox.

## Implementation details and limitations

- In v0.0.1 only generic **on/off switches** can be added dynamically. Each supports optional scheduled hours, weekdays and an entity-state condition. A second EVSE or continuously variable HVAC load needs its own driver in a later release. The existing OpenEVSE driver is supported.
- Priority order is changed via **numeric position** in integration settings (not drag-and-drop).
- Optional condition entities compare the state as a string (e.g. `on`); advanced numeric comparisons, sunset events and a full rule-builder UI are planned for later versions.
- The 15:30 fallback gives a 30-minute heating opportunity, **not an absolute hot water temperature guarantee** if hot water was already drained, the heater is slow, a thermal safety trips, or measurement is inaccurate. The boiler shuts off by 16:00 regardless.
- The grid-backup towel-warmer window can be turned off. The towel warmer is intentionally allowed to draw grid power during that window if the boiler cycle was marked complete.
- An EV helper is not a physical feedback sensor; if HA restarts with inconsistent helper state, align the helper with real charger state before turning Auto on.
- REST command failures are recorded in the diagnostic sensor and HA logs; action failures do not force assumed success.
- Change priority/sensors at runtime through Options (the integration reloads when options change).
- The controller reads sensors every ~20 seconds, plus fast checks on manual-mode changes. It does not replace distribution board breakers, overcurrent protections or OpenEVSE's own safeguards.

## Development

```sh
python -m compileall -q custom_components
python -m pytest -q tests
```

MIT license. Initial beta release 0.0.1.
