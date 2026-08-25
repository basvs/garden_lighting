"""Works out how much light is outside, and drives the lamps to match."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_MAX_COLOR_TEMP_KELVIN,
    ATTR_MIN_COLOR_TEMP_KELVIN,
    ATTR_SUPPORTED_COLOR_MODES,
    ATTR_TRANSITION,
    LightEntityFeature,
    brightness_supported,
    color_temp_supported,
)
from homeassistant.components.light import (
    DOMAIN as LIGHT_DOMAIN,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Context, Event, HomeAssistant, callback
from homeassistant.helpers.event import (
    EventStateChangedData,
    async_track_state_change_event,
)
from homeassistant.helpers.sun import get_astral_location
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from . import model
from .const import (
    CONF_CLOUD_IMPACT,
    CONF_COLOR_TEMP,
    CONF_COOL_KELVIN,
    CONF_FADE_END_LUX,
    CONF_FADE_START_LUX,
    CONF_LIGHTS,
    CONF_MAX_BRIGHTNESS,
    CONF_MIN_BRIGHTNESS,
    CONF_PERCEPTUAL,
    CONF_UPDATE_INTERVAL,
    CONF_WARM_KELVIN,
    CONF_WEATHER,
    DEFAULT_CLOUD_IMPACT,
    DEFAULT_COOL_KELVIN,
    DEFAULT_FADE_END_LUX,
    DEFAULT_FADE_START_LUX,
    DEFAULT_MAX_BRIGHTNESS,
    DEFAULT_MIN_BRIGHTNESS,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_WARM_KELVIN,
    MANUAL_TOLERANCE,
    SETTLE_GRACE,
)

_LOGGER = logging.getLogger(__name__)

# Weather entities expose this as a plain attribute; naming it directly keeps
# the weather component from becoming a dependency of ours.
ATTR_WEATHER_CLOUD_COVERAGE = "cloud_coverage"

_UNUSABLE = (STATE_UNAVAILABLE, STATE_UNKNOWN)


@dataclass(slots=True)
class GardenLightingState:
    """Everything one pass of the model worked out."""

    elevation: float
    cloud_coverage: float | None
    clear_sky_lux: float
    lux: float
    progress: float
    brightness: int
    color_temp_kelvin: int | None
    manual_control: tuple[str, ...]


class GardenLightingCoordinator(DataUpdateCoordinator[GardenLightingState]):
    """Recomputes the fade on a timer and pushes it to the lights."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        interval = int(self._option_from(entry, CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
        super().__init__(
            hass,
            _LOGGER,
            name=entry.title,
            update_interval=timedelta(seconds=interval),
        )
        self.enabled = True
        # Nothing reaches the lights until the master switch has restored its
        # state. The first refresh happens before the switch platform loads, so
        # without this a restart would drive the lights for a few hundred
        # milliseconds before finding out the fade had been switched off.
        self._armed = False
        self._manual: set[str] = set()
        # Our own service calls come back to us as state changes; remembering
        # the contexts we issued is how we tell our changes from a person's.
        self._contexts: deque[str] = deque(maxlen=128)
        self._commanded: dict[str, tuple[int, float]] = {}
        self._unsub_state: Any = None

    @staticmethod
    def _option_from(entry: ConfigEntry, key: str, default: Any) -> Any:
        return {**entry.data, **entry.options}.get(key, default)

    def _opt(self, key: str, default: Any) -> Any:
        return self._option_from(self.entry, key, default)

    @property
    def lights(self) -> list[str]:
        return list(self._opt(CONF_LIGHTS, []))

    @property
    def transition(self) -> int:
        """Glide over a whole update interval, so the discrete steps vanish."""
        return int(self._opt(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))

    @property
    def manual_control(self) -> tuple[str, ...]:
        return tuple(sorted(self._manual))

    @callback
    def async_start(self) -> None:
        self._unsub_state = async_track_state_change_event(
            self.hass, self.lights, self._async_light_changed
        )

    async def async_shutdown(self) -> None:
        if self._unsub_state is not None:
            self._unsub_state()
            self._unsub_state = None
        await super().async_shutdown()

    @callback
    def async_arm(self, enabled: bool) -> None:
        """Start driving lights, once the master switch knows what it is.

        Called by the switch entity as it restores, and nowhere else. Until it
        happens nothing is sent to any light, so a light is never touched on the
        strength of a default we are about to overwrite.
        """
        self._armed = True
        self.enabled = enabled
        self.hass.async_create_task(self.async_refresh())

    @callback
    def async_set_enabled(self, enabled: bool) -> None:
        """Turn the whole thing on or off.

        Switching it off touches nothing: the lights are left exactly as they
        are, neither switched off nor held. Switching it back on is an explicit
        "take over again", so what was flagged as hand-controlled comes back to
        us, and what we last sent is forgotten so control is asserted afresh.
        """
        self.enabled = enabled
        if enabled:
            self._manual.clear()
            self._commanded.clear()
        # Deliberately not the debounced request_refresh: a person flipping this
        # switch should not wait out a cooldown.
        self.hass.async_create_task(self.async_refresh())

    @callback
    def async_reset_manual_control(self, entity_ids: list[str] | None = None) -> None:
        if entity_ids:
            self._manual.difference_update(entity_ids)
        else:
            self._manual.clear()
        self.hass.async_create_task(self.async_refresh())

    def _solar_elevation(self) -> float:
        try:
            location, elevation_m = get_astral_location(self.hass)
            return float(location.solar_elevation(dt_util.utcnow(), elevation_m))
        except Exception as err:  # noqa: BLE001 - astral raises a variety of things
            _LOGGER.debug("astral could not give an elevation (%s), falling back to sun.sun", err)

        sun = self.hass.states.get("sun.sun")
        if sun is not None and (value := sun.attributes.get("elevation")) is not None:
            return float(value)
        raise UpdateFailed("no solar elevation available; is the location set?")

    def _cloud_coverage(self) -> float | None:
        entity_id = self._opt(CONF_WEATHER, None)
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in _UNUSABLE:
            return None
        value = state.attributes.get(ATTR_WEATHER_CLOUD_COVERAGE)
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    async def _async_update_data(self) -> GardenLightingState:
        elevation = self._solar_elevation()
        coverage = self._cloud_coverage()

        clear_sky_lux = model.clear_sky_illuminance(elevation)
        lux = model.natural_illuminance(
            elevation, coverage, float(self._opt(CONF_CLOUD_IMPACT, DEFAULT_CLOUD_IMPACT))
        )
        progress = model.fade_progress(
            lux,
            float(self._opt(CONF_FADE_START_LUX, DEFAULT_FADE_START_LUX)),
            float(self._opt(CONF_FADE_END_LUX, DEFAULT_FADE_END_LUX)),
        )
        brightness = model.target_brightness(
            progress,
            float(self._opt(CONF_MIN_BRIGHTNESS, DEFAULT_MIN_BRIGHTNESS)),
            float(self._opt(CONF_MAX_BRIGHTNESS, DEFAULT_MAX_BRIGHTNESS)),
            bool(self._opt(CONF_PERCEPTUAL, True)),
        )
        kelvin = (
            model.target_color_temp(
                progress,
                int(self._opt(CONF_COOL_KELVIN, DEFAULT_COOL_KELVIN)),
                int(self._opt(CONF_WARM_KELVIN, DEFAULT_WARM_KELVIN)),
            )
            if self._opt(CONF_COLOR_TEMP, False)
            else None
        )

        # Daylight is back: every evening starts from a clean slate.
        if progress <= 0.0 and self._manual:
            _LOGGER.debug("daylight returned, clearing manual control on %s", self.manual_control)
            self._manual.clear()

        state = GardenLightingState(
            elevation=elevation,
            cloud_coverage=coverage,
            clear_sky_lux=clear_sky_lux,
            lux=lux,
            progress=progress,
            brightness=brightness,
            color_temp_kelvin=kelvin,
            manual_control=self.manual_control,
        )

        if self._armed and self.enabled:
            await self._async_apply(state)
        return state

    async def _async_apply(self, state: GardenLightingState) -> None:
        entity_ids = self.lights
        results = await asyncio.gather(
            *(self._async_apply_one(entity_id, state) for entity_id in entity_ids),
            return_exceptions=True,
        )
        for entity_id, result in zip(entity_ids, results):
            if isinstance(result, Exception):
                _LOGGER.warning("could not set %s: %s", entity_id, result)

    async def _async_apply_one(self, entity_id: str, state: GardenLightingState) -> None:
        if entity_id in self._manual:
            return

        current = self.hass.states.get(entity_id)
        if current is None or current.state in _UNUSABLE:
            return

        commanded = self._commanded.get(entity_id)
        is_on = current.state == STATE_ON

        # Nothing new to say, and the light is still where we left it.
        if (
            commanded is not None
            and commanded[0] == state.brightness
            and is_on == (state.brightness > 0)
        ):
            return

        context = Context()
        self._contexts.append(context.id)
        supports_transition = bool(
            current.attributes.get(ATTR_SUPPORTED_FEATURES, 0) & LightEntityFeature.TRANSITION
        )

        if state.brightness <= 0:
            if is_on:
                off_data: dict[str, Any] = {ATTR_ENTITY_ID: entity_id}
                if supports_transition:
                    off_data[ATTR_TRANSITION] = self.transition
                await self.hass.services.async_call(
                    LIGHT_DOMAIN, SERVICE_TURN_OFF, off_data, blocking=True, context=context
                )
            self._commanded[entity_id] = (0, time.monotonic())
            return

        modes = current.attributes.get(ATTR_SUPPORTED_COLOR_MODES) or []
        data: dict[str, Any] = {ATTR_ENTITY_ID: entity_id}
        if brightness_supported(modes):
            data[ATTR_BRIGHTNESS] = state.brightness
        if state.color_temp_kelvin is not None and color_temp_supported(modes):
            kelvin = state.color_temp_kelvin
            if (low := current.attributes.get(ATTR_MIN_COLOR_TEMP_KELVIN)) is not None:
                kelvin = max(kelvin, int(low))
            if (high := current.attributes.get(ATTR_MAX_COLOR_TEMP_KELVIN)) is not None:
                kelvin = min(kelvin, int(high))
            data[ATTR_COLOR_TEMP_KELVIN] = kelvin
        if supports_transition:
            data[ATTR_TRANSITION] = self.transition

        await self.hass.services.async_call(
            LIGHT_DOMAIN, SERVICE_TURN_ON, data, blocking=True, context=context
        )
        self._commanded[entity_id] = (state.brightness, time.monotonic())

    @callback
    def _async_light_changed(self, event: Event[EventStateChangedData]) -> None:
        """Notice somebody taking a light off us, and stop fighting them."""
        if event.context.id in self._contexts:
            return

        entity_id = event.data["entity_id"]
        if entity_id in self._manual:
            return

        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in _UNUSABLE:
            return

        commanded = self._commanded.get(entity_id)
        if commanded is None:
            # We have not told this light anything yet, so nothing contradicts us.
            return

        target, issued_at = commanded
        if time.monotonic() - issued_at < self.transition + SETTLE_GRACE:
            # Still gliding towards what we asked for; its interim reports are
            # not somebody reaching for the switch.
            return

        if new_state.state != STATE_ON:
            if target > 0:
                self._flag_manual(entity_id, "it was switched off")
            return

        if target <= 0:
            self._flag_manual(entity_id, "it was switched on")
            return

        brightness = new_state.attributes.get(ATTR_BRIGHTNESS)
        if brightness is not None and abs(int(brightness) - target) > MANUAL_TOLERANCE:
            self._flag_manual(entity_id, f"brightness is {brightness}, we asked for {target}")

    @callback
    def _flag_manual(self, entity_id: str, reason: str) -> None:
        self._manual.add(entity_id)
        _LOGGER.debug("leaving %s alone: %s", entity_id, reason)
        self.async_update_listeners()
