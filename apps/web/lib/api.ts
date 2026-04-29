// Typed API client for the SaaS API.
// Caller passes the Clerk token (server: `auth().getToken()`,
// client: `useAuth().getToken()`). The fetch never reads from
// process.env on the client beyond the public base URL.

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// ─── Types (mirror apps/api/app/schemas/*) ──────────────────────────────

export interface TemplateMeta {
  template_id: string;
  name: string;
  description: string;
  category: string;
  tags: string[];
  has_plan_preview: boolean;
  input_schema: Record<string, unknown>;
}

export interface VoiceInfo {
  id: string;
  name: string;
  gender: "female" | "male" | "neutral";
  language: string;
  category?: string;
  tone?: string[];
  provider?: string;
  is_default?: boolean;
  preview_url?: string | null;
}

export interface VoiceCategory {
  id: string;
  label: string;
  voice_ids: string[];
}

export interface CaptionLanguage {
  code: string;
  name: string;
  native: string;
  rtl?: boolean;
}

export interface StylePresetMeta {
  id: string;
  name: string;
  description: string;
  palette: {
    background: string;
    surface: string;
    primary: string;
    text_strong: string;
    text_muted: string;
  };
  camera_motion: string;
  default_caption_style: string;
  music_mood: string;
  render_notes: string;
  tags: string[];
}

export interface PacingMeta {
  id: string;
  label: string;
  zoom_start: number;
  zoom_end: number;
  pan_amount: number;
  hold_seconds: number;
  transition_seconds: number;
}

export interface CaptionStyleInfo {
  id: string;
  default_for_format: Record<string, boolean>;
}

export interface Project {
  id: string;
  user_id: string;
  template: string;
  name: string;
  template_input: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface RenderSummary {
  id: string;
  job_id: string;
  stage:
    | "pending"
    | "scripting"
    | "rendering"
    | "postprocess"
    | "uploading"
    | "complete"
    | "failed";
  progress: number;
  final_mp4_url: string | null;
  error: string | null;
  started_at: string;
  completed_at: string | null;
  starred: boolean | null;
}

export interface ProjectDetail extends Project {
  renders: RenderSummary[];
}

export interface VideoPlan {
  title: string;
  hook: string;
  concept: string;
  emotional_angle: string;
  audience: string;
  visual_style: string;
  color_palette: string;
  pacing: string;
  voice_tone: string;
  caption_style: string;
  scenes: Array<{
    scene_id: string;
    duration: number;
    subject: string;
    environment: string;
    mood: string;
    camera_motion: string;
    transition: string;
    visual_prompt: string;
    on_screen_caption: string;
    narration_line: string;
  }>;
  voiceover_lines: string[];
  cta: string;
  seed: number;
  variation_id: number;
}

export interface PlanScore {
  total: number;
  hook_strength: number;
  scene_variety: number;
  visual_uniqueness: number;
  caption_punch: number;
  prompt_relevance: number;
  notes: string[];
}

export interface GeneratedPlan {
  video_plan: VideoPlan;
  score: PlanScore;
  warnings: string[];
}

export interface PlanResponse {
  plans: GeneratedPlan[];
  recommended_index?: number | null;
}

// ─── Phase 4: preferences + recommendations ──────────────────────────────

export interface TemplateMetrics {
  renders: number;
  completed: number;
  failed: number;
  starred: number;
  rejected: number;
  success_rate: number;
  star_rate: number;
}

export interface PreferenceProfile {
  starred_count: number;
  rejected_count: number;
  templates: Record<string, number>;
  caption_styles: Record<string, number>;
  voices: Record<string, number>;
  top_template: string | null;
  top_caption_style: string | null;
  top_voice: string | null;
  per_template: Record<string, TemplateMetrics>;
}

export interface Recommendations {
  template: string;
  caption_style: string | null;
  voice_name: string | null;
  style: string | null;
  reasons: Record<string, string>;
}

export const getPreferences = (token: string) =>
  apiFetch<PreferenceProfile>("/api/me/preferences", { token });

export const getRecommendations = (template: string, token: string) =>
  apiFetch<Recommendations>(
    `/api/me/recommendations/${encodeURIComponent(template)}`,
    { token },
  );

// ─── Phase 7: publishing metadata ───────────────────────────────────────

export interface PublishMetadata {
  title: string;
  description: string;
  hashtags: string[];
  alternates: string[];
}

export const getPublishMetadata = (projectId: string, token: string) =>
  apiFetch<PublishMetadata>(`/api/projects/${projectId}/publish-metadata`, {
    token,
  });

// ─── Phase 6: brand kit ─────────────────────────────────────────────────

export interface BrandKit {
  brand_color: string | null;
  accent_color: string | null;
  text_color: string | null;
  logo_url: string | null;
  brand_name: string | null;
}

export const getBrandKit = (token: string) =>
  apiFetch<BrandKit>("/api/me/brand-kit", { token });

export const upsertBrandKit = (body: BrandKit, token: string) =>
  apiFetch<BrandKit>("/api/me/brand-kit", {
    method: "PUT",
    body: JSON.stringify(body),
    token,
  });

export const deleteBrandKit = (token: string) =>
  apiFetch<void>("/api/me/brand-kit", { method: "DELETE", token });

export interface MeResponse {
  user_id: string;
  db_user_id: string;
  email: string | null;
  tier: string;
  created_at: string;
}

// ─── Fetch wrapper ──────────────────────────────────────────────────────

async function apiFetch<T>(
  path: string,
  opts: RequestInit & { token?: string | null } = {},
): Promise<T> {
  const { token, ...init } = opts;
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }
  if (token) headers.set("authorization", `Bearer ${token}`);

