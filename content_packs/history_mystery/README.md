# History & Mystery pack

Hook-driven Shorts about unsolved mysteries, lost history, and eerie
events. Pairs with narrative voiceover and subtitle burn-in (added in
your editor). The engine renders symbolic low-poly stills — artifacts,
silhouettes, ruins, shadowy architecture — that work as the visual bed
beneath the voice.

## How to use

```bash
python scripts/run_shorts_batch.py \
    --pack history_mystery \
    --csv content_packs/history_mystery/template.csv \
    --batch-name mystery-2026-04-22
```

## Column reference

| Column | Required | Description |
|--------|----------|-------------|
| id | yes (recommended) | Unique row key |
| topic | yes | The story itself, stated plainly: "The Dyatlov Pass incident", "MH370's final hours", "The Voynich manuscript". Used in titles/captions. |
| mystery_angle | yes | One of: `unsolved`, `forgotten`, `conspiracy`, `lost_civilization`, `eerie`, `cover_up`, `haunted`. Drives preset, action, environment, hook. |
| visual_subject | yes | The low-poly symbolic visual: `a snowy mountain silhouette`, `an ancient open book`, `a lone plane over dark ocean`. Avoid naming real people — use silhouettes or symbolic objects. |
| preset | no | Override preset. Default from angle. |
| motion | no | `calm` (default for most angles) or `medium` (for conspiracy/cover_up). Never `energetic` — pacing must feel serious. |
| duration | no | Seconds. Default 3.5 (longer for reveal-style pacing). |
| seeds | no | Comma-separated. Default `13,77,1947`. |

## Angle mapping

| Angle | Preset | Action | Environment | Hook |
|-------|--------|--------|-------------|------|
| unsolved | monument | sitting in silent stillness | dim atmospheric fog | No one has ever explained this. |
| forgotten | papercraft | slowly weathered by time | dusty sepia backdrop | Most people never learned this existed. |
| conspiracy | monument | hidden in shadow | dark tunnel, flickering light | The official story doesn't add up. |
| lost_civilization | monument | standing timeless | ancient stone ruins | They were advanced. Then gone. |
| eerie | crystal | barely moving in dead stillness | foggy moonlight, cold blue | If this is real, it changes things. |
| cover_up | monument | emerging from deep shadow | high-contrast harsh light | The files finally opened last year. |
| haunted | monument | standing silent in empty space | abandoned architecture, faint fog | Nobody lives near here anymore. |

## Publish output

Every clip gets:
- **Title**: `{angle.title_phrase}: {topic}` → "Still unsolved: The Dyatlov Pass incident"
- **Caption**: topic + angle line + CTA (e.g. "Follow for part 2.")
- **TikTok variant**: leads with hook phrase
- **Hashtags**: `#history #mystery #unexplained #shorts` + angle tags (#unsolved, #coldcase, etc.)

## Negative prompt

Auto-suppresses: realistic human faces, identifiable people, modern
smartphones and cars (keeps the timeless/eerie aesthetic), text,
gore/blood. You're generating mood, not a newspaper photo.

## Avoid

- Naming specific living people. Use silhouettes and symbolic objects.
- Graphic content (crime scene language, violence). The pack is eerie, not gore.
- Modern anachronisms in the visual subject (don't ask for "a 2024 iPhone" on a cold-case topic).
- Overly long `topic` strings — keep them to one sentence max so the title template reads cleanly.
- `energetic` motion — mystery content lives or dies on pacing.

## Good vs bad rows

```
# Good — symbolic subject, tight topic
hm_dyatlov,The Dyatlov Pass incident,unsolved,a snowy mountain silhouette with a single tent,,,,

# Good — conspiracy angle, shadowy architecture
hm_area51,The Area 51 files,cover_up,a desert bunker emerging from harsh shadow,,,,

# Bad — names a real person
hm_bad_name,Why Elon Musk is hiding the truth,conspiracy,a realistic portrait of a billionaire,,,,

# Bad — graphic, goes past the pack's tone
hm_bad_gore,The Black Dahlia murder,unsolved,a detailed crime scene with blood,,,,
```
