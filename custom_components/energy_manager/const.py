"""Constants and default settings for Energy Manager."""
from __future__ import annotations

DOMAIN = "energy_manager"
VERSION = "0.0.3"
PLATFORMS = ["sensor", "select", "number"]
MODES = ("auto", "on", "off")
TICK_SECONDS = 20

DEFAULTS = {
    "pcc_entity": "sensor.fotovoltaico_pcc_total_power",
    "battery_entity": "sensor.fotovoltaico_battery_power",
    "ev_power_entity": "sensor.wallbox_power",
    "boiler_power_entity": "sensor.boiler_power",
    "boiler_switch": "switch.boiler",
    "termo_switch": "switch.prese_lavanderia",
    "wallbox_helper": "input_boolean.wallbox",
    "wallbox_current_helper": "input_number.corrente_wallbox",
    "wallbox_coeff_helper": "input_number.wallbox_kw_per_amp",
    "evse_start": "rest_command.evse_start",
    "evse_stop": "rest_command.evse_stop",
    "evse_set_amp": "rest_command.evse_set_amp",
    "notify_entity": "notify.iphone_di_alessio",
    "boiler_force_at": "15:30",
    "boiler_cutoff": "16:00",
    "termo_grid_from": "16:00",
    "termo_grid_until": "20:00",
    "termo_grid_backup": True,
    "reserve_w": 250,
    "switch_on_stable_s": 180,
    "switch_off_stable_s": 300,
    "switch_min_on_s": 600,
    "switch_min_off_s": 300,
    "ev_min_off_s": 900,
    "ev_min_on_s": 900,
    "ev_current_step_s": 90,
    "ev_min_amp": 6,
    "ev_max_amp": 16,
    "ev_forced_amp": 6,
    "ev_watt_per_amp": 690,
}


def default_loads(settings: dict | None = None) -> list[dict]:
    """Return device configuration for the initial installation."""
    s = dict(DEFAULTS)
    s.update(settings or {})
    return [
        {"id": "boiler", "name": "Boiler", "kind": "boiler", "entity_id": s["boiler_switch"],
         "power_entity": s["boiler_power_entity"], "watts": 1200, "priority": 1},
        {"id": "wallbox", "name": "Wallbox OpenEVSE", "kind": "evse", "entity_id": s["wallbox_helper"],
         "power_entity": s["ev_power_entity"], "watts": 4140, "priority": 2},
        {"id": "termoarredo", "name": "Termoarredo", "kind": "switch", "entity_id": s["termo_switch"],
         "power_entity": "", "watts": 500, "priority": 3,
         "schedule_enabled": False, "schedule_start": "16:00", "schedule_end": "20:00",
         "schedule_inside": "on", "schedule_outside": "auto",
         "schedule_weekdays": "0,1,2,3,4,5,6", "require_boiler_done": True},
    ]
