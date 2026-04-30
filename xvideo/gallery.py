"""Auto-generated HTML gallery for batch output.

Reads a batch folder (clips/ + manifest.csv + sidecar *.meta.json) and
writes a single self-contained index.html that:
  - shows all clips in a responsive grid (autoplay muted loop, lazy-load)
  - overlays preset / motion / seed per tile
  - opens modal on click with full video + metadata + copy-prompt
  - supports star (select) / reject on tiles, persisted in localStorage
  - keyboard nav in modal: arrows next/prev, S star, X reject, Esc close
  - filters by preset via top buttons
  - exports selection.json so operator can hand off picks

No build step, no framework, no backend. Vanilla HTML/CSS/JS.
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _load_clips(batch_dir: Path) -> list[dict]:
    """Walk batch folder and build clip descriptors from manifest + sidecars."""
    clips: list[dict] = []
    manifest = batch_dir / "manifest.csv"
    clips_dir = batch_dir / "clips"

    rows: list[dict] = []
    if manifest.exists():
        with open(manifest, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    else:
        # Fallback: discover from sidecars
        for sidecar in sorted(clips_dir.glob("*.meta.json")):
            rows.append({"job_id": sidecar.stem.replace(".meta", "")})

    for row in rows:
        job_id = row.get("job_id", "")
        if not job_id:
            continue
        video = clips_dir / f"{job_id}.mp4"
        thumb = clips_dir / f"{job_id}.png"
        sidecar_path = clips_dir / f"{job_id}.meta.json"
        if not video.exists():
            continue

        meta: dict = {}
        if sidecar_path.exists():
            try:
                meta = json.loads(sidecar_path.read_text())
            except Exception as e:
                logger.warning("Sidecar unreadable for %s: %s", job_id, e)

        fmt = row.get("format") or (meta.get("format", {}) or {}).get("name", "")
        clips.append({
            "job_id": job_id,
            "preset": row.get("preset") or meta.get("preset_name", ""),
            "motion": row.get("motion") or meta.get("motion", ""),
            "format": fmt,
            "seed": int(row.get("seed") or meta.get("seed", 0) or 0),
            "subject": row.get("subject") or "",
            "status": row.get("status", ""),
            "total_sec": float(row.get("total_sec") or 0.0),
            "image_gen_sec": float(row.get("image_gen_sec") or 0.0),
            "video": f"clips/{job_id}.mp4",
            "thumb": f"clips/{job_id}.png" if thumb.exists() else "",
            "sidecar": f"clips/{job_id}.meta.json",
            "meta": meta,
        })
    return clips


def _html_template(batch_name: str, clips: list[dict], stats: dict) -> str:
    """Build the standalone HTML string with embedded clip data."""
    clips_json = json.dumps(clips)
    stats_json = json.dumps(stats)

    # Preset accent colors
    preset_colors = {
        "crystal": "#7aaed6",
        "papercraft": "#d4a373",
        "wireframe": "#a855f7",
        "geometric_nature": "#7a9b5c",
        "neon_arcade": "#ec4899",
        "monument": "#e8a87c",
    }

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>LowPoly Shorts — {batch_name}</title>
<style>
  :root {{
    --bg: #0e0e11;
    --panel: #1a1a20;
    --panel-hi: #26262e;
    --border: #2e2e38;
    --text: #e6e6ea;
    --muted: #8a8a96;
    --accent: #7aaed6;
    --star: #fbbf24;
    --reject: #ef4444;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--bg); color: var(--text);
    font: 14px/1.4 -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  }}
  header {{
    position: sticky; top: 0; z-index: 10;
    background: rgba(14,14,17,0.95); backdrop-filter: blur(8px);
    border-bottom: 1px solid var(--border);
    padding: 12px 20px;
  }}
  .title {{ display: flex; align-items: baseline; gap: 16px; margin-bottom: 10px; }}
  .title h1 {{ margin: 0; font-size: 18px; font-weight: 600; }}
  .title .meta {{ color: var(--muted); font-size: 13px; }}
  .controls {{ display: flex; gap: 16px; align-items: center; flex-wrap: wrap; }}
  .filters {{ display: flex; gap: 6px; flex-wrap: wrap; }}
  .filter-btn, .action-btn {{
    background: var(--panel); border: 1px solid var(--border); color: var(--text);
    padding: 6px 12px; font-size: 13px; border-radius: 6px; cursor: pointer;
    transition: background 0.1s;
  }}
  .filter-btn:hover, .action-btn:hover {{ background: var(--panel-hi); }}
  .filter-btn.active {{ background: var(--accent); color: #0e0e11; border-color: var(--accent); }}
  .action-btn {{ margin-left: auto; }}
  .stats-bar {{
    display: flex; gap: 20px; font-size: 12px; color: var(--muted);
    margin-top: 8px;
  }}
  .stats-bar b {{ color: var(--text); }}

  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 12px; padding: 16px 20px;
  }}
  .tile {{
    position: relative; background: var(--panel); border: 1px solid var(--border);
    border-radius: 8px; overflow: hidden; cursor: pointer;
    transition: transform 0.15s, border-color 0.15s;
  }}
  .tile:hover {{ transform: translateY(-2px); border-color: var(--accent); }}
  .tile.starred {{ border-color: var(--star); box-shadow: 0 0 0 1px var(--star); }}
  .tile.rejected {{ opacity: 0.4; border-color: var(--reject); }}
  .tile video, .tile img {{
    display: block; width: 100%; aspect-ratio: 9/16;
    object-fit: cover; background: #000;
  }}
  .tile .badges {{
    position: absolute; top: 8px; left: 8px;
    display: flex; gap: 4px; flex-wrap: wrap;
  }}
  .badge {{
    padding: 3px 7px; font-size: 11px; font-weight: 600;
    background: rgba(0,0,0,0.65); color: #fff; border-radius: 4px;
    backdrop-filter: blur(4px);
  }}
  .badge.preset {{ color: #0e0e11; }}
  .badge.format {{ background: rgba(122, 174, 214, 0.85); color: #0e0e11; }}
  .tile .info {{
    position: absolute; bottom: 0; left: 0; right: 0;
    padding: 8px 10px; font-size: 11px;
    background: linear-gradient(transparent, rgba(0,0,0,0.8));
    color: #fff;
  }}
  .tile .info .jid {{ font-family: monospace; font-size: 10px; opacity: 0.8; }}
  .tile .actions {{
    position: absolute; top: 8px; right: 8px;
    display: flex; gap: 4px; opacity: 0; transition: opacity 0.15s;
  }}
  .tile:hover .actions, .tile.starred .actions, .tile.rejected .actions {{
    opacity: 1;
  }}
  .tile .act {{
    width: 28px; height: 28px; border: none; border-radius: 4px;
    background: rgba(0,0,0,0.7); color: #fff; font-size: 16px;
    cursor: pointer; display: flex; align-items: center; justify-content: center;
  }}
  .tile .act.star.on {{ background: var(--star); color: #000; }}
  .tile .act.reject.on {{ background: var(--reject); color: #fff; }}

  .modal {{
    display: none; position: fixed; inset: 0; z-index: 100;
    background: rgba(0,0,0,0.92); padding: 20px;
  }}
  .modal.open {{ display: flex; gap: 20px; }}
  .modal .video-col {{
    flex: 0 0 auto; display: flex; align-items: center; justify-content: center;
    max-width: 60%;
  }}
  .modal video {{ max-height: 90vh; max-width: 100%; border-radius: 8px; }}
  .modal .info-col {{
    flex: 1; overflow-y: auto; max-height: 90vh; padding-right: 8px;
  }}
  .modal h2 {{ margin: 0 0 4px; font-size: 20px; font-family: monospace; }}
  .modal .kv {{ margin: 12px 0; }}
  .modal .kv dt {{ color: var(--muted); font-size: 11px; text-transform: uppercase;
                   letter-spacing: 0.5px; margin-top: 10px; }}
  .modal .kv dd {{ margin: 2px 0 0; word-break: break-word; }}
  .modal .prompt-box {{
    background: var(--panel); border: 1px solid var(--border);
    border-radius: 6px; padding: 10px; font-family: monospace; font-size: 12px;
    margin-top: 4px; white-space: pre-wrap; max-height: 200px; overflow-y: auto;
  }}
  .modal .modal-actions {{ display: flex; gap: 8px; margin-top: 16px; flex-wrap: wrap; }}
  .modal .close {{
    position: absolute; top: 16px; right: 20px; font-size: 28px;
    background: none; border: none; color: #fff; cursor: pointer;
  }}
  .modal .nav {{ position: absolute; top: 50%; transform: translateY(-50%);
                 font-size: 36px; background: rgba(0,0,0,0.5); border: none;
                 color: #fff; cursor: pointer; padding: 12px 16px; border-radius: 6px; }}
  .modal .nav.prev {{ left: 16px; }}
  .modal .nav.next {{ right: 16px; }}

  .shortcut-hint {{
    position: fixed; bottom: 12px; right: 16px; font-size: 11px;
    color: var(--muted); background: var(--panel);
    border: 1px solid var(--border); padding: 6px 10px; border-radius: 4px;
    font-family: monospace;
  }}
  .empty {{ padding: 60px; text-align: center; color: var(--muted); }}

  .toast {{
    position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%);
    background: var(--panel-hi); color: var(--text); padding: 10px 18px;
    border-radius: 6px; border: 1px solid var(--border);
    opacity: 0; transition: opacity 0.2s; pointer-events: none; z-index: 200;
  }}
  .toast.show {{ opacity: 1; }}
</style>
</head>
<body>

<header>
  <div class="title">
    <h1>🎬 {batch_name}</h1>
    <span class="meta" id="summary"></span>
  </div>
  <div class="controls">
    <div class="filters" id="filters"></div>
    <button class="action-btn" id="export-btn">📥 Export selection.json</button>
    <button class="action-btn" id="clear-btn">↺ Clear selections</button>
  </div>
  <div class="stats-bar" id="stats"></div>
</header>

<div class="grid" id="grid"></div>

<div class="modal" id="modal">
  <button class="close" id="modal-close">✕</button>
  <button class="nav prev" id="modal-prev">‹</button>
  <button class="nav next" id="modal-next">›</button>
  <div class="video-col">
    <video id="modal-video" controls autoplay loop></video>
  </div>
  <div class="info-col" id="modal-info"></div>
</div>

<div class="shortcut-hint">← → prev/next · S star · X reject · Esc close</div>
<div class="toast" id="toast"></div>

<script>
const CLIPS = {clips_json};
const STATS = {stats_json};
const BATCH_NAME = {json.dumps(batch_name)};
const PRESET_COLORS = {json.dumps(preset_colors)};

const LS_KEY = `lowpoly-selections-${{BATCH_NAME}}`;

// ── State ─────────────────────────────────────────────────────────────
const state = {{
  filter: "all",
  selections: JSON.parse(localStorage.getItem(LS_KEY) || "{{}}"),
  modalIndex: -1,
  visible: [...CLIPS],
}};

function save() {{
  localStorage.setItem(LS_KEY, JSON.stringify(state.selections));
}}

function setSel(jobId, kind) {{
  if (state.selections[jobId] === kind) delete state.selections[jobId];
  else state.selections[jobId] = kind;
  save();
  render();
  updateSummary();
}}

// ── Rendering ─────────────────────────────────────────────────────────
function render() {{
  const grid = document.getElementById("grid");
  state.visible = state.filter === "all"
    ? [...CLIPS]
    : CLIPS.filter(c => c.preset === state.filter);

  if (state.visible.length === 0) {{
    grid.innerHTML = `<div class="empty">No clips match filter "${{state.filter}}"</div>`;
    return;
  }}

  grid.innerHTML = state.visible.map((c, i) => {{
    const sel = state.selections[c.job_id];
    const color = PRESET_COLORS[c.preset] || "#888";
    return `
      <div class="tile ${{sel === 'star' ? 'starred' : sel === 'reject' ? 'rejected' : ''}}"
           data-i="${{i}}">
        <video preload="none" muted loop playsinline
               poster="${{c.thumb}}"
               data-src="${{c.video}}"></video>
        <div class="badges">
          <span class="badge preset" style="background:${{color}}">${{c.preset || '?'}}</span>
          ${{c.motion ? `<span class="badge">${{c.motion}}</span>` : ''}}
          ${{c.format ? `<span class="badge format">${{c.format}}</span>` : ''}}
          <span class="badge">s${{c.seed}}</span>
        </div>
        <div class="actions">
          <button class="act star ${{sel === 'star' ? 'on' : ''}}" data-act="star" title="Star (S)">★</button>
          <button class="act reject ${{sel === 'reject' ? 'on' : ''}}" data-act="reject" title="Reject (X)">✕</button>
        </div>
        <div class="info">
          <div class="jid">${{c.job_id}}</div>
          ${{c.subject ? `<div>${{c.subject}}</div>` : ''}}
        </div>
      </div>
    `;
  }}).join("");

  // Wire tile events + lazy-load videos as they enter viewport
  const io = new IntersectionObserver((entries) => {{
    entries.forEach(e => {{
      if (e.isIntersecting) {{
        const v = e.target.querySelector("video");
        if (v && !v.src && v.dataset.src) {{
          v.src = v.dataset.src;
          v.load();
          v.play().catch(() => {{}});
        }}
      }}
    }});
  }}, {{ rootMargin: "200px" }});

  grid.querySelectorAll(".tile").forEach(tile => {{
    io.observe(tile);
    const idx = +tile.dataset.i;
    const clip = state.visible[idx];
    tile.addEventListener("click", (ev) => {{
      if (ev.target.closest(".act")) return;
      openModal(idx);
    }});
    tile.querySelectorAll(".act").forEach(btn => {{
      btn.addEventListener("click", (ev) => {{
        ev.stopPropagation();
        setSel(clip.job_id, btn.dataset.act);
      }});
    }});
  }});
}}

// ── Filters ───────────────────────────────────────────────────────────
function renderFilters() {{
  const counts = {{ all: CLIPS.length }};
  CLIPS.forEach(c => {{ counts[c.preset] = (counts[c.preset] || 0) + 1; }});
  const order = ["all", "crystal", "papercraft", "neon_arcade", "monument",
                  "wireframe", "geometric_nature"];
  const present = order.filter(k => counts[k]);

  document.getElementById("filters").innerHTML = present.map(k => `
    <button class="filter-btn ${{state.filter === k ? 'active' : ''}}" data-f="${{k}}">
      ${{k === 'all' ? 'All' : k}} <span style="opacity:0.6">${{counts[k]}}</span>
    </button>
  `).join("");

  document.querySelectorAll(".filter-btn").forEach(b => {{
    b.addEventListener("click", () => {{
      state.filter = b.dataset.f;
      render();
      renderFilters();
    }});
  }});
}}

// ── Modal ─────────────────────────────────────────────────────────────
function openModal(i) {{
  state.modalIndex = i;
  const c = state.visible[i];
  if (!c) return;

  const modal = document.getElementById("modal");
  const video = document.getElementById("modal-video");
  video.src = c.video;
  video.load();
  video.play().catch(() => {{}});

  const m = c.meta || {{}};
  const guards = (m.guard_mutations || []).map(g =>
    `${{g.rule}}: ${{g.field}} ${{g.from_value}} → ${{g.to_value}}`
  ).join("\\n") || "(none)";
  const timing = m.timing || {{}};

  const pub = m.publish || null;
  const hashtags = pub ? (pub.hashtags || []).join(" ") : "";
  const platforms = pub ? (pub.platforms || {{}}) : {{}};
  const platformRow = (name) => {{
    const p = platforms[name];
    if (!p) return "";
    return `
      <dt>${{name.toUpperCase()}}</dt>
      <dd>
        <div style="display:flex; gap:6px; align-items:flex-start; margin-bottom:4px">
          <button class="action-btn" data-copy-text="${{escapeAttr(p.title || '')}}" title="Copy title">📋 Title</button>
          <button class="action-btn" data-copy-text="${{escapeAttr(p.caption || '')}}" title="Copy caption">📋 Caption</button>
        </div>
        <div class="prompt-box"><b>${{escapeHtml(p.title || '')}}</b>\\n\\n${{escapeHtml(p.caption || '')}}</div>
      </dd>
    `;
  }};

  const publishBlock = pub ? `
    <div style="border-top:1px solid var(--border); margin-top:16px; padding-top:12px">
      <h3 style="margin:0 0 8px; font-size:14px; color:var(--accent)">📢 PUBLISH</h3>
      <dl class="kv">
        <dt>Title (default)</dt>
        <dd>
          <div class="prompt-box">${{escapeHtml(pub.title || '')}}</div>
          <button class="action-btn" data-copy-text="${{escapeAttr(pub.title || '')}}" style="margin-top:4px">📋 Copy title</button>
        </dd>
        <dt>Caption (default)</dt>
        <dd>
          <div class="prompt-box">${{escapeHtml(pub.caption || '')}}</div>
          <button class="action-btn" data-copy-text="${{escapeAttr(pub.caption || '')}}" style="margin-top:4px">📋 Copy caption</button>
        </dd>
        <dt>CTA</dt>
        <dd><div class="prompt-box">${{escapeHtml(pub.cta || '')}}</div></dd>
        <dt>Hashtags (${{(pub.hashtags || []).length}})</dt>
        <dd>
          <div class="prompt-box">${{escapeHtml(hashtags)}}</div>
          <button class="action-btn" data-copy-text="${{escapeAttr(hashtags)}}" style="margin-top:4px">📋 Copy hashtags</button>
        </dd>
        ${{platformRow("shorts")}}
        ${{platformRow("tiktok")}}
        ${{platformRow("reels")}}
      </dl>
    </div>
  ` : "";

  document.getElementById("modal-info").innerHTML = `
    <h2>${{c.job_id}}</h2>
    <div>${{c.subject || ''}}</div>

    <dl class="kv">
      <dt>Preset / Motion / Seed</dt>
      <dd><b>${{c.preset}}</b> · ${{c.motion || '—'}} · seed ${{c.seed}}${{c.format ? ` · <span class="badge format">${{c.format}}</span>` : ''}}</dd>

      <dt>Prompt</dt>
      <dd><div class="prompt-box">${{escapeHtml(m.compiled_prompt || '(unavailable)')}}</div></dd>

      <dt>Guard mutations</dt>
      <dd><div class="prompt-box">${{escapeHtml(guards)}}</div></dd>

      <dt>Timing</dt>
      <dd>gen ${{timing.generation_sec ?? '?'}}s · total ${{timing.total_sec ?? '?'}}s · steps ${{m.num_inference_steps ?? '?'}}</dd>

      <dt>Output</dt>
      <dd><code>${{c.video}}</code></dd>

      <dt>Prompt hash</dt>
      <dd><code>${{m.prompt_hash || '—'}}</code></dd>
    </dl>

    ${{publishBlock}}

    <div class="modal-actions">
      <button class="action-btn" id="m-star">★ Star</button>
      <button class="action-btn" id="m-reject">✕ Reject</button>
      <button class="action-btn" id="m-copy-prompt">📋 Copy prompt</button>
      <button class="action-btn" id="m-copy-file">📋 Copy filename</button>
      <button class="action-btn" id="m-open-sidecar">📄 Open sidecar</button>
    </div>
  `;

  // Wire all data-copy-text buttons (publish section dynamic buttons)
  document.getElementById("modal-info").querySelectorAll("[data-copy-text]").forEach(btn => {{
    btn.addEventListener("click", (ev) => {{
      ev.stopPropagation();
      navigator.clipboard.writeText(btn.getAttribute("data-copy-text") || "");
      toast("Copied");
    }});
  }});

  document.getElementById("m-star").onclick = () => {{
    setSel(c.job_id, "star");
    updateModalState();
  }};
  document.getElementById("m-reject").onclick = () => {{
    setSel(c.job_id, "reject");
    updateModalState();
  }};
  document.getElementById("m-copy-prompt").onclick = () => {{
    navigator.clipboard.writeText(m.compiled_prompt || "");
    toast("Prompt copied");
  }};
  document.getElementById("m-copy-file").onclick = () => {{
    navigator.clipboard.writeText(c.job_id + ".mp4");
    toast("Filename copied");
  }};
  document.getElementById("m-open-sidecar").onclick = () => {{
    window.open(c.sidecar, "_blank");
  }};

  updateModalState();
  modal.classList.add("open");
}}

function updateModalState() {{
  const c = state.visible[state.modalIndex];
  if (!c) return;
  const sel = state.selections[c.job_id];
  document.getElementById("m-star").style.background =
    sel === "star" ? "var(--star)" : "";
  document.getElementById("m-reject").style.background =
    sel === "reject" ? "var(--reject)" : "";
}}

function closeModal() {{
  document.getElementById("modal").classList.remove("open");
  document.getElementById("modal-video").pause();
  state.modalIndex = -1;
}}

function navModal(dir) {{
  const next = state.modalIndex + dir;
  if (next < 0 || next >= state.visible.length) return;
  openModal(next);
}}

// ── Summary bar ───────────────────────────────────────────────────────
function updateSummary() {{
  const stars = Object.values(state.selections).filter(v => v === "star").length;
  const rejects = Object.values(state.selections).filter(v => v === "reject").length;
  document.getElementById("summary").textContent =
    `${{CLIPS.length}} clips · ★ ${{stars}} starred · ✕ ${{rejects}} rejected`;

  const sb = document.getElementById("stats");
  const presets = Object.entries(STATS.per_preset || {{}})
    .map(([k, v]) => `<b>${{k}}</b> ${{v.completed}}/${{v.count}}`).join(" · ");
  const throughput = STATS.clips_per_minute || 0;
  sb.innerHTML = `
    <span>Total: <b>${{STATS.completed ?? CLIPS.length}}</b></span>
    <span>Avg clip: <b>${{STATS.avg_total_sec ?? '?'}}s</b></span>
    <span>${{throughput}} clips/min</span>
    ${{presets ? `<span>${{presets}}</span>` : ''}}
  `;
}}

// ── Export ────────────────────────────────────────────────────────────
function exportSelections() {{
  const out = {{
    batch_name: BATCH_NAME,
    exported_at: new Date().toISOString(),
    starred: Object.entries(state.selections)
      .filter(([_, v]) => v === "star").map(([k]) => k),
    rejected: Object.entries(state.selections)
      .filter(([_, v]) => v === "reject").map(([k]) => k),
  }};
  const blob = new Blob([JSON.stringify(out, null, 2)], {{ type: "application/json" }});
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `selection.json`;
  a.click();
  URL.revokeObjectURL(url);
  toast(`Exported ${{out.starred.length}} starred, ${{out.rejected.length}} rejected`);
}}

// ── Utilities ─────────────────────────────────────────────────────────
function escapeHtml(s) {{
  return String(s || "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}}
function escapeAttr(s) {{
  return String(s || "")
    .replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/'/g, "&#39;")
    .replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/\\n/g, "&#10;");
}}

let toastTimer;
function toast(msg) {{
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 1800);
}}

// ── Keyboard ──────────────────────────────────────────────────────────
document.addEventListener("keydown", (e) => {{
  const open = document.getElementById("modal").classList.contains("open");
  if (e.key === "Escape" && open) {{ closeModal(); return; }}
  if (!open) return;
  if (e.key === "ArrowRight") {{ e.preventDefault(); navModal(1); }}
  if (e.key === "ArrowLeft")  {{ e.preventDefault(); navModal(-1); }}
  if (e.key.toLowerCase() === "s") {{
    const c = state.visible[state.modalIndex];
    if (c) {{ setSel(c.job_id, "star"); updateModalState(); }}
  }}
  if (e.key.toLowerCase() === "x") {{
    const c = state.visible[state.modalIndex];
    if (c) {{ setSel(c.job_id, "reject"); updateModalState(); }}
  }}
}});

// ── Init ──────────────────────────────────────────────────────────────
document.getElementById("modal-close").onclick = closeModal;
document.getElementById("modal-prev").onclick = () => navModal(-1);
document.getElementById("modal-next").onclick = () => navModal(1);
document.getElementById("modal").addEventListener("click", (e) => {{
  if (e.target.id === "modal") closeModal();
}});
document.getElementById("export-btn").onclick = exportSelections;
document.getElementById("clear-btn").onclick = () => {{
  if (confirm("Clear all selections for this batch?")) {{
    state.selections = {{}};
    save();
    render();
    updateSummary();
  }}
}};

renderFilters();
render();
updateSummary();
</script>
</body>
</html>
"""


def build_gallery(batch_dir: str | Path) -> Path:
    """Generate index.html inside the batch folder. Returns the path."""
    batch_dir = Path(batch_dir)
    if not batch_dir.is_dir():
        raise FileNotFoundError(f"Batch folder not found: {batch_dir}")

    clips = _load_clips(batch_dir)
    if not clips:
        logger.warning("No clips found in %s", batch_dir)

    # Load stats if present
    stats: dict = {}
    stats_file = batch_dir / "stats.json"
    if stats_file.exists():
        try:
            stats = json.loads(stats_file.read_text())
        except Exception:
            stats = {}

    html = _html_template(batch_dir.name, clips, stats)
    out = batch_dir / "index.html"
    out.write_text(html, encoding="utf-8")
    logger.info("Gallery written: %s (%d clips)", out, len(clips))
    return out