  const res = await fetch(`${API_BASE_URL}${path}`, { ...init, headers, cache: "no-store" });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status} ${res.statusText}: ${text || path}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// ─── Catalog (public) ───────────────────────────────────────────────────

export const listTemplates = () => apiFetch<TemplateMeta[]>("/api/templates");
export const listVoices = () => apiFetch<VoiceInfo[]>("/api/voices");
export const listVoiceCategories = () =>
  apiFetch<VoiceCategory[]>("/api/voices/categories");
export const listCaptionStyles = () =>
  apiFetch<CaptionStyleInfo[]>("/api/caption-styles");
export const listCaptionLanguages = () =>
  apiFetch<CaptionLanguage[]>("/api/caption-languages");
export const listStylePresets = () =>
  apiFetch<StylePresetMeta[]>("/api/styles");
export const listPacingPresets = () =>
  apiFetch<PacingMeta[]>("/api/pacing");

// ─── Authed ─────────────────────────────────────────────────────────────

export const getMe = (token: string) =>
  apiFetch<MeResponse>("/api/me", { token });

export const listProjects = (token: string) =>
  apiFetch<Project[]>("/api/projects", { token });

export const getProject = (id: string, token: string) =>
  apiFetch<ProjectDetail>(`/api/projects/${id}`, { token });

export const createProject = (
  body: { template: string; name: string; template_input: Record<string, unknown> },
  token: string,
) =>
  apiFetch<Project>("/api/projects", {
    method: "POST",
    body: JSON.stringify(body),
    token,
  });

