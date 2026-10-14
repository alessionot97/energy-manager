"""Native Home Assistant per-load control modes."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.entity import EntityCategory
from .const import DOMAIN, MODES


async def async_setup_entry(hass, entry, async_add_entities):
    manager = entry.runtime_data
    async_add_entities([LoadMode(manager, load) for load in manager.loads])


class LoadMode(SelectEntity):
    _attr_should_poll = False
    _attr_options = list(MODES)
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:autorenew"

    def __init__(self, manager, load):
        self.manager = manager
        self.load = load
        self._attr_name = f"Energy Manager {load['name']} modalità"
        self._attr_unique_id = f"{manager.entry.entry_id}_{load['id']}_mode"

    @property
    def current_option(self):
        return self.manager.modes.get(self.load["id"], "auto")

    async def async_select_option(self, option: str) -> None:
        if option not in MODES:
            raise ValueError("Unsupported mode")
        await self.manager.async_set_mode(self.load["id"], option)
        self.async_write_ha_state()

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.async_on_remove(self.manager.add_listener(self.async_write_ha_state))
