const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8040";

export type Task = {
  id: string;
  title: string;
  user_prompt: string;
  status: string;
  cost_estimate_cny: number;
  cost_confirmed: boolean;
  skill_id?: string | null;
  expert_id?: string | null;
  plan?: { title: string; steps: { name: string; goal: string }[] } | null;
  steps: { seq: number; name: string; status: string }[];
  uploads?: { id: string; filename: string; size_bytes: number; text_excerpt?: string }[];
  has_report: boolean;
  merged_into_id?: string | null;
  merged_from_ids?: string[];
  search_snippet?: string | null;
  error_code?: string | null;
  error_message?: string | null;
};

export type Skill = {
  id: string;
  name: string;
  description: string;
  strength?: string;
  best_for?: string;
  output_shape?: string;
};

export type Expert = {
  id: string;
  name: string;
  description: string;
  default_skill_id: string;
  strength?: string;
  best_for?: string;
  output_shape?: string;
};

function networkHint(err: unknown): string {
  const msg = err instanceof Error ? err.message : String(err || "");
  if (/Failed to fetch|NetworkError|Load failed|ECONNREFUSED/i.test(msg)) {
    return "连不上后端 8040。请先启动：cd backend && source .venv/bin/activate && uvicorn app.main:app --host 127.0.0.1 --port 8040 --reload";
  }
  return msg || "请求失败";
}

async function parse<T>(res: Response): Promise<T> {
  let data: any = null;
  try {
    data = await res.json();
  } catch (e) {
    throw new Error(
      res.ok
        ? networkHint(e)
        : `请求失败（HTTP ${res.status}）。请确认后端 8040 已启动并重试。`
    );
  }
  if (!res.ok) {
    const msg = data?.error?.message || "请求失败";
    const code = data?.error?.code || "ERROR";
    throw new Error(`${code}: ${msg}`);
  }
  return data as T;
}

/** 包装 fetch，把断连转成可读中文。 */
async function apiFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(input, init);
  } catch (e) {
    throw new Error(networkHint(e));
  }
}

export async function listTasks(opts?: {
  includeMerged?: boolean;
  includeArchived?: boolean;
  q?: string;
}): Promise<Task[]> {
  const params = new URLSearchParams();
  if (opts?.includeMerged) params.set("include_merged", "true");
  if (opts?.includeArchived) params.set("include_archived", "true");
  if (opts?.q?.trim()) params.set("q", opts.q.trim());
  const q = params.toString() ? `?${params}` : "";
  const res = await apiFetch(`${API_BASE}/api/tasks${q}`, { cache: "no-store" });
  const data = await parse<{ items: Task[] }>(res);
  return data.items;
}

export async function createTask(
  prompt: string,
  urls: string[],
  opts?: { skill_id?: string; expert_id?: string }
): Promise<Task> {
  const res = await apiFetch(`${API_BASE}/api/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      prompt,
      urls,
      skill_id: opts?.skill_id || null,
      expert_id: opts?.expert_id || null,
    }),
  });
  return parse<Task>(res);
}

export async function getTask(id: string): Promise<Task> {
  const res = await apiFetch(`${API_BASE}/api/tasks/${id}`, { cache: "no-store" });
  return parse<Task>(res);
}

export async function confirmTask(id: string, confirmCost = false): Promise<Task> {
  const res = await apiFetch(`${API_BASE}/api/tasks/${id}/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirm_cost: confirmCost }),
  });
  return parse<Task>(res);
}

