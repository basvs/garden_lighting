"""Tests for the light model. Plain unittest: no Home Assistant needed."""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "garden_lighting"))

import model  # noqa: E402


class TestClearSkyTable(unittest.TestCase):
    def test_table_is_strictly_monotone(self):
        elevations = [e for e, _ in model.CLEAR_SKY_LUX]
        luxes = [lux for _, lux in model.CLEAR_SKY_LUX]
        self.assertEqual(elevations, sorted(elevations))
        self.assertEqual(luxes, sorted(luxes))
        self.assertEqual(len(set(elevations)), len(elevations))

    def test_known_anchors(self):
        # Values straight out of the table must come back unchanged.
        self.assertAlmostEqual(model.clear_sky_illuminance(-6.0), 3.4, places=6)
        self.assertAlmostEqual(model.clear_sky_illuminance(0.0), 400.0, places=6)
        self.assertAlmostEqual(model.clear_sky_illuminance(30.0), 55000.0, places=3)

    def test_clamps_outside_table(self):
        self.assertAlmostEqual(model.clear_sky_illuminance(-40.0), 0.0015, places=6)
        self.assertAlmostEqual(model.clear_sky_illuminance(120.0), 120000.0, places=3)

    def test_interpolates_geometrically(self):
        # Midway between two entries should be their geometric mean, not their
        # arithmetic one -- that is the whole point of interpolating in log-lux.
        midpoint = model.clear_sky_illuminance(-1.5)
        self.assertAlmostEqual(midpoint, math.sqrt(120.0 * 220.0), places=6)

    def test_monotone_across_a_fine_sweep(self):
        previous = -1.0
        elevation = -25.0
        while elevation <= 95.0:
            lux = model.clear_sky_illuminance(elevation)
            self.assertGreaterEqual(lux, previous)
            previous = lux
            elevation += 0.05

    def test_twilight_falls_about_a_decade_every_three_degrees(self):
        for top in (-1.0, -2.0, -3.0):
            decades = math.log10(
                model.clear_sky_illuminance(top) / model.clear_sky_illuminance(top - 3.0)
            )
            self.assertTrue(0.6 < decades < 1.6, f"{top}: {decades} decades per 3 deg")


class TestClouds(unittest.TestCase):
    def test_clear_sky_passes_everything(self):
        self.assertAlmostEqual(model.cloud_factor(0.0), 1.0)
        self.assertAlmostEqual(model.cloud_factor(None), 1.0)

    def test_overcast_leaves_a_quarter(self):
        self.assertAlmostEqual(model.cloud_factor(100.0), 0.25)

    def test_thin_cover_barely_matters(self):
        self.assertGreater(model.cloud_factor(30.0), 0.97)

    def test_impact_zero_disables_the_correction(self):
        self.assertAlmostEqual(model.cloud_factor(100.0, impact=0.0), 1.0)

    def test_out_of_range_coverage_is_clamped(self):
        self.assertAlmostEqual(model.cloud_factor(150.0), 0.25)
        self.assertAlmostEqual(model.cloud_factor(-10.0), 1.0)

    def test_night_floor_survives_clouds(self):
        self.assertGreaterEqual(model.natural_illuminance(-30.0, 100.0), model.NIGHT_FLOOR_LUX)


class TestFadeProgress(unittest.TestCase):
    def test_endpoints(self):
        self.assertAlmostEqual(model.fade_progress(300.0, 300.0, 3.0), 0.0)
        self.assertAlmostEqual(model.fade_progress(3.0, 300.0, 3.0), 1.0)

    def test_clamped_beyond_the_window(self):
        self.assertAlmostEqual(model.fade_progress(50000.0, 300.0, 3.0), 0.0)
        self.assertAlmostEqual(model.fade_progress(0.001, 300.0, 3.0), 1.0)

    def test_halfway_is_the_geometric_middle(self):
        self.assertAlmostEqual(model.fade_progress(30.0, 300.0, 3.0), 0.5)

    def test_equal_decades_give_equal_progress(self):
        # The "same pace" property: every factor-of-ten drop in daylight moves
        # the fade by the same amount.
        steps = [model.fade_progress(lux, 1000.0, 1.0) for lux in (1000.0, 100.0, 10.0, 1.0)]
        deltas = [b - a for a, b in zip(steps, steps[1:])]
        for delta in deltas:
            self.assertAlmostEqual(delta, deltas[0], places=9)

    def test_rejects_an_inverted_window(self):
        with self.assertRaises(ValueError):
            model.fade_progress(10.0, 3.0, 300.0)


