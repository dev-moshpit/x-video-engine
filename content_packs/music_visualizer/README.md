# Music Visualizer pack

Abstract, loopable low-poly visuals that pair with music tracks. Track
mood drives what the subject is doing; energy drives motion intensity;
color bias hints at preset selection.

Use this pack to bulk-produce 3-5 second visual loops you can then
sequence against music in your editor.

## How to use

```bash
python scripts/run_shorts_batch.py \
    --pack music_visualizer \
    --csv content_packs/music_visualizer/template.csv \
    --batch-name musicviz-2026-04-21
```

## Column reference

| Column | Required | Description |
|--------|----------|-------------|
| id | yes (recommended) | Unique row key |
| track_mood | yes | One of: `dreamy`, `driving`, `melancholic`, `euphoric`, `ambient`, `dark`. |
| energy | yes | `low`, `medium`, `high` — maps directly to motion profile. |
| color_bias | no | `warm`, `cool`, `neon`, `monochrome`, `pastel`. Hints at preset. Default `neon`. |
| visual_subject | yes | Keep abstract: `faceted cloud forms`, `a pulsing neon tunnel`, `a single glowing ring`. Avoid figurative subjects — they look weird looping for music. |
| preset | no | Override preset. Default from color_bias. |
| motion | no | Override motion. Default from energy. |
| duration | no | Seconds. Default 3.0. Music loops usually want 2-4s. |
| seeds | no | Comma-separated. Default `11,111,1111`. |

## Mood mapping

| Mood | Action | Environment |
|------|--------|-------------|
| dreamy | floating weightlessly | soft nebula drift, pastel gradient haze |
| driving | pulsing forward with momentum | neon grid tunnel stretching to horizon |
| melancholic | slowly drifting downward | misty rain-soaked abstract cityscape, cool blue tones |
| euphoric | bursting outward in every direction | rays of light, crystal explosion, warm glow |
| ambient | suspended still, barely moving | gentle abstract mist, soft ethereal light |
| dark | slowly emerging from shadow | near-black void with deep purple accents |

## Energy → motion

| Energy | Motion profile |
|--------|----------------|
| low | calm |
| medium | medium |
| high | energetic |

## Color bias → preset hint

| Color bias | Preset hint |
|------------|-------------|
| warm / cool | crystal |
| neon | neon_arcade |
| monochrome / pastel | monument |

## Avoid

- Figurative subjects (people, animals, cars). They look off when music-looped.
- Descriptive subjects that fight the mood (a "dreamy" pulsing neon car).
- Long durations. Music loops are tight — 2.5-4s is the sweet spot.
- Multiple high-contrast focal points. Keep one thing moving clearly.

## Good vs bad rows

```
# Good
mv_drive_tunnel,driving,high,neon,a pulsing neon tunnel,,,,
mv_dream_clouds,dreamy,low,pastel,faceted cloud forms adrift,,,,

# Bad — figurative subject for music loop
mv_bad_fox,dreamy,low,pastel,a geometric fox running,,,,

# Bad — mood fights color bias
mv_bad_mood,ambient,high,neon,a pulsing chaotic grid,,,,
```
