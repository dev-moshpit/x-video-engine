# Motivational Quotes pack

Pair a short quote with a stylized low-poly subject whose posture and
environment reinforce the emotional tone. The engine generates clean
visuals — you add the quote as a text overlay in your editor of choice.

## How to use

1. Copy `template.csv` to your own file (e.g. `my_quotes.csv`).
2. Fill in the rows. The only required columns are `quote`, `tone`, and
   `visual_subject`. Everything else is optional.
3. Run:
   ```bash
   python scripts/run_shorts_batch.py \
       --pack motivational_quotes \
       --csv content_packs/motivational_quotes/template.csv \
       --batch-name quotes-2026-04-21
   ```
4. Open `cache/batches/quotes-2026-04-21/index.html`.
5. Star the winners, export `selection.json`, overlay the quote in your
   editor.

## Column reference

| Column | Required | Description |
|--------|----------|-------------|
| id | yes (recommended) | Unique row key. Used for resume and filenames. |
| quote | yes | The quote you'll overlay later. Not fed to the model — kept in the CSV so the gallery shows you which clip goes with which line. |
| tone | yes | One of: `reflective`, `triumphant`, `peaceful`, `fierce`, `grateful`, `resilient`. Drives the subject's action and environment. |
| visual_subject | yes | The low-poly subject to render. Good: `a geometric lone wolf`. Bad: `a wolf that represents resilience`. Be literal. |
| preset | no | Override preset: `crystal` (default), `monument`, `papercraft`. |
| motion | no | Override motion: `calm` (default), `medium`. Tone suggests a motion automatically. |
| duration | no | Clip length in seconds (default 3.5). |
| seeds | no | Comma-separated seeds → one clip per seed. Default: `42,137,2024`. |

## Tone mapping

The pack converts `tone` into concrete action + environment phrases:

| Tone | Action | Environment | Suggested motion |
|------|--------|-------------|------------------|
| reflective | standing still, glowing softly | serene pastel mist, soft sunrise gradient | calm |
| triumphant | rising into the light, arms outstretched | dramatic sky with rays of sun, mountain peak | medium |
| peaceful | drifting gently | soft floating clouds, warm gradient horizon | calm |
| fierce | charging forward with intent | storm clouds breaking open, distant ridge | medium |
| grateful | open stance, looking upward | golden hour warm gradient, soft glow | calm |
| resilient | holding ground against wind | sparse rocky plateau, clearing sky | medium |

## Negative prompt additions

This pack automatically suppresses on-screen text, typography, letters,
captions, logos, and watermarks — you'll overlay the quote yourself,
cleanly, in post.

## Avoid

- Abstract subjects without a clear form (`a feeling of hope`). Use a concrete subject.
- Humans with detailed faces (the low-poly aesthetic fights photorealism; faceted figures work, realistic faces don't).
- On-screen text requests (they're in the negative prompt for a reason).
- More than 3 seeds per row unless you want a lot of variants to sort through.

## Good vs bad rows

```
# Good
mq_wolf_fierce,"The only way out is through",fierce,a geometric lone wolf,crystal,,,

# Bad (abstract subject)
mq_vibes,"Just vibe",peaceful,good vibes,crystal,,,

# Bad (subject fights the preset)
mq_beach,"Summer forever",peaceful,a photorealistic beach sunset,crystal,,,
```
