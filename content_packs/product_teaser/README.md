# Product Teaser pack

Premium-looking abstract promo clips for any product. Built for sellable
content, not meme-bait: restrained copy, commercial CTAs, 8-10 focused
hashtags (not dumps).

**Category** drives which preset aesthetic the product lands in.
**Vibe** drives the reveal behavior and tone of the copy.

## How to use

```bash
python scripts/run_shorts_batch.py \
    --pack product_teaser \
    --csv content_packs/product_teaser/template.csv \
    --batch-name drop-2026-04-22
```

## Column reference

| Column | Required | Description |
|--------|----------|-------------|
| id | yes (recommended) | Unique row key |
| product | yes | Product name as it should appear in titles/captions (e.g. "Arc Watch", "Forge Grip"). Keep it short and brandable. |
| category | yes | One of: `tech`, `beauty`, `home`, `fashion`, `food`, `fitness`, `luxury`, `saas`, `accessory`, `gadget`. Drives preset selection + caption angle. |
| vibe | yes | One of: `elegant`, `bold`, `playful`, `premium`, `clean`, `cinematic`. Drives action, environment, title prefix, hook phrase. |
| visual_subject | yes | The low-poly visual, concretely: `a geometric watch on a pedestal`, `a low poly sneaker spinning`. Not: "something modern". |
| preset | no | Override preset. Default comes from category. |
| motion | no | `calm` or `medium`. Default from vibe. Never `energetic` — product reveals shouldn't feel frantic. |
| duration | no | Seconds. Default 3.0. |
| seeds | no | Comma-separated. Default `3,33,333`. |

## Category → Preset + caption angle

| Category | Preset | Caption angle |
|----------|--------|---------------|
| tech | neon_arcade | "Precision engineering." |
| beauty | crystal | "Designed to feel like a ritual." |
| home | papercraft | "Where warmth meets design." |
| fashion | monument | "A silhouette worth noticing." |
| food | papercraft | "Small moments, big flavor." |
| fitness | neon_arcade | "Built for the next rep." |
| luxury | monument | "For those who already know." |
| saas | neon_arcade | "Built for people who ship." |
| accessory | crystal | "The detail that makes the look." |
| gadget | neon_arcade | "Tech that actually feels new." |

## Vibe mapping

| Vibe | Action | Environment | Title prefix | Hook |
|------|--------|-------------|--------------|------|
| elegant | floating on a pedestal | soft spotlight, marble gradient | Introducing | It's not just a product. It's a feeling. |
| bold | emerging from shadow | high-contrast, hero light | Meet | Loud enough to notice. Refined enough to want. |
| playful | spinning gently | bright airy gradient | Say hello to | Fun was part of the brief. |
| premium | rotating on dark pedestal | gallery spotlight | Presenting | Designed without compromise. |
| clean | suspended still | clean cream gradient | Meet | Less, done properly. |
| cinematic | slow camera arc | dramatic backdrop, volumetric light | The new | Made to be seen. |

## Publish output

Every clip gets:
- **Title**: `{vibe.title_prefix} {product}` → "Introducing Arc Watch"
- **Caption**: product + category angle + reveal phrase + CTA
- **CTA** (seed-stable pick): "Link in bio", "Shop the drop", "Available now", "Pre-order open", "Tap to learn more"
- **Hashtags** (max 10): `#shorts #reels #newdrop #lowpoly #productdesign` + category + vibe tags
- **Platform variants**: TikTok leads with the hook phrase; Shorts/Reels stay cleaner.

## Avoid

- Long product names ("The Ultra-Premium Experience Package 2026") — use a short brandable name.
- Subjects fighting the preset: don't put `tech` + `cinematic` on a handwoven wicker chair.
- `energetic` motion — commercial reveals do not feel rushed. The pack rejects it.
- Showing humans wearing/using the product — the generator renders abstract forms, not lifestyle.
- Realistic packaging (logos, price tags). Pack's negative prompt already suppresses these.

## Good vs bad rows

```
# Good — concrete subject, category matches vibe
pt_watch_premium,The Arc Watch,luxury,premium,a geometric watch floating on a dark pedestal,,,,

# Good — playful vibe on fashion, different preset
pt_sneaker_playful,Sprint 01,fashion,playful,a faceted sneaker spinning in bright space,,,,

# Bad — subject is too abstract for a teaser
pt_bad_abstract,Product X,tech,cinematic,the feeling of innovation,,,,

# Bad — tries to render text/packaging
pt_bad_pkg,SuperBlend 3000,food,bold,a cereal box with logos and nutrition facts,,,,
```
