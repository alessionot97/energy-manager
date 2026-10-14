"""Onboarding and editable load management through Home Assistant UI."""
from __future__ import annotations

import re
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import DEFAULTS, DOMAIN, default_loads


def ent(domain: str | None = None):
    return selector.EntitySelector(selector.EntitySelectorConfig(domain=domain))


def txt():
    return selector.TextSelector()


def integer(low: int = 0, high: int = 100000):
    return selector.NumberSelector(selector.NumberSelectorConfig(
        min=low, max=high, step=1, mode=selector.NumberSelectorMode.BOX))


class EnergyManagerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors = {}
        if user_input is not None:
            await self.async_set_unique_id("energy_manager_main")
            self._abort_if_unique_id_configured()
            if user_input["pcc_entity"] == user_input["battery_entity"]:
                errors["base"] = "same_sensors"
            else:
                return self.async_create_entry(
                    title="Energy Manager", data=user_input,
                    options={"loads": default_loads(user_input)},
                )
        schema = vol.Schema({
            vol.Required("pcc_entity", default=DEFAULTS["pcc_entity"]): ent("sensor"),
            vol.Required("battery_entity", default=DEFAULTS["battery_entity"]): ent("sensor"),
            vol.Required("boiler_switch", default=DEFAULTS["boiler_switch"]): ent("switch"),
            vol.Required("boiler_power_entity", default=DEFAULTS["boiler_power_entity"]): ent("sensor"),
            vol.Required("termo_switch", default=DEFAULTS["termo_switch"]): ent("switch"),
            vol.Required("wallbox_helper", default=DEFAULTS["wallbox_helper"]): ent("input_boolean"),
            vol.Required("ev_power_entity", default=DEFAULTS["ev_power_entity"]): ent("sensor"),
            vol.Required("notify_entity", default=DEFAULTS["notify_entity"]): txt(),
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return EnergyManagerOptionsFlow()


class EnergyManagerOptionsFlow(config_entries.OptionsFlow):
    def __init__(self):
        self._options = None
        self._editing = None

    @property
    def opts(self):
        if self._options is None:
            self._options = dict(self.config_entry.options)
            self._options.setdefault("loads", default_loads(self.config_entry.data))
        return self._options

    @property
    def cfg(self):
        return dict(DEFAULTS) | dict(self.config_entry.data) | self.opts

    def _save(self):
        return self.async_create_entry(title="", data=self.opts)

    def _sorted(self):
        return sorted(self.opts["loads"], key=lambda x: (int(x["priority"]), x["id"]))

    def _reorder(self):
        for idx, item in enumerate(self._sorted(), start=1):
            item["priority"] = idx

    def _ids(self):
        return {load["id"]: f"{load['priority']}. {load['name']}" for load in self._sorted()}

    async def async_step_init(self, user_input=None):
        return self.async_show_menu(step_id="init", menu_options=[
            "general", "schedule", "evse", "notifications",
            "add_load", "choose_edit", "choose_remove", "priority",
        ])

    async def async_step_general(self, user_input=None):
        if user_input is not None:
            self.opts.update(user_input)
            return self._save()
        c = self.cfg
        return self.async_show_form(step_id="general", data_schema=vol.Schema({
            vol.Required("pcc_entity", default=c["pcc_entity"]): ent("sensor"),
            vol.Required("battery_entity", default=c["battery_entity"]): ent("sensor"),
            vol.Required("reserve_w", default=c["reserve_w"]): integer(0, 2000),
            vol.Required("switch_on_stable_s", default=c["switch_on_stable_s"]): integer(20, 1800),
            vol.Required("switch_off_stable_s", default=c["switch_off_stable_s"]): integer(20, 1800),
            vol.Required("switch_min_on_s", default=c["switch_min_on_s"]): integer(0, 3600),
            vol.Required("switch_min_off_s", default=c["switch_min_off_s"]): integer(0, 3600),
        }))

    async def async_step_schedule(self, user_input=None):
        if user_input is not None:
            self.opts.update(user_input)
            return self._save()
        c = self.cfg
        return self.async_show_form(step_id="schedule", data_schema=vol.Schema({
            vol.Required("boiler_force_at", default=c["boiler_force_at"]): selector.TimeSelector(),
            vol.Required("boiler_cutoff", default=c["boiler_cutoff"]): selector.TimeSelector(),
            vol.Required("termo_grid_from", default=c["termo_grid_from"]): selector.TimeSelector(),
            vol.Required("termo_grid_until", default=c["termo_grid_until"]): selector.TimeSelector(),
            vol.Required("termo_grid_backup", default=c["termo_grid_backup"]): bool,
        }))

    async def async_step_evse(self, user_input=None):
        if user_input is not None:
            self.opts.update(user_input)
            return self._save()
        c = self.cfg
        return self.async_show_form(step_id="evse", data_schema=vol.Schema({
            vol.Required("ev_power_entity", default=c["ev_power_entity"]): ent("sensor"),
            vol.Required("wallbox_helper", default=c["wallbox_helper"]): ent("input_boolean"),
            vol.Required("wallbox_current_helper", default=c["wallbox_current_helper"]): ent("input_number"),
            vol.Required("wallbox_coeff_helper", default=c["wallbox_coeff_helper"]): ent("input_number"),
            vol.Required("evse_start", default=c["evse_start"]): txt(),
            vol.Required("evse_stop", default=c["evse_stop"]): txt(),
            vol.Required("evse_set_amp", default=c["evse_set_amp"]): txt(),
            vol.Required("ev_min_amp", default=c["ev_min_amp"]): integer(1, 32),
            vol.Required("ev_max_amp", default=c["ev_max_amp"]): integer(1, 32),
            vol.Required("ev_min_off_s", default=c["ev_min_off_s"]): integer(0, 7200),
            vol.Required("ev_min_on_s", default=c["ev_min_on_s"]): integer(0, 7200),
            vol.Required("ev_current_step_s", default=c["ev_current_step_s"]): integer(20, 900),
        }))

    async def async_step_notifications(self, user_input=None):
        if user_input is not None:
            self.opts.update(user_input)
            return self._save()
        c = self.cfg
        return self.async_show_form(step_id="notifications", data_schema=vol.Schema({
            vol.Required("notify_entity", default=c["notify_entity"]): txt(),
        }))

    async def async_step_add_load(self, user_input=None):
        errors = {}
        if user_input is not None:
            slug = re.sub(r"[^a-z0-9]+", "_", user_input["name"].lower()).strip("_")
            if not slug or slug in self._ids():
                errors["base"] = "duplicate_load"
            else:
                self.opts["loads"].append({
                    "id": slug, "name": user_input["name"], "kind": "switch",
                    "entity_id": user_input["entity_id"],
                    "power_entity": user_input.get("power_entity", ""),
                    "watts": int(user_input["watts"]),
                    "priority": int(user_input["priority"]),
                })
                self._reorder()
                return self._save()
        return self.async_show_form(step_id="add_load", errors=errors, data_schema=vol.Schema({
            vol.Required("name"): txt(),
            vol.Required("entity_id"): ent("switch"),
            vol.Optional("power_entity"): ent("sensor"),
            vol.Required("watts", default=500): integer(1, 15000),
            vol.Required("priority", default=len(self._ids()) + 1): integer(1, 100),
        }))

    async def async_step_choose_edit(self, user_input=None):
        if user_input is not None:
            self._editing = user_input["load_id"]
            return await self.async_step_edit_load()
        return self.async_show_form(step_id="choose_edit", data_schema=vol.Schema({
            vol.Required("load_id"): vol.In(self._ids()),
        }))

    async def async_step_edit_load(self, user_input=None):
        load = next(x for x in self.opts["loads"] if x["id"] == self._editing)
        if user_input is not None:
            load.update({"name": user_input["name"], "entity_id": user_input["entity_id"],
                         "power_entity": user_input.get("power_entity", ""),
                         "watts": int(user_input["watts"]),
                         "priority": int(user_input["priority"])})
            self._reorder()
            return self._save()
        schema = {
            vol.Required("name", default=load["name"]): txt(),
            vol.Required("entity_id", default=load["entity_id"]): ent("input_boolean" if load["kind"] == "evse" else "switch"),
            vol.Required("watts", default=load["watts"]): integer(1, 15000),
            vol.Required("priority", default=load["priority"]): integer(1, 100),
        }
        if load.get("power_entity"):
            schema[vol.Optional("power_entity", default=load["power_entity"])] = ent("sensor")
        else:
            schema[vol.Optional("power_entity")] = ent("sensor")
        return self.async_show_form(step_id="edit_load", data_schema=vol.Schema(schema))

    async def async_step_choose_remove(self, user_input=None):
        if user_input is not None:
            self.opts["loads"] = [x for x in self.opts["loads"] if x["id"] != user_input["load_id"]]
            self._reorder()
            return self._save()
        return self.async_show_form(step_id="choose_remove", data_schema=vol.Schema({
            vol.Required("load_id"): vol.In(self._ids()),
        }))

    async def async_step_priority(self, user_input=None):
        if user_input is not None:
            item = next(x for x in self.opts["loads"] if x["id"] == user_input["load_id"])
            arr = [x for x in self._sorted() if x["id"] != item["id"]]
            arr.insert(min(max(1, int(user_input["priority"])), len(arr) + 1) - 1, item)
            for idx, load in enumerate(arr, 1):
                load["priority"] = idx
            return self._save()
        return self.async_show_form(step_id="priority", data_schema=vol.Schema({
            vol.Required("load_id"): vol.In(self._ids()),
            vol.Required("priority", default=1): integer(1, max(1, len(self._ids()))),
        }))
