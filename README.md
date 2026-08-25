# Garden Lighting

A Home Assistant custom integration that fades your garden lights **up** at the
same pace the daylight fades **down**, so the two cross over without anybody
noticing a light switch on.

No lux sensor needed: the daylight is worked out from the sun's position, and
optionally dimmed by the cloud cover your weather entity reports.

## The idea

Outdoor light does not fall linearly at dusk. It falls roughly **a factor of ten
every three degrees** of solar elevation — from ~400 lx at sunset to ~3 lx at the
end of civil twilight, half an hour later.

Two consequences drive the whole design:

1. **Match the fade in log-lux, not in lux.** Compensating linearly means the
   lamps do almost nothing for most of dusk and then lurch. Every halving of the
   daylight should move the fade by the same amount, so the crossover feels like
   one continuous change rather than a lamp catching up.
2. **Ramp the lamps perceptually, not linearly.** Half-way up to the eye is only
   about 18% of the actual light output (CIE L\*). A lamp ramped linearly in
   brightness appears to shoot up and then crawl. The `perceptual_ramp` option
   corrects for this and is on by default.

Together those are what "the same pace" actually means.

## What it does over a dusk

With the defaults (fade from 300 lx down to 3 lx), at mid latitudes:

| Sun elevation | Daylight | Lamps |
|--------------:|---------:|------:|
| `+0.5°` | 663 lx | off |
| `-0.5°` | 297 lx | just on |
| `-2.0°` | 120 lx | 4% |
| `-3.0°` | 60 lx | 9% |
| `-4.0°` | 25 lx | 23% |
| `-5.0°` | 9 lx | 51% |
| `-6.0°` | 3.4 lx | 93% |
| `-6.5°` | 2.4 lx | 100% |

Because it is driven off the light level and not off the clock, dawn simply runs
the same curve backwards, and an overcast evening starts the fade earlier — both
for free.

## Installation

Copy `custom_components/garden_lighting` into your Home Assistant `config`
directory, restart, then **Settings → Devices & Services → Add Integration →
Garden Lighting**. (Or add `basvs/garden_lighting` to HACS as a custom
repository.)

## Configuration

Everything is set in the config flow and changeable afterwards under
**Configure**.

| Option | Default | What it does |
|---|---|---|
| Garden lights | — | The lights to drive. |
| Weather entity | none | Read for `cloud_coverage`. Without one you get clear-sky values. |
| Start fading at | 300 lx | Outdoor level where the lamps first come on — about sunset. |
| Fully lit at | 3 lx | Outdoor level where they reach full — end of civil twilight. |
| Minimum / maximum brightness | 1% / 100% | Clamps the lamp end of the fade. |
| Even to the eye | on | The CIE L\* ramp described above. |
| How much cloud matters | 1.0 | 0 ignores weather; 1 lets full overcast cut the estimate to a quarter. |
| Update every | 30 s | Also used as the transition time, so the lamps glide between steps. |
| Warm the colour as it darkens | off | Fades colour temperature alongside brightness. |
| Colour at start / end of fade | 4000 K / 2200 K | Only for lights that support colour temperature. |

Widen the window (say 1000 lx → 1 lx) for a longer, gentler fade; narrow it for a
snappier one.

## Entities

Each config entry gives you a device with:

- **`sensor.*_natural_illuminance`** — the estimated daylight in lux, with
  `solar_elevation`, `cloud_coverage` and `clear_sky_lux` as attributes.
- **`sensor.*_target_brightness`** — where the fade currently wants the lamps, as
  a percentage, with `fade_progress` and `manually_controlled`.
- **`switch.*_fade`** — the master switch. It survives restarts.

Switched off, the garden lights are left **entirely** alone: not switched on, not
switched off, not held anywhere. Nothing is sent to them at all, and that holds
across a restart too — the integration drives nothing until the switch has
restored, so it can never act on a default it is about to overwrite. Switching it
back on takes control again from scratch.

The sensors exist so the lamps are never a mystery: if something looks wrong,
graph the illuminance sensor against the target brightness and the reason is
usually obvious.

## Not fighting you

If you change a garden light by hand, the integration notices and backs off that
light for the rest of the night.

It tells your changes from its own by the Home Assistant **context** attached to
each service call, and it ignores what a light reports while it is still gliding
through a transition, so a slow Zigbee bulb reporting an in-between brightness is
not mistaken for a person.

A light is left alone once it is switched off, switched on, or moved more than
~10% away from what was asked of it. Control resumes when:

- daylight returns the next morning (the fade resets every day),
- you turn the master switch off and on again, or
- you call `garden_lighting.reset_manual_control`, optionally with an `entity_id`.

## Notes

- The lamps stay at full all night. If you want them off after a certain hour,
  put a schedule helper in front of the master switch rather than changing the
  fade — that keeps the two concerns separate.
- `cloud_coverage` is not published by every weather integration. If yours does
  not have it, the estimate falls back to clear-sky values, which simply means
  the fade runs a little late on grey evenings.
- Accuracy of the absolute lux figure is not really the point. What matters is
  that the curve has the right *shape*, since that is what the fade follows.

## Development

The light model in `custom_components/garden_lighting/model.py` deliberately
imports nothing from Home Assistant, so it can be tested on its own:

```sh
python3 -m unittest discover -s tests -v
```
