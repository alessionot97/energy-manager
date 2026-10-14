"""Centralized solar-first load arbiter for Energy Manager.

This module REALLY calls Home Assistant switch and REST actions. Never run the
legacy OpenEVSE/boiler/termoarredo automations simultaneously with it.
"""
from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timedelta
import logging
import math
import time
from typing import Callable

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DEFAULTS, TICK_SECONDS, DOMAIN
from .policy import after, within, recompute_capacity, net_surplus, current_target, normalized_loads

_LOGGER = logging.getLogger(__name__)


class EnergyManager:
    """Makes a single coherent allocation across managed loads."""

    def __init__(self, hass: HomeAssistant, entry):
        self.hass = hass
        self.entry = entry
        self.cfg = dict(DEFAULTS) | dict(entry.data) | {k: v for k, v in entry.options.items() if k != "loads"}
        self.loads = normalized_loads(list(entry.options.get("loads", [])))
        self.modes: dict[str, str] = {}
        self.ev_forced_amp = int(self.cfg["ev_forced_amp"])
        self.boiler_done_date = ""
        self.boiler_heat_seen = False
        self.boiler_low_since: float | None = None
        self.boiler_started_at: float | None = None
        self.last_change: dict[str, float] = {}
        self.last_amp_change = 0.0
        self.actual_ev_amp = int(self.cfg["ev_min_amp"])
        self._on_since: dict[str, float] = {}
        self._off_since: dict[str, float] = {}
        self._listeners: set[Callable] = set()
        self._lock = asyncio.Lock()
        self._unsub = None
        self._store = Store(hass, 1, f"energy_manager.{entry.entry_id}")
        self.snapshot = {"net": None, "capacity": None, "reason": "Inizializzazione", "boiler": "in attesa", "loads": {}}

    async def async_initialize(self):
        saved = await self._store.async_load() or {}
        self.modes = {item["id"]: saved.get("modes", {}).get(item["id"], "auto") for item in self.loads}
        self.boiler_done_date = saved.get("boiler_done_date", "")
        self.ev_forced_amp = max(int(self.cfg["ev_min_amp"]), min(int(self.cfg["ev_max_amp"]),
                                                               int(saved.get("ev_forced_amp", self.ev_forced_amp))))
        self.last_change = saved.get("last_change", {})
        self.actual_ev_amp = int(self._state_number(self.cfg["wallbox_current_helper"]) or self.cfg["ev_min_amp"])
        self.actual_ev_amp = max(int(self.cfg["ev_min_amp"]), min(int(self.cfg["ev_max_amp"]), self.actual_ev_amp))

    async def _save(self):
        await self._store.async_save({
            "modes": self.modes, "boiler_done_date": self.boiler_done_date,
            "ev_forced_amp": self.ev_forced_amp, "last_change": self.last_change,
        })

    async def async_start(self):
        self._unsub = async_track_time_interval(self.hass, self._periodic, timedelta(seconds=TICK_SECONDS))
        self.hass.async_create_task(self._initial_tick())

    async def _initial_tick(self):
        # Allow HA to finish restoring switches and helpers after startup.
        await asyncio.sleep(6)
        await self.async_tick()

    def _periodic(self, _now):
        self.hass.async_create_task(self.async_tick())

    async def async_stop(self):
        if self._unsub:
            self._unsub()
            self._unsub = None
        async with self._lock:
            await self._save()

    def add_listener(self, func: Callable):
        self._listeners.add(func)
        return lambda: self._listeners.discard(func)

    def _broadcast(self):
        for cb in tuple(self._listeners):
            cb()

    async def async_set_mode(self, load_id: str, mode: str):
        if load_id not in self.modes or mode not in ("auto", "on", "off"):
            raise ValueError("Invalid mode")
        self.modes[load_id] = mode
        await self._save()
        self._broadcast()
        await self.async_tick()

    async def async_set_forced_amp(self, amps: int):
        self.ev_forced_amp = max(int(self.cfg["ev_min_amp"]), min(int(self.cfg["ev_max_amp"]), amps))
        await self._save()
        self._broadcast()
        await self.async_tick()

    def _state_number(self, entity: str | None) -> float | None:
        if not entity:
            return None
        state = self.hass.states.get(entity)
        if state is None or state.state in ("unknown", "unavailable", "none"):
            return None
        try:
            value = float(state.state)
            if not math.isfinite(value):
                return None
            unit = str(state.attributes.get("unit_of_measurement", "")).lower()
            return value * 1000 if unit == "kw" else value
        except (TypeError, ValueError):
            return None

    def _is_on(self, entity: str) -> bool:
        return self.hass.states.is_state(entity, "on")

    def _is_valid(self, entity: str) -> bool:
        state = self.hass.states.get(entity)
        return state is not None and state.state in ("on", "off")

    def _load_power(self, load: dict) -> float:
        if not self._is_on(load["entity_id"]):
            return 0
        power = self._state_number(load.get("power_entity"))
        if load["kind"] == "evse":
            power = self._state_number(self.cfg["ev_power_entity"])
            # 0 W means the vehicle is not actively charging, NOT 6A consumption.
            return max(0, power) if power is not None else self.actual_ev_amp * self._watts_per_amp()
        return max(0, power) if power is not None else float(load["watts"])

    def _watts_per_amp(self) -> float:
        kw = self._state_number(self.cfg["wallbox_coeff_helper"])
        # Input helper is in kW/A (0.69), not W.  _state_number changes
        # actual 'kW' units to W, but some helpers are unitless.
        if kw is not None:
            if kw < 10:
                kw *= 1000
            if 100 <= kw <= 2500:
                return kw
        return float(self.cfg["ev_watt_per_amp"])

    async def _service_entity(self, entity: str, on: bool):
        domain = "input_boolean" if entity.startswith("input_boolean.") else "switch"
        await self.hass.services.async_call(domain, "turn_on" if on else "turn_off",
                                            {"entity_id": entity}, blocking=True)

    async def _evse_service(self, setting: str, payload: dict | None = None):
        service_full = str(self.cfg[setting])
        if "." not in service_full:
            raise ValueError(f"Invalid action {service_full}")
        domain, action = service_full.split(".", 1)
        if not self.hass.services.has_service(domain, action):
            raise RuntimeError(f"Required Home Assistant action absent: {service_full}")
        await self.hass.services.async_call(domain, action, payload or {}, blocking=True)

    async def _notify(self, message: str):
        target = str(self.cfg.get("notify_entity", "")).strip()
        if not target:
            return
        try:
            await self.hass.services.async_call("notify", "send_message",
                                                {"title": "Energy Manager", "message": message},
                                                target={"entity_id": target}, blocking=True)
        except Exception as err:  # nosec: notifications must never disrupt the controller
            _LOGGER.warning("Energy Manager push failed: %s", err)

    async def _set_ev_current(self, amps: int, reason: str):
        amps = int(max(int(self.cfg["ev_min_amp"]), min(int(self.cfg["ev_max_amp"]), amps)))
        if amps == self.actual_ev_amp:
            return
        await self._evse_service("evse_set_amp", {"ampere": amps})
        self.actual_ev_amp = amps
        helper = self.cfg["wallbox_current_helper"]
        if self.hass.states.get(helper):
            await self.hass.services.async_call("input_number", "set_value",
                                                {"entity_id": helper, "value": amps}, blocking=True)
        self.last_amp_change = time.monotonic()
        self.snapshot["reason"] = f"Wallbox {amps} A: {reason}"
        await self._notify(f"Wallbox regolata a {amps} A. {reason}")

    async def _apply(self, load: dict, should_on: bool, reason: str):
        load_id = load["id"]
        entity = load["entity_id"]
        if not self._is_valid(entity):
            _LOGGER.warning("Cannot control unavailable %s (%s)", load_id, entity)
            self.snapshot["reason"] = f"Entità non disponibile: {entity}"
            return
        if self._is_on(entity) == should_on:
            return
        try:
            if load["kind"] == "evse":
                if should_on:
                    requested = self.ev_forced_amp if self.modes[load_id] == "on" else int(self.cfg["ev_min_amp"])
                    # Must command the real wallbox: input_boolean alone is insufficient.
                    await self._evse_service("evse_set_amp", {"ampere": requested})
                    self.actual_ev_amp = requested
                    if self.hass.states.get(self.cfg["wallbox_current_helper"]):
                        await self.hass.services.async_call("input_number", "set_value",
                            {"entity_id": self.cfg["wallbox_current_helper"], "value": requested}, blocking=True)
                    await self._evse_service("evse_start")
                    await self._service_entity(entity, True)
                else:
                    await self._evse_service("evse_stop")
                    await self._service_entity(entity, False)
            else:
                await self._service_entity(entity, should_on)
            self.last_change[load_id] = time.time()
            self._on_since.pop(load_id, None)
            self._off_since.pop(load_id, None)
            self.snapshot["reason"] = f"{load['name']} {'ON' if should_on else 'OFF'}: {reason}"
            await self._save()
            await self._notify(f"{load['name']} {'ACCESO' if should_on else 'SPENTO'}. {reason}")
        except Exception as err:
            _LOGGER.exception("Cannot change %s", load_id)
            self.snapshot["reason"] = f"ERRORE {load['name']}: {err}"
            await self._notify(f"Errore controllo {load['name']}: {err}")

    def _long_enough(self, load_id: str, seconds: int) -> bool:
        return time.time() - float(self.last_change.get(load_id, 0)) >= seconds

    def _stable(self, mapping: dict[str, float], load_id: str, value: bool, seconds: int, now: float) -> bool:
        if not value:
            mapping.pop(load_id, None)
            return False
        mapping.setdefault(load_id, now)
        return now - mapping[load_id] >= seconds

    async def _observe_boiler(self, now_mono: float, date: str):
        boiler = next((x for x in self.loads if x["kind"] == "boiler"), None)
        if boiler is None or self.boiler_done_date == date:
            return
        if not self._is_on(boiler["entity_id"]):
            self.boiler_started_at = None
            self.boiler_low_since = None
            self.boiler_heat_seen = False
            return
        if self.boiler_started_at is None:
            self.boiler_started_at = now_mono
        measured = self._state_number(boiler.get("power_entity") or self.cfg["boiler_power_entity"])
        if measured is None:
            return
        if measured > max(250, float(boiler["watts"]) * 0.35):
            self.boiler_heat_seen = True
            self.boiler_low_since = None
        elif measured < 100:
            if self.boiler_low_since is None:
                self.boiler_low_since = now_mono
            low_for = now_mono - self.boiler_low_since
            # Thermostat opened after heating, or was already satisfied at start.
            if (self.boiler_heat_seen and low_for >= 180) or (
                not self.boiler_heat_seen and low_for >= 480
                and now_mono - self.boiler_started_at >= 480
            ):
                self.boiler_done_date = date
                self.snapshot["reason"] = "Boiler: termostato soddisfatto, ciclo giornaliero concluso"
                await self._save()
                await self._notify("Boiler pronto: termostato non assorbe più energia. Bloccato fino a domani.")
        else:
            self.boiler_low_since = None

    def _scheduled_mode(self, load: dict, now: datetime) -> tuple[str, str]:
        """Resolve per-load condition + weekday/time rules for automatic mode.

        Manual on/off is handled by the caller and always takes precedence.
        Missing condition entities are considered false (fail closed).
        """
        condition_entity = str(load.get("condition_entity", "")).strip()
        if condition_entity:
            entity = self.hass.states.get(condition_entity)
            if entity is None or entity.state != str(load.get("condition_state", "on")):
                return "off", f"condizione non soddisfatta: {condition_entity}"
        if load.get("require_boiler_done", False) and load["kind"] != "boiler":
            if self.boiler_done_date != now.date().isoformat():
                return "off", "attesa completamento boiler"
        if not load.get("schedule_enabled", False):
            return "auto", "nessun orario applicato"
        try:
            weekdays = {int(day.strip()) for day in str(load.get("schedule_weekdays", "0,1,2,3,4,5,6")).split(",")}
            if now.weekday() not in weekdays:
                return "off", "giorno non abilitato"
            active = within(now, load.get("schedule_start", "16:00"), load.get("schedule_end", "20:00"))
            action = load.get("schedule_inside" if active else "schedule_outside", "auto")
            return (action if action in ("auto", "on", "off") else "off"), ("orario attivo" if active else "fuori orario")
        except (ValueError, TypeError):
            return "off", "configurazione orario non valida"

    async def async_tick(self):
        async with self._lock:
            await self._tick_locked()

    async def _tick_locked(self):
        now = dt_util.as_local(dt_util.utcnow())
        today = now.date().isoformat()
        mono = time.monotonic()
        await self._observe_boiler(mono, today)
        pcc = self._state_number(self.cfg["pcc_entity"])
        battery = self._state_number(self.cfg["battery_entity"])
        valid_meter = pcc is not None and battery is not None
        net = net_surplus(pcc, battery) if valid_meter else None
        active = sum(self._load_power(load) for load in self.loads)
        capacity = recompute_capacity(pcc, battery, active) if valid_meter else None
        self.snapshot["net"] = net
        self.snapshot["capacity"] = capacity
        self.snapshot["boiler"] = "completato" if self.boiler_done_date == today else (
            "chiuso alle 16" if after(now, self.cfg["boiler_cutoff"]) else "da riscaldare")
        self.snapshot["loads"] = {}

        # Mandatory schedules and manual Force ON are reserved first.
        # A schedule alone cannot bypass the daily 16:00 boiler cutoff.
        commitments: dict[str, str] = {}
        schedule_decisions = {load["id"]: self._scheduled_mode(load, now) for load in self.loads}
        for load in self.loads:
            load_id = load["id"]
            mode = self.modes.get(load_id, "auto")
            timed, description = schedule_decisions[load_id]
            boiler_blocked = load["kind"] == "boiler" and (
                self.boiler_done_date == today or after(now, self.cfg["boiler_cutoff"]))
            if mode == "on":
                commitments[load_id] = "forzatura manuale"
            elif mode == "auto" and not boiler_blocked and timed == "on":
                commitments[load_id] = f"accensione programmata: {description}"
            elif mode == "auto" and load["kind"] == "boiler" and not boiler_blocked \
                and timed != "off" and within(now, self.cfg["boiler_force_at"], self.cfg["boiler_cutoff"]):
                commitments[load_id] = "riscaldamento garantito 15:30–16:00"
            elif mode == "auto" and load_id == "termoarredo" and not load.get("schedule_enabled") \
                and bool(self.cfg["termo_grid_backup"]) and self.boiler_done_date == today \
                and within(now, self.cfg["termo_grid_from"], self.cfg["termo_grid_until"]):
                commitments[load_id] = "fascia riscaldamento dopo boiler completato"

        remaining = capacity if capacity is not None else -1e9
        plans: dict[str, tuple[bool, str, int | None]] = {}
        for load in self.loads:
            load_id = load["id"]
            timed, description = schedule_decisions[load_id]
            if load_id in commitments:
                plans[load_id] = (True, commitments[load_id],
                                  self.ev_forced_amp if load["kind"] == "evse" else None)
                remaining -= (self.ev_forced_amp * self._watts_per_amp() if load["kind"] == "evse"
                              else float(load["watts"]))
            elif self.modes.get(load_id) == "off":
                plans[load_id] = (False, "forzatura manuale OFF", None)
            elif load["kind"] == "boiler" and (self.boiler_done_date == today or after(now, self.cfg["boiler_cutoff"])):
                plans[load_id] = (False, "ciclo concluso / dopo le 16", None)
            elif timed == "off":
                plans[load_id] = (False, description, None)
            elif load_id == "termoarredo" and not load.get("schedule_enabled") and self.boiler_done_date != today:
                plans[load_id] = (False, "attesa fine riscaldamento boiler", None)
            elif load_id == "termoarredo" and not load.get("schedule_enabled") and after(now, self.cfg["termo_grid_until"]):
                plans[load_id] = (False, "fuori dalla fascia termoarredo", None)

        for load in self.loads:
            load_id = load["id"]
            if load_id in plans:
                continue
            mode = self.modes.get(load_id, "auto")
            if mode != "auto":
                continue
            on = self._is_on(load["entity_id"])
            margin = float(self.cfg["reserve_w"])
            if load["kind"] == "evse":
                watts_per_amp = self._watts_per_amp()
                target_amp = current_target(remaining, watts_per_amp,
                    int(self.cfg["ev_min_amp"]), int(self.cfg["ev_max_amp"]), margin)
                min_w = int(self.cfg["ev_min_amp"]) * watts_per_amp
                on_ready = self._stable(self._on_since, load_id,
                    valid_meter and target_amp >= int(self.cfg["ev_min_amp"]),
                    int(self.cfg["switch_on_stable_s"]), mono)
                off_ready = self._stable(self._off_since, load_id,
                    (not valid_meter) or remaining < min_w - margin,
                    int(self.cfg["switch_off_stable_s"]), mono)
                if on:
                    keep = not (off_ready and self._long_enough(load_id, int(self.cfg["ev_min_on_s"])))
                else:
                    keep = on_ready and self._long_enough(load_id, int(self.cfg["ev_min_off_s"]))
                requested = max(int(self.cfg["ev_min_amp"]), target_amp) if keep else None
                plans[load_id] = (keep, "ricarica FV modulata" if keep else "surplus insufficiente/stabilità", requested)
                if keep:
                    remaining -= (self.actual_ev_amp if on else int(self.cfg["ev_min_amp"])) * watts_per_amp
                continue
            nominal = float(load["watts"])
            # Once a switch is on, accept a small import temporarily and do
            # not demand its nominal consumption a second time.
            start_ready = self._stable(self._on_since, load_id,
                valid_meter and remaining >= nominal + margin,
                int(self.cfg["switch_on_stable_s"]), mono)
            stop_ready = self._stable(self._off_since, load_id,
                not valid_meter or remaining < nominal - margin,
                int(self.cfg["switch_off_stable_s"]), mono)
            if on:
                keep = not (stop_ready and self._long_enough(load_id, int(self.cfg["switch_min_on_s"])))
            else:
                keep = start_ready and self._long_enough(load_id, int(self.cfg["switch_min_off_s"]))
            plans[load_id] = (keep, "surplus stabile" if keep else "surplus insufficiente", None)
            if keep:
                remaining -= nominal

        # Stop (release power) first, then turn on newly authorized loads.
        for stage_on in (False, True):
            for load in self.loads:
                enabled, reason, _ = plans[load["id"]]
                self.snapshot["loads"][load["id"]] = {
                    "mode": self.modes.get(load["id"], "auto"),
                    "target": "on" if enabled else "off", "reason": reason,
                    "priority": load["priority"],
                }
                if enabled == stage_on:
                    await self._apply(load, enabled, reason)

        for load in self.loads:
            if load["kind"] != "evse" or not self._is_on(load["entity_id"]):
                continue
            enabled, reason, target_amp = plans[load["id"]]
            if not enabled:
                continue
            if self.modes[load["id"]] == "on":
                target_amp = self.ev_forced_amp
            if target_amp is None:
                continue
            if self.modes[load["id"]] == "auto":
                if mono - self.last_amp_change < int(self.cfg["ev_current_step_s"]):
                    continue
                target_amp = min(self.actual_ev_amp + 1, max(self.actual_ev_amp - 1, target_amp)) \
                    if target_amp > self.actual_ev_amp else max(self.actual_ev_amp - 1, target_amp)
            try:
                await self._set_ev_current(target_amp, reason)
            except Exception as err:
                _LOGGER.exception("EVSE amp change failed")
                self.snapshot["reason"] = f"ERRORE corrente EVSE: {err}"

        if not valid_meter:
            self.snapshot["reason"] = "Sensori rete/batteria non disponibili; carichi FV bloccati"
        self._broadcast()