class TestPerceptualRamp(unittest.TestCase):
    def test_endpoints(self):
        self.assertAlmostEqual(model.perceptual_to_linear(0.0), 0.0)
        self.assertAlmostEqual(model.perceptual_to_linear(1.0), 1.0)

    def test_halfway_up_is_about_eighteen_percent_of_the_light(self):
        self.assertAlmostEqual(model.perceptual_to_linear(0.5), 0.1842, places=3)

    def test_monotone(self):
        values = [model.perceptual_to_linear(i / 200.0) for i in range(201)]
        self.assertEqual(values, sorted(values))

    def test_continuous_at_the_piecewise_join(self):
        below = model.perceptual_to_linear(0.0799)
        above = model.perceptual_to_linear(0.0801)
        self.assertLess(abs(above - below), 1e-4)


class TestTargets(unittest.TestCase):
    def test_off_before_the_fade_starts(self):
        self.assertEqual(model.target_brightness(0.0, 1.0, 100.0), 0)

    def test_full_at_the_end(self):
        self.assertEqual(model.target_brightness(1.0, 1.0, 100.0), 255)

    def test_respects_a_capped_maximum(self):
        self.assertEqual(model.target_brightness(1.0, 1.0, 60.0), round(255 * 0.6))

    def test_monotone_in_progress(self):
        values = [model.target_brightness(i / 200.0, 1.0, 100.0) for i in range(201)]
        self.assertEqual(values, sorted(values))

    def test_linear_mode_rises_faster_early(self):
        linear = model.target_brightness(0.5, 0.0, 100.0, perceptual=False)
        perceptual = model.target_brightness(0.5, 0.0, 100.0, perceptual=True)
        self.assertGreater(linear, perceptual)

    def test_colour_temp_warms_towards_the_end(self):
        self.assertEqual(model.target_color_temp(0.0, 4000, 2200), 4000)
        self.assertEqual(model.target_color_temp(1.0, 4000, 2200), 2200)
        self.assertEqual(model.target_color_temp(0.5, 4000, 2200), 3100)


class TestDuskSweep(unittest.TestCase):
    """End to end over a real dusk, in elevation rather than in lux."""

    def _sweep(self, coverage=None):
        out = []
        elevation = 5.0
        while elevation >= -12.0:
            lux = model.natural_illuminance(elevation, coverage)
            progress = model.fade_progress(lux, 300.0, 3.0)
            out.append((elevation, lux, model.target_brightness(progress, 1.0, 100.0)))
            elevation -= 0.1
        return out

    def test_brightness_only_ever_rises(self):
        brightnesses = [b for _, _, b in self._sweep()]
        self.assertEqual(brightnesses, sorted(brightnesses))

    def test_lights_are_off_in_daylight_and_full_by_nautical_twilight(self):
        sweep = self._sweep()
        self.assertEqual(sweep[0][2], 0)
        self.assertEqual(sweep[-1][2], 255)

    def test_default_window_spans_civil_twilight(self):
        # 300 lx to 3 lx should start around sunset and finish around the end of
        # civil twilight, which is what makes the defaults sensible.
        started = [e for e, _, b in self._sweep() if b > 0][0]
        finished = [e for e, _, b in self._sweep() if b == 255][0]
        self.assertTrue(-1.5 < started < 1.0, f"fade started at {started} deg")
        self.assertTrue(-7.0 < finished < -5.0, f"fade completed at {finished} deg")

    def test_clouds_bring_the_fade_forward(self):
        clear = [e for e, _, b in self._sweep() if b > 0][0]
        overcast = [e for e, _, b in self._sweep(100.0) if b > 0][0]
        self.assertGreater(overcast, clear)

    def test_no_step_is_jarring(self):
        # Sampled every 0.1 deg -- roughly every 30 s at mid latitudes. The
        # steepest step lands near the top of the fade, where the CIE L* curve
        # is at its steepest; a transition of one update interval smooths it.
        sweep = self._sweep()
        steps = [b - a for (_, _, a), (_, _, b) in zip(sweep, sweep[1:])]
        self.assertLessEqual(max(steps), 20, "brightness jumps too hard between updates")

    def test_pace_tracks_the_daylight(self):
        # The actual design claim: the lamps come up at the same pace the
        # daylight goes down. Equal drops in log-lux must move the fade by
        # equal amounts, all the way across a real dusk.
        inside = [(lux, p) for _, lux, b in self._sweep() for p in [model.fade_progress(lux, 300.0, 3.0)] if 0.0 < p < 1.0]
        rates = [
            (p1 - p0) / (math.log10(lux0) - math.log10(lux1))
            for (lux0, p0), (lux1, p1) in zip(inside, inside[1:])
            if lux1 < lux0
        ]
        self.assertGreater(len(rates), 40)
        for rate in rates:
            self.assertAlmostEqual(rate, rates[0], places=9)


if __name__ == "__main__":
    unittest.main(verbosity=2)
