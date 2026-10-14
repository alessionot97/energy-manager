"""Number entity for EV manual charging current."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.helpers.entity import EntityCategory
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    manager = entry.runtime_data
    if any(item["kind"] == "evse" for item in manager.loads):
        async_add_entities([ManualEvAmps(manager)])


class ManualEvAmps(NumberEntity):
    _attr_should_poll = False
    _attr_mode = NumberMode.SLIDER
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "A"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:ev-station"

    def __init__(self, manager):
        self.manager = manager
        self._attr_name = "Energy Manager corrente auto forzata"
        self._attr_unique_id = f"{manager.entry.entry_id}_forced_ev_amp"
        self._attr_native_min_value = int(manager.cfg["ev_min_amp"])
        self._attr_native_max_value = int(manager.cfg["ev_max_amp"])

    @property
    def native_value(self):
        return int(self.manager.ev_forced_amp)

    async def async_set_native_value(self, value: float):
        await self.manager.async_set_forced_amp(int(value))
        self.async_write_ha_state()

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.async_on_remove(self.manager.add_listener(self.async_write_ha_state))
