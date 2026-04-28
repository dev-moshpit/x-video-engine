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
  is_default?: boolean;
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
}

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
export const listCaptionStyles = () =>
  apiFetch<CaptionStyleInfo[]>("/api/caption-styles");

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