export const updateProject = (
  projectId: string,
  body: { name?: string; template_input?: Record<string, unknown> },
  token: string,
) =>
  apiFetch<Project>(`/api/projects/${projectId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
    token,
  });

export const previewPlan = (
  projectId: string,
  body: { variations?: number; seed?: number | null; score_and_filter?: boolean },
  token: string,
) =>
  apiFetch<PlanResponse>(`/api/projects/${projectId}/plan`, {
    method: "POST",
    body: JSON.stringify(body),
    token,
  });

export const createRender = (projectId: string, token: string) =>
  apiFetch<RenderSummary>(`/api/projects/${projectId}/render`, {
    method: "POST",
    token,
  });

export const createRenderBatch = (
  projectId: string, count: number, token: string,
) =>
  apiFetch<RenderSummary[]>(`/api/projects/${projectId}/render-batch`, {
    method: "POST",
    body: JSON.stringify({ count }),
    token,
  });

export const getRender = (renderId: string, token: string) =>
  apiFetch<RenderSummary>(`/api/renders/${renderId}`, { token });

export const starRender = (renderId: string, token: string) =>
  apiFetch<RenderSummary>(`/api/renders/${renderId}/star`, {
    method: "POST",
    token,
  });

export const rejectRender = (renderId: string, token: string) =>
  apiFetch<RenderSummary>(`/api/renders/${renderId}/reject`, {
    method: "POST",
    token,
  });

export const clearRenderFeedback = (renderId: string, token: string) =>
  apiFetch<RenderSummary>(`/api/renders/${renderId}/feedback`, {
    method: "DELETE",
    token,
  });

// ─── Media Library (Phase 2.5) ──────────────────────────────────────────

export interface MediaSearchHit {
  provider: string;
  provider_asset_id: string;
  kind: "video" | "image";
  url: string;
  thumbnail_url: string;
  width: number;
  height: number;
  duration_sec: number | null;
  orientation: string;
  tags: string[];
  attribution: string;
}

export interface MediaSearchResponse {
  hits: MediaSearchHit[];
  warnings: string[];
}

export interface MediaAsset {
  id: string;
  provider: string;
  provider_asset_id: string;
  kind: "video" | "image";
  url: string;
  thumbnail_url: string | null;
  width: number | null;
  height: number | null;
  duration_sec: number | null;
  orientation: string | null;
  tags: string[];
  attribution: string | null;
}

export const searchMedia = (
  body: {
    query: string;
    kind?: "video" | "image";
    orientation?: "any" | "vertical" | "horizontal" | "square";
    providers?: ("pexels" | "pixabay")[];
    page?: number;
  },
  token: string,
) =>
  apiFetch<MediaSearchResponse>("/api/media/search", {
    method: "POST",
    body: JSON.stringify(body),
    token,
  });

export const saveMediaAsset = (
  body: Omit<MediaAsset, "id"> & { thumbnail_url?: string | null },
  token: string,
) =>
  apiFetch<MediaAsset>("/api/media/save", {
    method: "POST",
    body: JSON.stringify(body),
    token,
  });

export const listMediaAssets = (
  token: string,
  filters: { kind?: "video" | "image"; orientation?: "vertical" | "horizontal" | "square" } = {},
) => {
  const qs = new URLSearchParams();
  if (filters.kind) qs.set("kind", filters.kind);
  if (filters.orientation) qs.set("orientation", filters.orientation);
  const path = qs.toString() ? `/api/media?${qs.toString()}` : "/api/media";
  return apiFetch<MediaAsset[]>(path, { token });
};

export const deleteMediaAsset = (id: string, token: string) =>
  apiFetch<void>(`/api/media/${id}`, { method: "DELETE", token });

// ─── Billing (Phase 3) ──────────────────────────────────────────────────

export interface TierInfo {
  name: string;
  display_name: string;
  monthly_credits: number;
  watermark: boolean;
  concurrent_renders: number;
  purchaseable: boolean;
}

export interface BillingStatus {
  tier: string;
  balance: number;
  monthly_credits: number;
  watermark: boolean;
  has_active_subscription: boolean;
  stripe_customer_id: string | null;
  current_period_end: string | null;
}

export const listTiers = () => apiFetch<TierInfo[]>("/api/billing/tiers");

export const getBillingStatus = (token: string) =>
  apiFetch<BillingStatus>("/api/billing", { token });

export const createCheckout = (
  body: { tier: "pro" | "business"; success_url: string; cancel_url: string },
  token: string,
) =>
  apiFetch<{ url: string }>("/api/billing/checkout", {
    method: "POST",
    body: JSON.stringify(body),
    token,
  });

export const createPortal = (
  body: { return_url: string },
  token: string,
) =>
  apiFetch<{ url: string }>("/api/billing/portal", {
    method: "POST",
    body: JSON.stringify(body),
    token,
  });

// ─── Phase 8: smart generate ────────────────────────────────────────────

export interface SmartGenerateResponse {
  plans: GeneratedPlan[];
  best_index: number;
  best_plan: GeneratedPlan;
  reasoning: string[];
  boosted_score: number;
  rendered: RenderSummary[];
}

export const smartGenerate = (
  projectId: string,
  body: { candidates?: number; render_top?: number; seed?: number | null },
  token: string,
) =>
  apiFetch<SmartGenerateResponse>(
    `/api/projects/${projectId}/generate-smart`,
    {
      method: "POST",
      body: JSON.stringify(body),
      token,
    },
  );

// ─── Phase 9: saved prompts ─────────────────────────────────────────────

export interface SavedPrompt {
  id: string;
  user_id: string;
  template: string;
  label: string;
  template_input: Record<string, unknown>;
  use_count: number;
  last_used_at: string | null;
  created_at: string;
  updated_at: string;
}

export const listSavedPrompts = (token: string) =>
  apiFetch<SavedPrompt[]>("/api/me/saved-prompts", { token });

export const createSavedPrompt = (
  body: { template: string; label: string; template_input: Record<string, unknown> },
  token: string,
) =>
  apiFetch<SavedPrompt>("/api/me/saved-prompts", {
    method: "POST",
    body: JSON.stringify(body),
    token,
  });

export const useSavedPrompt = (
  id: string,
  body: { name?: string },
  token: string,
) =>
  apiFetch<Project>(`/api/me/saved-prompts/${id}/use`, {
    method: "POST",
    body: JSON.stringify(body),
    token,
  });

export const updateSavedPrompt = (
  id: string,
  body: { label?: string; template_input?: Record<string, unknown> },
  token: string,
) =>
  apiFetch<SavedPrompt>(`/api/me/saved-prompts/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
    token,
  });