export async function replanTask(
  id: string,
  body?: { prompt?: string; urls?: string[] }
): Promise<Task> {
  const res = await apiFetch(`${API_BASE}/api/tasks/${id}/replan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  return parse<Task>(res);
}

export async function rewriteReport(id: string, instruction: string): Promise<Task> {
  const res = await apiFetch(`${API_BASE}/api/tasks/${id}/rewrite`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ instruction }),
  });
  return parse<Task>(res);
}

export async function pauseTask(id: string): Promise<Task> {
  const res = await apiFetch(`${API_BASE}/api/tasks/${id}/pause`, { method: "POST" });
  return parse<Task>(res);
}

export async function resumeTask(id: string): Promise<Task> {
  const res = await apiFetch(`${API_BASE}/api/tasks/${id}/resume`, { method: "POST" });
  return parse<Task>(res);
}

export async function deleteTask(id: string): Promise<void> {
  const res = await apiFetch(`${API_BASE}/api/tasks/${id}`, { method: "DELETE" });
  await parse<{ status: string }>(res);
}

export async function mergeTasks(taskIds: string[]): Promise<Task> {
  const res = await apiFetch(`${API_BASE}/api/tasks/merge`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task_ids: taskIds }),
  });
  return parse<Task>(res);
}

export async function unarchiveTask(id: string): Promise<Task> {
  const res = await apiFetch(`${API_BASE}/api/tasks/${id}/unarchive`, { method: "POST" });
  return parse<Task>(res);
}

export async function getReport(id: string): Promise<string> {
  const res = await apiFetch(`${API_BASE}/api/tasks/${id}/report`, { cache: "no-store" });
  const data = await parse<{ markdown: string }>(res);
  return data.markdown;
}

export function reportDocxUrl(id: string): string {
  return `${API_BASE}/api/tasks/${id}/report.docx`;
}

export function reportXlsxUrl(id: string): string {
  return `${API_BASE}/api/tasks/${id}/report.xlsx`;
}

export function reportPptxUrl(id: string): string {
  return `${API_BASE}/api/tasks/${id}/report.pptx`;
}

export type FeishuExportResult = {
  document_id: string;
  url: string;
  title: string;
  mock: boolean;
  identity?: "user" | "app" | string;
  space?: "my" | "app" | string;
  space_label?: string;
};

export async function exportToFeishu(
  id: string,
  confirmed = true,
  opts?: { asApp?: boolean }
): Promise<FeishuExportResult> {
  const res = await apiFetch(`${API_BASE}/api/tasks/${id}/export/feishu`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirmed, as_app: Boolean(opts?.asApp) }),
  });
  return parse(res);
}

export type FeishuOAuthStatus = {
  connected: boolean;
  expired?: boolean;
  mock: boolean;
  token_mock?: boolean;
  user_name?: string;
  has_refresh?: boolean;
  expires_at?: string;
  oauth_ready: boolean;
  redirect_uri: string;
  scopes?: string;
  identity_default: "user" | "app" | string;
  hint?: string;
};

export function feishuOAuthStartUrl(): string {
  return `${API_BASE}/api/feishu/oauth/start`;
}

export async function getFeishuOAuthStatus(): Promise<FeishuOAuthStatus> {
  const res = await apiFetch(`${API_BASE}/api/feishu/oauth/status`, { cache: "no-store" });
  return parse(res);
}

export async function disconnectFeishuOAuth(): Promise<FeishuOAuthStatus> {
  const res = await apiFetch(`${API_BASE}/api/feishu/oauth/disconnect`, { method: "POST" });
  return parse(res);
}

/** 仅 FEISHU_MOCK=1：一键模拟已授权（工程测通）。 */
export async function mockConnectFeishuOAuth(
  userName = "Mock 用户"
): Promise<FeishuOAuthStatus> {
  const res = await apiFetch(`${API_BASE}/api/feishu/oauth/mock-connect`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_name: userName }),
  });
  return parse(res);
}

export async function uploadFile(id: string, file: File): Promise<void> {
  const form = new FormData();
  form.append("file", file);
  const res = await apiFetch(`${API_BASE}/api/tasks/${id}/uploads`, {
    method: "POST",
    body: form,
  });
  await parse(res);
}

export async function attachWorkspaceRefs(id: string, paths: string[]): Promise<Task> {
  const res = await apiFetch(`${API_BASE}/api/tasks/${id}/workspace-refs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ paths }),
  });
  return parse(res);
}

export async function uploadWorkspaceTable(
  file: File,
  relDir = ""
): Promise<{ name: string; rel: string; size: number; is_dir: boolean }> {
  const form = new FormData();
  form.append("file", file);
  form.append("rel_dir", relDir);
  const res = await apiFetch(`${API_BASE}/api/workspace/upload`, {
    method: "POST",
    body: form,
  });
  return parse(res);
}

export async function getWorkspace(): Promise<{ configured: boolean; root: string }> {
  const res = await apiFetch(`${API_BASE}/api/workspace`, { cache: "no-store" });
  return parse(res);
}

