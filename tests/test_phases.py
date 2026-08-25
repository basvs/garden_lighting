"""The phase state machine, and the logbook entries it writes."""

import pytest
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.const import EVENT_LOGBOOK_ENTRY, SERVICE_TURN_OFF, SERVICE_TURN_ON
from homeassistant.core import callback
from pytest_homeassistant_custom_component.common import async_mock_service


@pytest.fixture
def logbook(hass):
    """Collect logbook entries as they are fired."""
    entries: list[dict] = []

    @callback
    def _collect(event):
        entries.append(event.data)

    hass.bus.async_listen(EVENT_LOGBOOK_ENTRY, _collect)
    return entries


@pytest.fixture(autouse=True)
def quiet_lights(hass):
    """Swallow the service calls; these tests are about the narration."""
    async_mock_service(hass, LIGHT_DOMAIN, SERVICE_TURN_ON)
    async_mock_service(hass, LIGHT_DOMAIN, SERVICE_TURN_OFF)


async def _run(hass, entry, at_elevation, *elevations):
    for degrees in elevations:
        at_elevation(degrees)
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()


def _messages(logbook):
    return [entry["message"] for entry in logbook]


async def test_a_whole_night_narrates_four_phases(hass, setup_entry, at_elevation, logbook):
    at_elevation(5.0)
    entry = await setup_entry()
    assert logbook == [], "settling into a phase at startup should be silent"

    await _run(hass, entry, at_elevation, -2.0, -6.5, -2.0, 5.0)

    assert _messages(logbook) == [
        "Fading up, daylight down to 120 lx",
        "At full brightness, daylight down to 2.4 lx",
        "Fading back down, daylight up to 120 lx",
        "Lights off, daylight up to 7000 lx",
    ]


async def test_entries_are_attributed(hass, setup_entry, at_elevation, logbook):
    at_elevation(5.0)
    entry = await setup_entry()
    await _run(hass, entry, at_elevation, -2.0)

    assert logbook[0]["name"] == "Garden"
    assert logbook[0]["domain"] == "garden_lighting"


async def test_starting_mid_fade_is_silent(hass, setup_entry, at_elevation, logbook):
    at_elevation(-4.0)
    await setup_entry()
    assert logbook == []


async def test_nothing_is_narrated_while_switched_off(
    hass, setup_entry, at_elevation, logbook
):
    at_elevation(5.0)
    entry = await setup_entry()
    await hass.services.async_call(
        "switch", SERVICE_TURN_OFF, {"entity_id": "switch.garden_fade"}, blocking=True
    )
    await hass.async_block_till_done()
    logbook.clear()

    await _run(hass, entry, at_elevation, -2.0, -6.5)
    assert logbook == []

    # The phase was still tracked while quiet, so switching back on does not
    # suddenly deliver a backlog of everything that was missed.
    await hass.services.async_call(
        "switch", SERVICE_TURN_ON, {"entity_id": "switch.garden_fade"}, blocking=True
    )
    await hass.async_block_till_done()
    assert logbook == []


async def test_a_brushed_edge_stays_quiet(hass, setup_entry, at_elevation, logbook):
    at_elevation(5.0)
    entry = await setup_entry()

    # Hovering right at the top of the window, inside the deadband. A cloud
    # drifting past should not narrate itself.
    await _run(hass, entry, at_elevation, -0.55, 0.0, -0.5, 0.2, -0.55)
    assert logbook == []

    await _run(hass, entry, at_elevation, -2.0)
    assert _messages(logbook) == ["Fading up, daylight down to 120 lx"]


async def test_a_dusk_that_never_completes_still_ends_cleanly(
    hass, setup_entry, at_elevation, logbook
):
    at_elevation(5.0)
    entry = await setup_entry()

    # Into the fade, then back out without ever reaching full brightness.
    await _run(hass, entry, at_elevation, -2.0, 5.0)

    assert _messages(logbook) == [
        "Fading up, daylight down to 120 lx",
        "Lights off, daylight up to 7000 lx",
    ]


async def test_the_phase_is_on_the_sensor(hass, setup_entry, at_elevation):
    at_elevation(-4.0)
    entry = await setup_entry()
    assert hass.states.get("sensor.garden_target_brightness").attributes["phase"] == "fading_up"

    await _run(hass, entry, at_elevation, -6.5)
    assert hass.states.get("sensor.garden_target_brightness").attributes["phase"] == "full"