export const deleteSavedPrompt = (id: string, token: string) =>
  apiFetch<void>(`/api/me/saved-prompts/${id}`, {
    method: "DELETE",
    token,
  });

// ─── Phase 9: dashboard insights ────────────────────────────────────────

export interface TemplatePerformance {
  template: string;
  template_name: string;
  starred: number;
  rejected: number;
  star_rate: number;
  renders: number;
}

export interface InsightSuggestion {
  template: string;
  label: string;
  prompt: string | null;
  reason: string;
}

export interface InsightsResponse {
  is_new_user: boolean;
  total_renders: number;
  renders_last_7_days: number;
  completed_renders: number;
  starred_renders: number;
  best_template: TemplatePerformance | null;
  suggestions: InsightSuggestion[];
  last_active_template: string | null;
  last_active_at: string | null;
}

export const getInsights = (token: string) =>
  apiFetch<InsightsResponse>("/api/me/insights", { token });

// ─── Phase 13: share preview links ──────────────────────────────────────

export interface RenderShare {
  id: string;
  render_id: string;
  token: string;
  is_active: boolean;
  expires_at: string | null;
  created_at: string;
}

export const getRenderShare = (jobId: string, token: string) =>
  apiFetch<RenderShare>(`/api/renders/${jobId}/share`, { token });

export const createRenderShare = (
  jobId: string,
  body: { expires_at?: string | null },
  token: string,
) =>
  apiFetch<RenderShare>(`/api/renders/${jobId}/share`, {
    method: "POST",
    body: JSON.stringify(body),
    token,
  });

export const deleteRenderShare = (jobId: string, token: string) =>
  apiFetch<void>(`/api/renders/${jobId}/share`, {
    method: "DELETE",
    token,
  });

// ─── Phase 13.5: export variants ────────────────────────────────────────

export type ExportAspect = "9:16" | "1:1" | "16:9";

export interface RenderArtifact {
  id: string;
  render_id: string;
  kind: string;
  aspect: string;
  captions: boolean;
  url: string | null;
  status: "pending" | "rendering" | "complete" | "failed";
  error: string | null;
  created_at: string;
}

export const listRenderArtifacts = (jobId: string, token: string) =>
  apiFetch<RenderArtifact[]>(`/api/renders/${jobId}/artifacts`, { token });

export const createExportVariant = (
  jobId: string,
  body: { aspect: ExportAspect; captions: boolean },
  token: string,
) =>
  apiFetch<RenderArtifact>(`/api/renders/${jobId}/export-variant`, {
    method: "POST",
    body: JSON.stringify(body),
    token,
  });
