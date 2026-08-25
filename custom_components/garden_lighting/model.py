"""Light model for the garden_lighting integration.

Deliberately free of Home Assistant imports: everything here is ordinary
arithmetic on floats, so it can be reasoned about -- and tested -- on its own.
"""

from __future__ import annotations

import math
from bisect import bisect_left

# Clear-sky horizontal illuminance in lux against solar elevation in degrees,
# ascending by elevation.
#
# Above roughly +5 degrees the entries follow a Kasten-Young air-mass model
# (extraterrestrial 133.1 klx, extinction 0.21) plus a diffuse term. Below the
# horizon that model has nothing to say -- twilight is light scattered from the
# upper atmosphere, a different regime entirely -- so those entries are the
# conventional published values instead. The -6 degree entry is 3.4 lx by
# definition: that is what "end of civil twilight" means.
#
# This is the region the whole integration exists to serve, which is why the
# table is anchored to measurements there rather than extrapolated into it.
CLEAR_SKY_LUX: tuple[tuple[float, float], ...] = (
    (-18.0, 0.0015),  # astronomical twilight ends; moonless night sky
    (-16.0, 0.0025),
    (-14.0, 0.006),
    (-12.0, 0.02),  # nautical twilight ends
    (-10.0, 0.15),
    (-8.0, 0.8),
    (-6.0, 3.4),  # civil twilight ends
    (-5.0, 9.0),
    (-4.0, 25.0),
    (-3.0, 60.0),
    (-2.0, 120.0),
    (-1.0, 220.0),
    (0.0, 400.0),  # geometric sunset
    (1.0, 1100.0),
    (2.0, 2200.0),
    (3.0, 3500.0),
    (5.0, 7000.0),
    (7.0, 11000.0),
    (10.0, 16000.0),
    (15.0, 27000.0),
    (20.0, 37000.0),
    (30.0, 55000.0),
    (45.0, 85000.0),
    (60.0, 105000.0),
    (90.0, 120000.0),
)

_ELEVATIONS: tuple[float, ...] = tuple(e for e, _ in CLEAR_SKY_LUX)
_LOG_LUX: tuple[float, ...] = tuple(math.log10(lux) for _, lux in CLEAR_SKY_LUX)

# Kasten-Czeplak: overcast leaves about a quarter of the clear-sky value, and
# thin cover barely matters, hence the steep exponent.
CLOUD_MAX_ATTENUATION = 0.75
CLOUD_EXPONENT = 3.4

# Starlight on a moonless night. Keeps the lux value away from zero so it stays
# usable as a logarithm.
NIGHT_FLOOR_LUX = 0.0015


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def clear_sky_illuminance(elevation_deg: float) -> float:
    """Horizontal illuminance under a clear sky, in lux, for a solar elevation.

    Interpolated linearly in log-lux, because that is how the quantity actually
    behaves -- during twilight it falls by roughly a factor of ten every three
    degrees, so interpolating the raw lux would badly undershoot between table
    entries.
    """
    if elevation_deg <= _ELEVATIONS[0]:
        return 10.0 ** _LOG_LUX[0]
    if elevation_deg >= _ELEVATIONS[-1]:
        return 10.0 ** _LOG_LUX[-1]

    i = bisect_left(_ELEVATIONS, elevation_deg)
    e0, e1 = _ELEVATIONS[i - 1], _ELEVATIONS[i]
    l0, l1 = _LOG_LUX[i - 1], _LOG_LUX[i]
    fraction = (elevation_deg - e0) / (e1 - e0)
    return 10.0 ** (l0 + fraction * (l1 - l0))


def cloud_factor(coverage_pct: float | None, impact: float = 1.0) -> float:
    """Fraction of clear-sky light that survives the given cloud coverage."""
    if coverage_pct is None:
        return 1.0
    coverage = clamp(coverage_pct / 100.0, 0.0, 1.0)
    return 1.0 - CLOUD_MAX_ATTENUATION * clamp(impact, 0.0, 1.0) * coverage**CLOUD_EXPONENT


def natural_illuminance(
    elevation_deg: float,
    coverage_pct: float | None = None,
    cloud_impact: float = 1.0,
) -> float:
    """Estimated outdoor illuminance in lux."""
    lux = clear_sky_illuminance(elevation_deg) * cloud_factor(coverage_pct, cloud_impact)
    return max(lux, NIGHT_FLOOR_LUX)


def fade_progress(lux: float, start_lux: float, end_lux: float) -> float:
    """How far through the fade we are: 0 at start_lux, 1 at end_lux.

    Linear in log-lux, which is what makes the lamps come up at the same pace
    the daylight goes down. Driving this off lux rather than off the clock also
    means the morning runs the curve backwards for free.
    """
    if start_lux <= end_lux:
        raise ValueError("start_lux must be greater than end_lux")

    span = math.log10(start_lux) - math.log10(end_lux)
    progress = (math.log10(start_lux) - math.log10(max(lux, 1e-9))) / span
    return clamp(progress, 0.0, 1.0)


def perceptual_to_linear(progress: float) -> float:
    """Map an evenly-perceived fraction to relative luminance, via CIE L*.

    A lamp driven linearly in luminance appears to shoot up and then crawl.
    Half-way up perceptually is only ~18% of the light output, and this is the
    curve that says so.
    """
    lstar = 100.0 * clamp(progress, 0.0, 1.0)
    if lstar > 8.0:
        return ((lstar + 16.0) / 116.0) ** 3
    return lstar / 903.3


def target_brightness(
    progress: float,
    min_pct: float,
    max_pct: float,
    perceptual: bool = True,
) -> int:
    """Lamp brightness on Home Assistant's 0-255 scale; 0 means off."""
    if progress <= 0.0:
        return 0
    fraction = perceptual_to_linear(progress) if perceptual else clamp(progress, 0.0, 1.0)
    pct = min_pct + (max_pct - min_pct) * fraction
    return round(255.0 * clamp(pct, 0.0, 100.0) / 100.0)


def target_color_temp(progress: float, cool_kelvin: int, warm_kelvin: int) -> int:
    """Colour temperature, warming towards warm_kelvin as the fade completes."""
    return round(cool_kelvin + (warm_kelvin - cool_kelvin) * clamp(progress, 0.0, 1.0))
