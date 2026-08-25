"""Setting up the entry, and actually driving the lamps."""

import pytest
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.const import SERVICE_TURN_OFF, SERVICE_TURN_ON, STATE_OFF, STATE_ON
from homeassistant.core import Context, State
from pytest_homeassistant_custom_component.common import (
    async_mock_service,
    mock_restore_cache,
)

from custom_components.garden_lighting.const import DOMAIN


async def test_daylight_leaves_the_lamps_off(hass, setup_entry, dimmable, at_elevation):
    at_elevation(20.0)
    turn_on = async_mock_service(hass, LIGHT_DOMAIN, SERVICE_TURN_ON)
    await setup_entry()
    assert turn_on == []


async def test_dusk_drives_the_lamps(hass, setup_entry, dimmable, at_elevation):
    at_elevation(-4.0)
    turn_on = async_mock_service(hass, LIGHT_DOMAIN, SERVICE_TURN_ON)
    await setup_entry()

    assert len(turn_on) == 1
    data = turn_on[0].data
    assert data["entity_id"] == "light.garden"
    # -4 degrees is a little over halfway through the default fade.
    assert 40 < data["brightness"] < 80
    # No transition: this light does not claim to support one.
    assert "transition" not in data


async def test_transition_is_sent_when_the_light_supports_it(
    hass, setup_entry, dimmable, at_elevation, entry_data
):
    at_elevation(-4.0)
    turn_on = async_mock_service(hass, LIGHT_DOMAIN, SERVICE_TURN_ON)
    await setup_entry(attributes={**dimmable, "supported_features": 32})

    assert turn_on[0].data["transition"] == entry_data["update_interval"]


async def test_colour_temp_is_clamped_to_the_lamp(hass, setup_entry, dimmable, at_elevation):
    at_elevation(-6.0)  # fade essentially complete, so it wants the warm end
    turn_on = async_mock_service(hass, LIGHT_DOMAIN, SERVICE_TURN_ON)
    await setup_entry(
        color_temp_enabled=True,
        attributes={
            "supported_color_modes": ["color_temp"],
            "supported_features": 0,
            "min_color_temp_kelvin": 2700,
            "max_color_temp_kelvin": 6500,
        },
    )
    # The model wants 2200 K but this lamp cannot go below 2700 K.
    assert turn_on[0].data["color_temp_kelvin"] == 2700


async def test_night_turns_a_lit_lamp_off_at_dawn(hass, setup_entry, dimmable, at_elevation):
    at_elevation(20.0)
    turn_off = async_mock_service(hass, LIGHT_DOMAIN, SERVICE_TURN_OFF)
    await setup_entry(light_state=STATE_ON)
    assert len(turn_off) == 1


async def test_entities_are_created(hass, setup_entry, dimmable, at_elevation):
    at_elevation(-4.0)
    async_mock_service(hass, LIGHT_DOMAIN, SERVICE_TURN_ON)
    await setup_entry()

    illuminance = hass.states.get("sensor.garden_natural_illuminance")
    target = hass.states.get("sensor.garden_target_brightness")
    switch = hass.states.get("switch.garden_fade")

    assert illuminance is not None
    assert float(illuminance.state) == pytest.approx(25.0, rel=0.01)
    assert illuminance.attributes["solar_elevation"] == -4.0
    assert target is not None
    assert 15 < float(target.state) < 32
    assert switch.state == STATE_ON


async def test_unload(hass, setup_entry, dimmable, at_elevation):
    at_elevation(-4.0)
    async_mock_service(hass, LIGHT_DOMAIN, SERVICE_TURN_ON)
    entry = await setup_entry()

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.garden_natural_illuminance").state == "unavailable"


