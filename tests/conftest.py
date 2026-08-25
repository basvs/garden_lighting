"""Fixtures for the Home Assistant level tests."""

import pytest
from homeassistant.const import STATE_OFF
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.garden_lighting.const import DOMAIN
from custom_components.garden_lighting.coordinator import GardenLightingCoordinator

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant see custom_components/ during tests."""
    yield


@pytest.fixture
def entry_data():
    return {
        "lights": ["light.garden"],
        "fade_start_lux": 300.0,
        "fade_end_lux": 3.0,
        "min_brightness_pct": 1.0,
        "max_brightness_pct": 100.0,
        "perceptual_ramp": True,
        "cloud_impact": 1.0,
        "update_interval": 30,
        "color_temp_enabled": False,
        "cool_kelvin": 4000,
        "warm_kelvin": 2200,
    }


@pytest.fixture
def dimmable():
    """A plain dimmable lamp: no transition support, no colour temperature."""
    return {
        "supported_color_modes": ["brightness"],
        "supported_features": 0,
        "friendly_name": "Garden",
    }


@pytest.fixture
def at_elevation(monkeypatch):
    """Pin the sun wherever a test needs it."""

    def _set(degrees):
        monkeypatch.setattr(
            GardenLightingCoordinator, "_solar_elevation", lambda self: float(degrees)
        )

    return _set


@pytest.fixture
def setup_entry(hass, entry_data, dimmable):
    """Set up one configured entry driving a single garden light."""

    async def _setup(*, light_state=STATE_OFF, attributes=None, **overrides):
        hass.states.async_set("light.garden", light_state, dict(attributes or dimmable))
        entry = MockConfigEntry(
            domain=DOMAIN, title="Garden", data={**entry_data, **overrides}
        )
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        return entry

    return _setup