export async function setWorkspace(root: string): Promise<{ configured: boolean; root: string }> {
  const res = await apiFetch(`${API_BASE}/api/workspace`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ root }),
  });
  return parse(res);
}

export async function listWorkspaceEntries(
  rel = ""
): Promise<{ name: string; rel: string; is_dir: boolean; size: number; mtime?: number }[]> {
  const q = new URLSearchParams({ rel });
  const res = await apiFetch(`${API_BASE}/api/workspace/entries?${q}`, { cache: "no-store" });
  const data = await parse<{
    items: { name: string; rel: string; is_dir: boolean; size: number; mtime?: number }[];
  }>(res);
  return data.items;
}

export async function readWorkspaceFile(rel: string): Promise<{ content: string; name: string }> {
  const q = new URLSearchParams({ rel });
  const res = await apiFetch(`${API_BASE}/api/workspace/file?${q}`, { cache: "no-store" });
  return parse(res);
}

export async function exportToWorkspace(
  taskId: string,
  formats: string[],
  confirm: boolean
): Promise<{ written: string[] }> {
  const res = await apiFetch(`${API_BASE}/api/workspace/export`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task_id: taskId, formats, confirm }),
  });
  return parse(res);
}

export async function listSkills(): Promise<Skill[]> {
  const res = await apiFetch(`${API_BASE}/api/skills`, { cache: "no-store" });
  const data = await parse<{ items: Skill[] }>(res);
  return data.items;
}

export async function listExperts(): Promise<Expert[]> {
  const res = await apiFetch(`${API_BASE}/api/experts`, { cache: "no-store" });
  const data = await parse<{ items: Expert[] }>(res);
  return data.items;
}

export type Scene = {
  id: string;
  name: string;
  category?: string;
  blurb: string;
  prompt_template: string;
  skill_id?: string | null;
  expert_id?: string | null;
  needs_table_upload?: boolean;
};

export type SceneDetect = {
  scene_id: string | null;
  confidence: number;
  skill_id: string | null;
  expert_id: string | null;
  label: string | null;
  needs_table_upload: boolean;
  reason: string;
};

export async function listScenes(): Promise<Scene[]> {
  const res = await apiFetch(`${API_BASE}/api/scenes`, { cache: "no-store" });
  const data = await parse<{ items: Scene[] }>(res);
  return data.items;
}

export async function detectScene(prompt: string): Promise<SceneDetect> {
  const res = await apiFetch(`${API_BASE}/api/scenes/detect`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
  });
  return parse<SceneDetect>(res);
}

export type Schedule = {
  id: string;
  name: string;
  prompt: string;
  skill_id?: string | null;
  expert_id?: string | null;
  interval_minutes: number;
  trigger_mode?: "interval" | "on_task_succeeded" | string;
  listen_schedule_id?: string | null;
  hook_configured?: boolean;
  webhook_path?: string | null;
  feishu_notify?: boolean;
  feishu_notify_chat_id?: string | null;
  enabled: boolean;
  next_run_at?: string | null;
  last_run_at?: string | null;
  last_task_id?: string | null;
  last_error?: string | null;
};

export type HookTokenRotate = Schedule & {
  hook_token: string;
  webhook_url: string;
  usage_hint: string;
};

/** 后端基址（Webhook URL 拼接用） */
export function apiBaseUrl(): string {
  return API_BASE.replace(/\/$/, "");
}

export function scheduleWebhookUrl(scheduleId: string): string {
  return `${apiBaseUrl()}/api/schedules/${scheduleId}/hook`;
}

export async function rotateHookToken(id: string): Promise<HookTokenRotate> {
  const res = await apiFetch(`${API_BASE}/api/schedules/${id}/rotate-hook-token`, {
    method: "POST",
  });
  return parse(res);
}

export async function listSchedules(): Promise<Schedule[]> {
  const res = await apiFetch(`${API_BASE}/api/schedules`, { cache: "no-store" });
  const data = await parse<{ items: Schedule[] }>(res);
  return data.items;
}

