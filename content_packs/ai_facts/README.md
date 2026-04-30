# AI Facts pack

Bite-sized AI/tech facts with stylized visuals. The engine renders a
clean visual loop; you overlay the fact + narration in your editor.

## How to use

```bash
python scripts/run_shorts_batch.py \
    --pack ai_facts \
    --csv content_packs/ai_facts/template.csv \
    --batch-name aifacts-2026-04-21
```

Then open the batch `index.html` and star the winners.

## Column reference

| Column | Required | Description |
|--------|----------|-------------|
| id | yes (recommended) | Unique row key |
| topic | yes | The fact / talking point. Not fed to the model — kept for your reference so you match clip ↔ voiceover later. |
| angle | yes | One of: `mind-blowing`, `wholesome`, `cautionary`, `curious`, `future`, `historical`. Drives tone + preset hint + motion. |
| visual_subject | yes | Concrete low-poly subject. Keep literal: `a geometric microchip`, not `the concept of AI`. |
| preset | no | Override preset. Default comes from the angle's `preset_hint`. |
| motion | no | Override motion. Angle suggests one automatically. |
| duration | no | Seconds. Default 3.0. |
| seeds | no | Comma-separated. Default `7,77,808`. |

## Angle mapping

| Angle | Action | Environment | Preset hint | Motion |
|-------|--------|-------------|-------------|--------|
| mind-blowing | pulsing with energy | complex glowing network of interconnected nodes | neon_arcade | energetic |
| wholesome | softly floating | friendly abstract space with warm pastel clouds | crystal | calm |
| cautionary | slowly looming | deep dark space with red accent glow, sharp shadows | neon_arcade | medium |
| curious | suspended, contemplating | abstract void with drifting particles, soft light | monument | calm |
| future | gliding forward on a grid | sleek neon cyber grid, glowing horizon | neon_arcade | energetic |
| historical | standing timeless | vintage sepia-tinted abstract space | papercraft | calm |

## Negative prompt additions

Suppresses: humans with realistic faces, on-screen text, UI elements,
code on screen, typography, logos. Clean plates for your overlay.

## Good vs bad rows

```
# Good — concrete subject, clear angle
af_gpu,"Why GPUs changed AI forever",future,a geometric microchip with glowing circuits,,,,

# Bad — abstract concept as subject
af_bad,"What is intelligence",curious,the concept of thinking,,,,

# Bad — subject undermines the aesthetic
af_uh,"AI facts",mind-blowing,a photorealistic human coder at a keyboard,,,,
```

## Avoid

- Subjects that demand realistic humans. Use figures, silhouettes, robots.
- Cluttered scenes. One strong focal subject reads well on a 9:16 phone screen.
- Angles that don't match the subject. A "wholesome" angle on a microchip won't land.
