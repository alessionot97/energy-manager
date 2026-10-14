"""Diagnostic and power sensors for Energy Manager."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    manager = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ManagerSensor(manager, "net", "Surplus netto", "mdi:transmission-tower", "W"),
                        ManagerSensor(manager, "capacity", "Potenza gestibile", "mdi:solar-power", "W"),
                        ManagerSensor(manager, "reason", "Ultima decisione", "mdi:information-outline", None),
                        ManagerSensor(manager, "boiler", "Ciclo boiler", "mdi:water-boiler", None)])


class ManagerSensor(SensorEntity):
    _attr_should_poll = False

    def __init__(self, manager, key, name, icon, unit):
        self.manager = manager
        self.key = key
        self._attr_name = f"Energy Manager {name}"
        self._attr_unique_id = f"{manager.entry.entry_id}_sensor_{key}"
        self._attr_icon = icon
        self._attr_native_unit_of_measurement = unit
        if unit == "W":
            self._attr_device_class = SensorDeviceClass.POWER
            self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        value = self.manager.snapshot.get(self.key)
        if isinstance(value, (int, float)):
            return round(value)
        return value

    @property
    def extra_state_attributes(self):
        if self.key == "reason":
            return {"loads": self.manager.snapshot.get("loads", {}),
                    "battery_priority": True,
                    "ready_by": self.manager.cfg["boiler_cutoff"]}
        return None

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.async_on_remove(self.manager.add_listener(self.async_write_ha_state))
