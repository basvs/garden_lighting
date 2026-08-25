"""Constants for the garden_lighting integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "garden_lighting"
PLATFORMS: Final = ["sensor", "switch"]

CONF_LIGHTS: Final = "lights"
CONF_WEATHER: Final = "weather_entity"
CONF_FADE_START_LUX: Final = "fade_start_lux"
CONF_FADE_END_LUX: Final = "fade_end_lux"
CONF_MIN_BRIGHTNESS: Final = "min_brightness_pct"
CONF_MAX_BRIGHTNESS: Final = "max_brightness_pct"
CONF_UPDATE_INTERVAL: Final = "update_interval"
CONF_PERCEPTUAL: Final = "perceptual_ramp"
CONF_CLOUD_IMPACT: Final = "cloud_impact"
CONF_COLOR_TEMP: Final = "color_temp_enabled"
CONF_COOL_KELVIN: Final = "cool_kelvin"
CONF_WARM_KELVIN: Final = "warm_kelvin"

# 300 lx down to 3 lx is a two-decade window that lines up almost exactly with
# civil twilight: the fade begins around sunset and completes as the last usable
# daylight goes. Roughly half an hour at mid latitudes, longer nearer the poles.
DEFAULT_FADE_START_LUX: Final = 300.0
DEFAULT_FADE_END_LUX: Final = 3.0

DEFAULT_MIN_BRIGHTNESS: Final = 1.0
DEFAULT_MAX_BRIGHTNESS: Final = 100.0
DEFAULT_UPDATE_INTERVAL: Final = 30
DEFAULT_CLOUD_IMPACT: Final = 1.0
DEFAULT_COOL_KELVIN: Final = 4000
DEFAULT_WARM_KELVIN: Final = 2200

# A light that comes back reporting more than this far from what we asked for
# was moved by somebody else.
MANUAL_TOLERANCE: Final = 25

# Lights report their new state part-way through a transition, so ignore what
# they say until the transition has had time to finish.
SETTLE_GRACE: Final = 5.0

SERVICE_RESET_MANUAL_CONTROL: Final = "reset_manual_control"

# Where the fade currently is. Announced to the logbook on each change.
PHASE_OFF: Final = "off"
PHASE_FADING_UP: Final = "fading_up"
PHASE_FULL: Final = "full"
PHASE_FADING_DOWN: Final = "fading_down"

# Cloud cover can move the daylight estimate sharply, so a phase has to be left
# properly rather than brushed against. Without this, an evening hovering around
# the top of the fade would announce itself over and over.
PHASE_DEADBAND: Final = 0.02

# The logbook reads this off the event; naming it here keeps the logbook
# integration from becoming a dependency, and the entries are simply ignored if
# it is not loaded.
ATTR_MESSAGE: Final = "message"

ATTR_ELEVATION: Final = "solar_elevation"
ATTR_CLEAR_SKY_LUX: Final = "clear_sky_lux"
ATTR_CLOUD_COVERAGE: Final = "cloud_coverage"
ATTR_FADE_PROGRESS: Final = "fade_progress"
ATTR_MANUAL_CONTROL: Final = "manually_controlled"
ATTR_PHASE: Final = "phase"
