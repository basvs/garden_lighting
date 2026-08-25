"""Sensors that show what the model thinks, so the lamps are never a mystery."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import LIGHT_LUX, PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_CLEAR_SKY_LUX,
    ATTR_CLOUD_COVERAGE,
    ATTR_ELEVATION,
    ATTR_FADE_PROGRESS,
    ATTR_MANUAL_CONTROL,
)
from .entity import GardenLightingEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [NaturalIlluminanceSensor(coordinator), TargetBrightnessSensor(coordinator)]
    )


class NaturalIlluminanceSensor(GardenLightingEntity, SensorEntity):
    """The estimated daylight outside."""

    _attr_device_class = SensorDeviceClass.ILLUMINANCE
    _attr_native_unit_of_measurement = LIGHT_LUX
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "natural_illuminance")

    @property
    def native_value(self) -> float | None:
        if (data := self.coordinator.data) is None:
            return None
        # Spans eight orders of magnitude over a day, so keep the small end.
        return round(data.lux, 4) if data.lux < 1 else round(data.lux, 1)

    @property
    def extra_state_attributes(self) -> dict:
        if (data := self.coordinator.data) is None:
            return {}
        return {
            ATTR_ELEVATION: round(data.elevation, 3),
            ATTR_CLOUD_COVERAGE: data.cloud_coverage,
            ATTR_CLEAR_SKY_LUX: round(data.clear_sky_lux, 1),
        }


class TargetBrightnessSensor(GardenLightingEntity, SensorEntity):
    """Where the fade currently wants the lamps."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:brightness-6"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "target_brightness")

    @property
    def native_value(self) -> float | None:
        if (data := self.coordinator.data) is None:
            return None
        return round(data.brightness / 255 * 100, 1)

    @property
    def extra_state_attributes(self) -> dict:
        if (data := self.coordinator.data) is None:
            return {}
        return {
            ATTR_FADE_PROGRESS: round(data.progress, 4),
            ATTR_MANUAL_CONTROL: list(data.manual_control),
        }
