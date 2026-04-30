# Music beds

Drop royalty-free instrumental loops here — `.mp3`, `.m4a`, `.wav`, or `.ogg`.

The prompt-native finalizer with `--music-bed auto` will pick the first
file whose name matches the plan's pacing (e.g. `calm_*.mp3`,
`energetic_*.mp3`) or theme (e.g. `motivation_*.mp3`,
`mystery_*.mp3`). If no match, the alphabetically-first file is used.

Beds are mixed under voice at `-18 dB` (configurable via
`--music-bed-db`), faded in/out at edges, and looped to fit the final
duration.

Captions and voice are unaffected — bed is purely background.