export async function createSchedule(body: {
  name: string;
  prompt: string;
  interval_minutes: number;
  skill_id?: string;
  expert_id?: string;
  trigger_mode?: "interval" | "on_task_succeeded";
  listen_schedule_id?: string;
  enabled?: boolean;
  feishu_notify?: boolean;
  feishu_notify_chat_id?: string | null;
}): Promise<Schedule> {
  const res = await apiFetch(`${API_BASE}/api/schedules`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return parse(res);
}

export async function patchSchedule(
  id: string,
  body: Partial<{
    enabled: boolean;
    name: string;
    prompt: string;
    interval_minutes: number;
    trigger_mode: "interval" | "on_task_succeeded";
    listen_schedule_id: string | null;
    feishu_notify: boolean;
    feishu_notify_chat_id: string | null;
  }>
): Promise<Schedule> {
  const res = await apiFetch(`${API_BASE}/api/schedules/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return parse(res);
}

export async function deleteSchedule(id: string): Promise<void> {
  const res = await apiFetch(`${API_BASE}/api/schedules/${id}`, { method: "DELETE" });
  await parse(res);
}

export async function runScheduleNow(id: string): Promise<Schedule> {
  const res = await apiFetch(`${API_BASE}/api/schedules/${id}/run-now`, { method: "POST" });
  return parse(res);
}

export type ScheduleRun = {
  id: string;
  schedule_id: string;
  task_id?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  status: string;
  error?: string | null;
  trigger?: string | null;
};

export async function listScheduleRuns(
  id: string,
  limit = 20
): Promise<ScheduleRun[]> {
  const q = new URLSearchParams({ limit: String(limit) });
  const res = await apiFetch(`${API_BASE}/api/schedules/${id}/runs?${q}`, { cache: "no-store" });
  const data = await parse<{ items: ScheduleRun[]; limit: number }>(res);
  return data.items;
}


export type ScheduleNotice = {
  run_id: string;
  schedule_id: string;
  schedule_name: string;
  task_id?: string | null;
  status: string;
  error?: string | null;
  finished_at?: string | null;
  trigger?: string | null;
};

export async function listScheduleNotices(opts?: {
  limit?: number;
  status?: "success" | "failed";
}): Promise<ScheduleNotice[]> {
  const q = new URLSearchParams();
  q.set("limit", String(opts?.limit ?? 20));
  if (opts?.status) q.set("status", opts.status);
  const res = await apiFetch(`${API_BASE}/api/schedules/notices?${q}`, { cache: "no-store" });
  const data = await parse<{ items: ScheduleNotice[]; limit: number }>(res);
  return data.items;
}

export type RuntimeHealth = {
  status: string;
  service?: string;
  llm_mock?: boolean;
  search_mock?: boolean;
  llm_configured?: boolean;
  search_configured?: boolean;
  llm_model?: string;
};

export async function getRuntimeHealth(): Promise<RuntimeHealth> {
  const res = await apiFetch(`${API_BASE}/health`, { cache: "no-store" });
  if (!res.ok) throw new Error("健康检查失败");
  return (await res.json()) as RuntimeHealth;
}

export type FeishuNotifyOn = "off" | "failed" | "always";

export type FeishuNotifyLogItem = {
  status: string;
  mock?: boolean;
  message?: string;
  chat_id?: string | null;
  code?: string;
  schedule_id?: string;
  schedule_name?: string;
  run_id?: string;
  task_id?: string | null;
  run_status?: string;
  sent_at?: string;
  text_preview?: string;
};

export type FeishuNotifySettings = {
  notify_on: FeishuNotifyOn | string;
  chat_id: string;
  chat_id_configured: boolean;
  app_configured: boolean;
  feishu_mock: boolean;
  hint: string;
  recent: FeishuNotifyLogItem[];
};

export async function getFeishuNotifySettings(): Promise<FeishuNotifySettings> {
  const res = await apiFetch(`${API_BASE}/api/feishu/notify`, { cache: "no-store" });
  return parse(res);
}

export async function putFeishuNotifySettings(body: {
  notify_on?: FeishuNotifyOn;
  chat_id?: string;
}): Promise<FeishuNotifySettings> {
  const res = await apiFetch(`${API_BASE}/api/feishu/notify`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return parse(res);
}

export async function listFeishuNotifyLog(limit = 20): Promise<FeishuNotifyLogItem[]> {
  const q = new URLSearchParams({ limit: String(limit) });
  const res = await apiFetch(`${API_BASE}/api/feishu/notify/log?${q}`, { cache: "no-store" });
  const data = await parse<{ items: FeishuNotifyLogItem[]; limit: number }>(res);
  return data.items;
}
