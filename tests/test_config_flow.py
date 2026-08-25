"""The config and options flows."""

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.garden_lighting.const import DOMAIN


async def _start(hass):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def test_user_flow_creates_an_entry(hass):
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Garden", "lights": ["light.garden"]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Garden"

    # The rest of the form has usable defaults, so it should be filled in.
    assert result["data"]["fade_start_lux"] == 300
    assert result["data"]["fade_end_lux"] == 3
    assert "name" not in result["data"]


async def test_rejects_an_inverted_fade_window(hass):
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Garden", "lights": ["light.garden"], "fade_start_lux": 2, "fade_end_lux": 50},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"fade_start_lux": "start_below_end"}


async def test_rejects_min_above_max_brightness(hass):
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Garden",
            "lights": ["light.garden"],
            "min_brightness_pct": 80,
            "max_brightness_pct": 20,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"min_brightness_pct": "min_above_max"}


async def test_rejects_a_colour_ramp_that_cools(hass):
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Garden",
            "lights": ["light.garden"],
            "color_temp_enabled": True,
            "cool_kelvin": 2200,
            "warm_kelvin": 4000,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"warm_kelvin": "warm_above_cool"}


async def test_options_flow_round_trips(hass, entry_data):
    entry = MockConfigEntry(domain=DOMAIN, title="Garden", data=entry_data)
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**entry_data, "fade_start_lux": 1000.0}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["fade_start_lux"] == 1000.0
