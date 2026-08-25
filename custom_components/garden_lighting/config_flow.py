"""Config and options flow for garden_lighting."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

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
    DOMAIN,
)


def _number(
    minimum: float,
    maximum: float,
    step: float,
    unit: str | None = None,
    mode: selector.NumberSelectorMode = selector.NumberSelectorMode.BOX,
) -> selector.NumberSelector:
    config = selector.NumberSelectorConfig(min=minimum, max=maximum, step=step, mode=mode)
    if unit is not None:
        config["unit_of_measurement"] = unit
    return selector.NumberSelector(config)


def _suggest(key: str, defaults: dict[str, Any]) -> dict[str, Any]:
    value = defaults.get(key)
    return {"suggested_value": value} if value is not None else {}


def _schema(defaults: dict[str, Any], include_name: bool) -> vol.Schema:
    fields: dict[Any, Any] = {}

    if include_name:
        fields[vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, "Garden Lighting"))] = (
            selector.TextSelector()
        )

    fields[vol.Required(CONF_LIGHTS, default=defaults.get(CONF_LIGHTS, []))] = (
        selector.EntitySelector(
            selector.EntitySelectorConfig(domain="light", multiple=True)
        )
    )
    fields[vol.Optional(CONF_WEATHER, description=_suggest(CONF_WEATHER, defaults))] = (
        selector.EntitySelector(selector.EntitySelectorConfig(domain="weather"))
    )

    fields[
        vol.Required(
            CONF_FADE_START_LUX, default=defaults.get(CONF_FADE_START_LUX, DEFAULT_FADE_START_LUX)
        )
    ] = _number(1, 100000, 1, "lx")
    fields[
        vol.Required(
            CONF_FADE_END_LUX, default=defaults.get(CONF_FADE_END_LUX, DEFAULT_FADE_END_LUX)
        )
    ] = _number(0.01, 10000, 0.1, "lx")

    fields[
        vol.Required(
            CONF_MIN_BRIGHTNESS, default=defaults.get(CONF_MIN_BRIGHTNESS, DEFAULT_MIN_BRIGHTNESS)
        )
    ] = _number(0, 100, 1, "%", selector.NumberSelectorMode.SLIDER)
    fields[
        vol.Required(
            CONF_MAX_BRIGHTNESS, default=defaults.get(CONF_MAX_BRIGHTNESS, DEFAULT_MAX_BRIGHTNESS)
        )
    ] = _number(1, 100, 1, "%", selector.NumberSelectorMode.SLIDER)

    fields[vol.Required(CONF_PERCEPTUAL, default=defaults.get(CONF_PERCEPTUAL, True))] = (
        selector.BooleanSelector()
    )
    fields[
        vol.Required(CONF_CLOUD_IMPACT, default=defaults.get(CONF_CLOUD_IMPACT, DEFAULT_CLOUD_IMPACT))
    ] = _number(0, 1, 0.05, None, selector.NumberSelectorMode.SLIDER)
    fields[
        vol.Required(
            CONF_UPDATE_INTERVAL, default=defaults.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        )
    ] = _number(5, 600, 5, "s")

    fields[vol.Required(CONF_COLOR_TEMP, default=defaults.get(CONF_COLOR_TEMP, False))] = (
        selector.BooleanSelector()
    )
    fields[
        vol.Required(CONF_COOL_KELVIN, default=defaults.get(CONF_COOL_KELVIN, DEFAULT_COOL_KELVIN))
    ] = _number(2000, 6500, 50, "K")
    fields[
        vol.Required(CONF_WARM_KELVIN, default=defaults.get(CONF_WARM_KELVIN, DEFAULT_WARM_KELVIN))
    ] = _number(1500, 6500, 50, "K")

    return vol.Schema(fields)


def _validate(user_input: dict[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}

    if not user_input.get(CONF_LIGHTS):
        errors[CONF_LIGHTS] = "no_lights"
    if user_input[CONF_FADE_START_LUX] <= user_input[CONF_FADE_END_LUX]:
        errors[CONF_FADE_START_LUX] = "start_below_end"
    if user_input[CONF_MIN_BRIGHTNESS] > user_input[CONF_MAX_BRIGHTNESS]:
        errors[CONF_MIN_BRIGHTNESS] = "min_above_max"
    if user_input.get(CONF_COLOR_TEMP) and user_input[CONF_WARM_KELVIN] > user_input[CONF_COOL_KELVIN]:
        errors[CONF_WARM_KELVIN] = "warm_above_cool"

    return errors


class GardenLightingConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up one garden-lighting group."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _validate(user_input)
            if not errors:
                data = dict(user_input)
                return self.async_create_entry(title=data.pop(CONF_NAME), data=data)

        return self.async_show_form(
            step_id="user",
            data_schema=_schema(user_input or {}, include_name=True),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return GardenLightingOptionsFlow(config_entry)


class GardenLightingOptionsFlow(OptionsFlow):
    """Change any of it afterwards."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _validate(user_input)
            if not errors:
                return self.async_create_entry(title="", data=user_input)

        defaults = {**self._entry.data, **self._entry.options, **(user_input or {})}
        return self.async_show_form(
            step_id="init",
            data_schema=_schema(defaults, include_name=False),
            errors=errors,
        )
