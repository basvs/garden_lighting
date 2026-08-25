"""The master switch: whether we are driving the lamps at all."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .entity import GardenLightingEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([GardenLightingSwitch(entry.runtime_data)])


class GardenLightingSwitch(GardenLightingEntity, SwitchEntity, RestoreEntity):
    """Turn the fade off to leave the garden lights entirely alone."""

    _attr_icon = "mdi:weather-sunset-down"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "enabled")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Survive a restart in whatever state it was left, defaulting to on for
        # a fresh install. This is also what lets the coordinator start driving
        # lights at all -- it deliberately does nothing until told.
        last = await self.async_get_last_state()
        self.coordinator.async_arm(last is None or last.state != STATE_OFF)

    @property
    def is_on(self) -> bool:
        return self.coordinator.enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.coordinator.async_set_enabled(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.coordinator.async_set_enabled(False)
        self.async_write_ha_state()
