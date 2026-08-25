"""Shared bits for the entities this integration exposes."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GardenLightingCoordinator


class GardenLightingEntity(CoordinatorEntity[GardenLightingCoordinator]):
    """Base entity; groups everything for one config entry under one device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: GardenLightingCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name=coordinator.entry.title,
            manufacturer="Garden Lighting",
            entry_type=DeviceEntryType.SERVICE,
        )
