# Abstract Loops pack

Volume-oriented aesthetic filler. Short, loopable, text-free, music-ready
low-poly visuals. Made for:

- Mood pages (aesthetic + ambient)
- Stitching as filler between longer Shorts
- Background plates behind music / TTS / lyrics
- Daily upload cadence without burning creative ideas
- Compilation reels (10 loops x 3s = 30s Reel)

## How to use

```bash
python scripts/run_shorts_batch.py \
    --pack abstract_loop \
    --csv content_packs/abstract_loop/template.csv \
    --batch-name loops-2026-04-22
```

Ten rows with 4 default seeds each = 40 variant clips in ~13 minutes on
a GTX 1650.

## Column reference

| Column | Required | Description |
|--------|----------|-------------|
| id | yes (recommended) | Unique row key |
| mood | yes | One of: `dreamy`, `sharp`, `serene`, `ethereal`, `rhythmic`, `chaotic`, `melancholic`. Drives action + environment + title word. |
| color_theme | yes | One of: `pastel`, `neon`, `mono`, `warm`, `cool`, `sunset`, `deep`. Drives preset selection. |
| visual_subject | yes | Abstract low-poly subject. Keep it abstract: `faceted shards`, `glowing particles`, `a pulsing ring`. Avoid anything figurative — these are meant to loop seamlessly without a focal character. |
| preset | no | Override preset. Default from color_theme. |
| motion | no | `calm` (default for most moods) or `medium` (for rhythmic/chaotic). |
| duration | no | Seconds. Default 2.5 (loops should feel tight). |
| seeds | no | Comma-separated. Default `1,2,3,4` — four seeds per row for variant volume. |

## Mood mapping

| Mood | Title word | Action | Environment |
|------|-----------|--------|-------------|
| dreamy | Drift | floating weightlessly | soft nebula, pastel haze |
| sharp | Pulse | pulsing rhythmically | sharp neon grid |
| serene | Stillness | barely drifting | quiet horizon, soft light |
| ethereal | Glow | glowing softly, suspended | luminous fog, pastel mist |
| rhythmic | Cycle | looping in steady pulse | beat-like rings |
| chaotic | Chaos | swirling in controlled chaos | bold color blocks colliding |
| melancholic | Weight | slowly descending | cool blue mist, rain particles |

## Color theme → preset

| color_theme | Preset hint |
|-------------|-------------|
| pastel | crystal |
| neon | neon_arcade |
| mono | monument |
| warm | crystal |
| cool | monument |
| sunset | crystal |
| deep | monument |

## Publish output

Title is deliberately a single vibe word: `Drift`, `Pulse`, `Stillness`,
`Glow`, `Cycle`, `Chaos`, `Weight`. Captions stay one line. Hashtags
stay under 10. These are filler clips — they shouldn't try to be essays
in the caption.

## Avoid

- Figurative subjects (people, animals, cars). Abstract only — these loop.
- Long durations. 2-3s is the sweet spot for loops that stitch.
- `energetic` motion — the pack rejects it. Loops should feel meditative or rhythmic, not frantic.
- Trying to communicate specific ideas. These are mood carriers. Save narrative for the other packs.
- Single-seed rows. This is the volume pack — use 3-4 seeds per row to build stock.

## Good vs bad rows

```
# Good — abstract, fits mood, right color pairing
al_drift_dream,dreamy,pastel,floating faceted crystals adrift,,,,
al_pulse_neon,sharp,neon,a pulsing neon ring,,,,

# Bad — figurative subject
al_bad_fox,dreamy,pastel,a geometric fox running,,,,

# Bad — mood + color bias fight each other
al_bad_mix,serene,neon,calm meditation,,,,
```
