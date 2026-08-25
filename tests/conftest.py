"""Fixtures for the Home Assistant level tests."""

import pytest

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
