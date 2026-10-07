const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8040";

export type Task = {
  usage?: { calls: number; total_tokens: number; unknown_calls: number; simulated_calls: number; estimated_cost_cny: number };
  id: string;
  title: string;
  user_prompt: string;
  status: string;
  cost_estimate_cny: number;
  cost_confirmed: boolean;
  model_id?: string | null;
  model_name?: string | null;
  model_label?: string | null;
  skill_id?: string | null;
  expert_id?: string | null;
  plan?: { title: string; steps: { name: string; goal: string }[] } | null;
  steps: { seq: number; name: string; status: string; detail?: { evidence?: string; summary?: string; error_code?: string } }[];
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

export type ModelOption = {
  id: string;
  label: string;
  provider: string;
  model: string;
  available: boolean;
  status: "configured" | "unconfigured" | "mock";
  hint: string;
};

export async function listModels(): Promise<ModelOption[]> {
  const res = await apiFetch(`${API_BASE}/api/models`, { cache: "no-store" });
  return (await parse<{ items: ModelOption[] }>(res)).items;
}

function networkHint(err: unknown): string {
  const msg = err instanceof Error ? err.message : String(err || "");
  if (/Failed to fetch|NetworkError|Load failed|ECONNREFUSED/i.test(msg)) {
    return "暂时连接不上服务，请稍后重试。";
  }
  return msg || "请求失败";
}

export class ApiError extends Error {
  constructor(public readonly code: string, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

export function userErrorMessage(message: string): string {
  return message.replace(/^[A-Z][A-Z0-9_]{2,}:\s*/, "");
}

async function parse<T>(res: Response): Promise<T> {
  let data: any = null;
  try {
    data = await res.json();
  } catch (e) {
    throw new Error(
      res.ok
        ? networkHint(e)
        : "服务暂时无法处理请求，请稍后重试。"
    );
  }
  if (!res.ok) {
    const msg = data?.error?.message || "请求失败";
    const code = data?.error?.code || "ERROR";
    throw new ApiError(code, msg);
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
  opts?: { model_id?: string; skill_id?: string; expert_id?: string }
): Promise<Task> {
  const res = await apiFetch(`${API_BASE}/api/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      prompt,
      urls,
      ...(opts?.model_id ? { model_id: opts.model_id } : {}),
      ...(opts?.skill_id ? { skill_id: opts.skill_id } : {}),
      ...(opts?.expert_id ? { expert_id: opts.expert_id } : {}),
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

export async function rewriteReport(
  id: string,
  instruction: string,
  options?: { scope: "full" | "section"; section_id?: string; expected_version: number },
): Promise<Task> {
  const res = await apiFetch(`${API_BASE}/api/tasks/${id}/rewrite`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ instruction, ...options }),
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

export type ReportDocument = {
  markdown: string;
  version: number;
  sections: { id: string; title: string }[];
};

export type ReportVersion = {
  version: number;
  reason: string;
  instruction: string;
  created_at: string;
  characters: number;
};

export type ReportVersionPreview = ReportVersion & {
  markdown: string;
  current_version: number;
  diff: string;
  diff_truncated: boolean;
};

export type DataChart = {
  kind: "bar" | "line";
  title: string;
  labels: string[];
  values: number[];
  metric: string;
  value_format: "number" | "percent";
};

export type TableSummary = {
  id: string;
  source: string;
  sheet: string;
  row_count: number;
  column_count: number;
  headers: string[];
  metrics: {
    column: string; index: number; kind: string; aggregation: "sum" | "mean"; count: number; missing_count: number;
    invalid_count: number; sum: number; mean: number; min: number; max: number; outlier_count: number;
  }[];
  groups: { dimension: string; metric: string; rows: { label: string; value: number; count: number }[] }[];
  periods: { period: string; metric: string; aggregation: "sum" | "mean"; value: number; mom_pct: number | null; yoy_pct: number | null }[];
  date_column: string | null;
  issues: { row: number; column: string; kind: string; value: string; message: string }[];
  issue_count: number;
  warnings: string[];
  charts: DataChart[];
};

export type AnalysisSummary = {
  id: string;
  complete: boolean;
  created_at: string;
  source_count: number;
  sheet_count: number;
  row_count: number;
  cell_count: number;
  sources: { filename: string; sha256: string }[];
  tables: TableSummary[];
};

export async function getReportDocument(id: string): Promise<ReportDocument> {
  return parse<ReportDocument>(await apiFetch(API_BASE + "/api/tasks/" + id + "/report", { cache: "no-store" }));
}

export async function getTableAnalysis(id: string): Promise<AnalysisSummary | null> {
  const data = await parse<{ analysis: AnalysisSummary | null }>(await apiFetch(API_BASE + "/api/tasks/" + id + "/analysis", { cache: "no-store" }));
  return data.analysis;
}

export async function listReportVersions(id: string): Promise<{ current_version: number; items: ReportVersion[] }> {
  return parse(await apiFetch(API_BASE + "/api/tasks/" + id + "/report/versions", { cache: "no-store" }));
}

export async function previewReportVersion(id: string, version: number): Promise<ReportVersionPreview> {
  return parse(await apiFetch(API_BASE + "/api/tasks/" + id + "/report/versions/" + version, { cache: "no-store" }));
}

export async function restoreReportVersion(id: string, version: number, expectedVersion: number): Promise<Task> {
  return parse(await apiFetch(API_BASE + "/api/tasks/" + id + "/report/restore", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ version, expected_version: expectedVersion }),
  }));
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

export type ScheduleInputs = {
  token_budget: number;
  urls: string[];
  workspace_paths: string[];
  material_mode: "snapshot" | "latest";
  include_upstream_result: boolean;
};

export type Schedule = Partial<ScheduleInputs> & {
  setup_required?: boolean;
  active_run_id?: string | null;
  id: string;
  name: string;
  prompt: string;
  model_id?: string | null;
  model_name?: string | null;
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

export async function createSchedule(body: Partial<ScheduleInputs> & {
  name: string;
  prompt: string;
  model_id?: string;
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
  body: Partial<ScheduleInputs & {
    enabled: boolean;
    model_id: string;
    name: string;
    prompt: string;
    skill_id: string | null;
    expert_id: string | null;
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
  token_budget?: number;
  budget_used_tokens?: number;
  usage?: { total_tokens: number; unknown_calls: number; simulated_calls: number; calls: number };
  input_manifest?: { files?: { filename: string; sha256: string }[]; upstream?: { run_id: string; version: number } };
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