class TestManualControl:
    """Somebody reaching for a light switch must win."""

    async def _dusk(self, hass, setup_entry, dimmable, at_elevation):
        at_elevation(-4.0)
        turn_on = async_mock_service(hass, LIGHT_DOMAIN, SERVICE_TURN_ON)
        entry = await setup_entry()
        coordinator = entry.runtime_data
        commanded = turn_on[0].data["brightness"]
        # The mocked service does not move the lamp, so land it on what we asked
        # for -- under our own context -- to get a realistic starting point.
        hass.states.async_set(
            "light.garden",
            STATE_ON,
            {**dimmable, "brightness": commanded},
            context=Context(id=coordinator._contexts[-1]),
        )
        await hass.async_block_till_done()
        # Backdate the command so the settle window has passed and later changes
        # are judged on their merits.
        coordinator._commanded["light.garden"] = (commanded, 0.0)
        return coordinator, turn_on, commanded

    async def test_a_hand_change_takes_the_light(self, hass, setup_entry, dimmable, at_elevation):
        coordinator, turn_on, commanded = await self._dusk(hass, setup_entry, dimmable, at_elevation)

        hass.states.async_set(
            "light.garden", STATE_ON, {**dimmable, "brightness": 255}, context=Context()
        )
        await hass.async_block_till_done()

        assert coordinator.manual_control == ("light.garden",)

        before = len(turn_on)
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert len(turn_on) == before, "kept driving a light somebody had taken"

    async def test_switching_it_off_by_hand_keeps_it_off(self, hass, setup_entry, dimmable, at_elevation):
        coordinator, turn_on, _ = await self._dusk(hass, setup_entry, dimmable, at_elevation)

        hass.states.async_set("light.garden", STATE_OFF, dimmable, context=Context())
        await hass.async_block_till_done()

        assert coordinator.manual_control == ("light.garden",)
        before = len(turn_on)
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert len(turn_on) == before

    async def test_our_own_changes_are_not_mistaken_for_a_person(
        self, hass, setup_entry, dimmable, at_elevation
    ):
        coordinator, _, commanded = await self._dusk(hass, setup_entry, dimmable, at_elevation)

        hass.states.async_set(
            "light.garden",
            STATE_ON,
            {**dimmable, "brightness": commanded + 60},
            context=Context(id=coordinator._contexts[-1]),
        )
        await hass.async_block_till_done()
        assert coordinator.manual_control == ()

    async def test_a_small_drift_is_not_a_person(self, hass, setup_entry, dimmable, at_elevation):
        coordinator, _, commanded = await self._dusk(hass, setup_entry, dimmable, at_elevation)

        hass.states.async_set(
            "light.garden",
            STATE_ON,
            {**dimmable, "brightness": commanded + 3},
            context=Context(),
        )
        await hass.async_block_till_done()
        assert coordinator.manual_control == ()

    async def test_the_reset_service_gives_control_back(self, hass, setup_entry, dimmable, at_elevation):
        coordinator, turn_on, _ = await self._dusk(hass, setup_entry, dimmable, at_elevation)

        hass.states.async_set(
            "light.garden", STATE_ON, {**dimmable, "brightness": 255}, context=Context()
        )
        await hass.async_block_till_done()
        assert coordinator.manual_control == ("light.garden",)

        await hass.services.async_call(
            DOMAIN, "reset_manual_control", {"entity_id": ["light.garden"]}, blocking=True
        )
        await hass.async_block_till_done()
        assert coordinator.manual_control == ()

    async def test_daylight_clears_it_for_the_next_evening(
        self, hass, setup_entry, dimmable, at_elevation
    ):
        coordinator, _, _ = await self._dusk(hass, setup_entry, dimmable, at_elevation)

        hass.states.async_set(
            "light.garden", STATE_ON, {**dimmable, "brightness": 255}, context=Context()
        )
        await hass.async_block_till_done()
        assert coordinator.manual_control == ("light.garden",)

        at_elevation(20.0)
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert coordinator.manual_control == ()


class TestFadeSwitch:
    """With the fade switched off, the light must be left entirely alone."""

    async def test_off_at_startup_touches_nothing(self, hass, setup_entry, dimmable, at_elevation):
        at_elevation(-4.0)  # mid-fade: it would very much like to drive the light
        turn_on = async_mock_service(hass, LIGHT_DOMAIN, SERVICE_TURN_ON)
        turn_off = async_mock_service(hass, LIGHT_DOMAIN, SERVICE_TURN_OFF)
        mock_restore_cache(hass, (State("switch.garden_fade", STATE_OFF),))

        await setup_entry()

        assert turn_on == []
        assert turn_off == []

    async def test_off_at_startup_does_not_switch_a_lit_light_off(
        self, hass, setup_entry, dimmable, at_elevation
    ):
        at_elevation(20.0)  # daylight: it would normally switch a lit light off
        turn_off = async_mock_service(hass, LIGHT_DOMAIN, SERVICE_TURN_OFF)
        mock_restore_cache(hass, (State("switch.garden_fade", STATE_OFF),))

        await setup_entry(light_state=STATE_ON)

        assert turn_off == []

    async def test_switching_it_off_leaves_the_light_lit(self, hass, setup_entry, dimmable, at_elevation):
        at_elevation(-4.0)
        turn_on = async_mock_service(hass, LIGHT_DOMAIN, SERVICE_TURN_ON)
        turn_off = async_mock_service(hass, LIGHT_DOMAIN, SERVICE_TURN_OFF)
        await setup_entry()
        assert len(turn_on) == 1

        await hass.services.async_call(
            "switch", SERVICE_TURN_OFF, {"entity_id": "switch.garden_fade"}, blocking=True
        )
        await hass.async_block_till_done()

        # Nothing was sent to the light: it is left exactly as it was.
        assert turn_off == []
        assert len(turn_on) == 1

    async def test_switching_it_back_on_resumes(self, hass, setup_entry, dimmable, at_elevation):
        at_elevation(-4.0)
        turn_on = async_mock_service(hass, LIGHT_DOMAIN, SERVICE_TURN_ON)
        await setup_entry()

        for service in (SERVICE_TURN_OFF, SERVICE_TURN_ON):
            await hass.services.async_call(
                "switch", service, {"entity_id": "switch.garden_fade"}, blocking=True
            )
            await hass.async_block_till_done()

        assert len(turn_on) > 1
