"use client";

import { Fragment, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  Expert,
  HookTokenRotate,
  RuntimeHealth,
  Schedule,
  ScheduleNotice,
  ScheduleRun,
  Scene,
  SceneDetect,
  Skill,
  Task,
  attachWorkspaceRefs,
  confirmTask,
  createSchedule,
  createTask,
  deleteSchedule,
  deleteTask,
  detectScene,
  exportToFeishu,
  FeishuExportResult,
  FeishuNotifySettings,
  FeishuOAuthStatus,
  disconnectFeishuOAuth,
  feishuOAuthStartUrl,
  getFeishuNotifySettings,
  getFeishuOAuthStatus,
  mockConnectFeishuOAuth,
  getReport,
  getRuntimeHealth,
  getWorkspace,
  listExperts,
  listScenes,
  listScheduleNotices,
  listScheduleRuns,
  listSchedules,
  listSkills,
  listTasks,
  listWorkspaceEntries,
  mergeTasks,
  patchSchedule,
  pauseTask,
  putFeishuNotifySettings,
  readWorkspaceFile,
  replanTask,
  reportDocxUrl,
  reportPptxUrl,
  reportXlsxUrl,
  resumeTask,
  rewriteReport,
  rotateHookToken,
  runScheduleNow,
  scheduleWebhookUrl,
  unarchiveTask,
  uploadFile,
  uploadWorkspaceTable,
} from "@/lib/api";
import { exportLabel, type ExportKind } from "@/lib/export-prefs";
import { linkifyReport } from "@/lib/linkify-report";
import {
  ackRunIds,
  formatNoticeLine,
  loadAckedRunIds,
  unreadFailures,
} from "@/lib/schedule-notices";

type Panel = "compose" | "task" | "workspace" | "schedules";
type WorkspaceEntry = { name: string; rel: string; is_dir: boolean; size: number; mtime?: number };

type WorkspaceEntryCategory =
  | "folder"
  | "table"
  | "document"
  | "image"
  | "pdf"
  | "audio-video"
  | "archive"
  | "code"
  | "other";

const WORKSPACE_CATEGORY_ORDER: WorkspaceEntryCategory[] = [
  "folder",
  "table",
  "document",
  "image",
  "pdf",
  "audio-video",
  "archive",
  "code",
  "other",
];

function isTableFileName(name: string): boolean {
  return /\.(csv|xlsx)$/i.test(name);
}

function workspaceEntryCategory(entry: WorkspaceEntry): WorkspaceEntryCategory {
  if (entry.is_dir) return "folder";
  const extension = entry.name.match(/\.([^.]+)$/)?.[1].toLowerCase() || "";
  if (["csv", "tsv", "xls", "xlsx", "ods", "numbers"].includes(extension)) return "table";
  if (["doc", "docx", "md", "mdx", "odt", "rtf", "txt"].includes(extension)) return "document";
  if (["png", "jpg", "jpeg", "gif", "webp", "svg", "bmp", "ico", "heic"].includes(extension)) return "image";
  if (extension === "pdf") return "pdf";
  if (["mp3", "wav", "m4a", "flac", "ogg", "mp4", "mov", "avi", "mkv", "webm"].includes(extension)) {
    return "audio-video";
  }
  if (["zip", "rar", "7z", "tar", "gz", "bz2"].includes(extension)) return "archive";
  if (
    [
      "c",
      "cpp",
      "css",
      "go",
      "h",
      "html",
      "java",
      "js",
      "json",
      "jsx",
      "py",
      "rs",
      "sh",
      "sql",
      "ts",
      "tsx",
      "xml",
      "yml",
      "yaml",
    ].includes(extension)
  ) {
    return "code";
  }
  return "other";
}

function compareWorkspaceEntries(a: WorkspaceEntry, b: WorkspaceEntry): number {
  const categoryDiff =
    WORKSPACE_CATEGORY_ORDER.indexOf(workspaceEntryCategory(a)) -
    WORKSPACE_CATEGORY_ORDER.indexOf(workspaceEntryCategory(b));
  if (categoryDiff !== 0) return categoryDiff;
  return a.name.localeCompare(b.name, "zh-CN", { numeric: true, sensitivity: "base" });
}

const STATUS_LABEL: Record<string, string> = {
  draft: "草稿",
  planning: "准备中",
  plan_ready: "待开始",
  running: "生成中",
  paused: "已暂停",
  succeeded: "已完成",
  failed: "失败",
  merged: "已合并",
  archived: "已归档",
};

const SCENE_CATEGORY_ORDER = ["research", "writing", "data"] as const;
const SCENE_CATEGORY_LABEL: Record<string, string> = {
  research: "调研",
  writing: "写稿",
  data: "数据",
};

function statusTone(status: string): string {
  if (status === "succeeded") return "bg-[var(--accent)]";
  if (status === "failed") return "bg-[var(--danger)]";
  if (status === "running" || status === "planning") return "bg-[#6e6b7a]";
  if (status === "paused") return "bg-[#9a97a8]";
  if (status === "plan_ready") return "bg-[var(--accent)]";
  if (status === "merged" || status === "archived") return "bg-[#b8b4c4]";
  return "bg-[#d4d0dc]";
}

const MERGE_NOTE_MARK = "【已合并任务】";

/** User-typed body only — strip merge appendix that lists other titles. */
function searchablePrompt(raw: string): string {
  const i = raw.indexOf(MERGE_NOTE_MARK);
  return (i >= 0 ? raw.slice(0, i) : raw).trim();
}

/** Side-rail label: when searching, prefer matching prompt / report snippet over a stale plan title. */
function taskRailLabel(
  task: { title?: string; user_prompt?: string; search_snippet?: string | null },
  query: string
): string {
  const title = (task.title || "").trim();
  const prompt = searchablePrompt(task.user_prompt || "").replace(/\s+/g, " ");
  const q = query.trim();
  if (!q) return title || "未命名";
  const needle = q.toLowerCase();
  if (title && title.toLowerCase().includes(needle)) return title;
  if (prompt) {
    const lower = prompt.toLowerCase();
    const idx = lower.indexOf(needle);
    if (idx >= 0) {
      const snip = prompt.slice(idx, idx + 28);
      return snip + (prompt.length > idx + 28 ? "…" : "");
    }
  }
  const snippet = (task.search_snippet || "").trim();
  if (snippet) return snippet;
  return title || "未命名";
}

function formatNextRun(value?: string | null): string {
  if (!value) return "—";
  try {
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return value;
    return d.toLocaleString("zh-CN", { hour12: false });
  } catch {
    return value;
  }
}

function BackHomeArrow({
  onClick,
  label = "返回首页",
}: {
  onClick: () => void;
  label?: string;
}) {
  return (
    <button
      className="btn-ghost !h-8 !w-8 !p-0"
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
    >
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
        <path
          d="M10.5 3.5 6 8l4.5 4.5M6.5 8H13"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </button>
  );
}

export default function HomePage() {
  const [panel, setPanel] = useState<Panel>("compose");
  /** 从任务页返回时落到的面板（如自动化「立即跑」→ 回自动化）；无则回首页 */
  const [taskBackTo, setTaskBackTo] = useState<Panel | null>(null);
  const taskBackToRef = useRef<Panel | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [selected, setSelected] = useState<Task | null>(null);
  const [prompt, setPrompt] = useState("");
  const [urls, setUrls] = useState("");
  const [report, setReport] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [wsRoot, setWsRoot] = useState("");
  const [wsEntries, setWsEntries] = useState<WorkspaceEntry[]>([]);
  const [wsPreview, setWsPreview] = useState("");
  const [wsFilter, setWsFilter] = useState<"tables" | "all">("tables");
  const [wsSearch, setWsSearch] = useState("");
  const [skills, setSkills] = useState<Skill[]>([]);
  const [experts, setExperts] = useState<Expert[]>([]);
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [activeSceneId, setActiveSceneId] = useState("");
  const [pinnedSceneCategory, setPinnedSceneCategory] = useState("writing");
  const [hoverSceneCategory, setHoverSceneCategory] = useState("");
  const sceneChildrenRef = useRef<HTMLDivElement | null>(null);
  const [sceneScroll, setSceneScroll] = useState({
    canUp: false,
    canDown: false,
    moreCount: 0,
  });
  const [detectHint, setDetectHint] = useState<SceneDetect | null>(null);
  const [skillId, setSkillId] = useState("");
  const [expertId, setExpertId] = useState("");
  const [shelfLocked, setShelfLocked] = useState(false);
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [expandedRunScheduleId, setExpandedRunScheduleId] = useState<string | null>(null);
  const [scheduleRuns, setScheduleRuns] = useState<ScheduleRun[]>([]);
  const [runsLoading, setRunsLoading] = useState(false);
  const [expandedHookScheduleId, setExpandedHookScheduleId] = useState<string | null>(null);
  const [hookReveal, setHookReveal] = useState<HookTokenRotate | null>(null);
  const [hookCopyTip, setHookCopyTip] = useState("");
  const [feishuNotify, setFeishuNotify] = useState<FeishuNotifySettings | null>(null);
  const [feishuNotifyChatDraft, setFeishuNotifyChatDraft] = useState("");
  const [feishuNotifySaving, setFeishuNotifySaving] = useState(false);
  const [schedFeishuNotify, setSchedFeishuNotify] = useState(false);
  const [scheduleNotices, setScheduleNotices] = useState<ScheduleNotice[]>([]);
  const [ackedRunIds, setAckedRunIds] = useState<Set<string>>(() => new Set());
  const [schedToast, setSchedToast] = useState<ScheduleNotice | null>(null);
  const schedToastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [schedName, setSchedName] = useState("自动化周报");
  const [schedPrompt, setSchedPrompt] = useState("");
  const [schedInterval, setSchedInterval] = useState(60);
  const [schedTriggerMode, setSchedTriggerMode] = useState<"interval" | "on_task_succeeded">("interval");
  const [schedListenId, setSchedListenId] = useState("");
  const [schedSkillId, setSchedSkillId] = useState("");
  const [schedExpertId, setSchedExpertId] = useState("");
  const [showMore, setShowMore] = useState(false);
  const [showSchedForm, setShowSchedForm] = useState(false);
  const [needsTableUpload, setNeedsTableUpload] = useState(false);
  const [pendingTableFiles, setPendingTableFiles] = useState<File[]>([]);
  const [pendingWsTables, setPendingWsTables] = useState<string[]>([]);
  const [wsRel, setWsRel] = useState("");
  const [shelfTab, setShelfTab] = useState<"experts" | "skills">("experts");
  const [shelfQuery, setShelfQuery] = useState("");
  const [showShelf, setShowShelf] = useState(false);
  const [shelfDraftExpertId, setShelfDraftExpertId] = useState("");
  const [shelfDraftSkillId, setShelfDraftSkillId] = useState("");
  const [taskRailOpen, setTaskRailOpen] = useState(true);
  const [taskQuery, setTaskQuery] = useState("");
  const [taskQueryDraft, setTaskQueryDraft] = useState("");
  const [manageMode, setManageMode] = useState(false);
  const [mergeIds, setMergeIds] = useState<string[]>([]);
  const [expandedMergeIds, setExpandedMergeIds] = useState<string[]>([]);
  const [runtime, setRuntime] = useState<RuntimeHealth | null>(null);
  const [feishuExport, setFeishuExport] = useState<FeishuExportResult | null>(null);
  const [feishuCopyTip, setFeishuCopyTip] = useState("");
  const [feishuOAuth, setFeishuOAuth] = useState<FeishuOAuthStatus | null>(null);
  const [feishuOAuthBusy, setFeishuOAuthBusy] = useState(false);
  const [feishuChooserOpen, setFeishuChooserOpen] = useState(false);
  const [feishuMoreOpen, setFeishuMoreOpen] = useState(false);
  const [copyReportTip, setCopyReportTip] = useState("");
  const [showMoreExports, setShowMoreExports] = useState(false);
  const [activeExportKind, setActiveExportKind] = useState<ExportKind>("md");

  async function refreshWorkspace(rel?: string) {
    const w = await getWorkspace();
    setWsRoot(w.root || "");
    const nextRel = rel === undefined ? wsRel : rel;
    if (rel !== undefined) setWsRel(rel);
    if (w.configured) {
      setWsEntries(await listWorkspaceEntries(nextRel));
    } else {
      setWsEntries([]);
    }
  }

  async function refreshSchedules() {
    setSchedules(await listSchedules());
  }

  async function refreshFeishuNotify() {
    try {
      const s = await getFeishuNotifySettings();
      setFeishuNotify(s);
      setFeishuNotifyChatDraft(s.chat_id || "");
    } catch {
      /* soft */
    }
  }


  async function refreshFeishuOAuth() {
    try {
      const s = await getFeishuOAuthStatus();
      setFeishuOAuth(s);
    } catch {
      /* ignore */
    }
  }

  async function onConnectFeishu() {
    setFeishuOAuthBusy(true);
    setError("");
    try {
      // 先拉最新状态，避免后端刚恢复时 mock 标记仍为空误走真机授权
      let status = feishuOAuth;
      try {
        status = await getFeishuOAuthStatus();
        setFeishuOAuth(status);
      } catch {
        /* 保留本地缓存；真正请求失败时下方会抛错 */
      }
      // Mock：直接 mock-connect；真实：开授权页（授权完回到本页再刷新）
      if (status?.mock) {
        const s = await mockConnectFeishuOAuth();
        setFeishuOAuth(s);
      } else {
        window.open(feishuOAuthStartUrl(), "_blank", "noopener,noreferrer");
        const started = Date.now();
        const poll = window.setInterval(() => {
          refreshFeishuOAuth().catch(() => undefined);
          if (Date.now() - started > 120000) window.clearInterval(poll);
        }, 2500);
        const onFocus = () => {
          refreshFeishuOAuth().catch(() => undefined);
        };
        window.addEventListener("focus", onFocus);
        window.setTimeout(() => {
          window.clearInterval(poll);
          window.removeEventListener("focus", onFocus);
        }, 120000);
      }
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setFeishuOAuthBusy(false);
    }
  }

  async function onDisconnectFeishu() {
    if (!window.confirm("断开飞书账号？之后导出将改用应用空间兜底（若已配置应用凭证）。")) {
      return;
    }
    setFeishuOAuthBusy(true);
    setError("");
    try {
      const s = await disconnectFeishuOAuth();
      setFeishuOAuth(s);
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setFeishuOAuthBusy(false);
    }
  }

  async function saveFeishuNotify(patch: {
    notify_on?: "off" | "failed" | "always";
    chat_id?: string;
  }) {
    setFeishuNotifySaving(true);
    setError("");
    try {
      const s = await putFeishuNotifySettings(patch);
      setFeishuNotify(s);
      if (patch.chat_id !== undefined) setFeishuNotifyChatDraft(s.chat_id || "");
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setFeishuNotifySaving(false);
    }
  }

  function formatFeishuLatestLine(): string {
    const latest = feishuNotify?.recent?.[0];
    if (!latest) return "最近一次：还没有";
    const mode =
      latest.mock || latest.status === "mocked"
        ? "模拟"
        : latest.status === "sent"
          ? "真实"
          : feishuNotify?.feishu_mock
            ? "模拟"
            : "真实";
    const outcome =
      latest.status === "skipped"
        ? "跳过"
        : latest.status === "mocked" || latest.status === "sent"
          ? "成功"
          : latest.message || latest.status || "—";
    const when = latest.sent_at ? latest.sent_at.replace("T", " ").slice(0, 19) : "—";
    return `最近一次：${mode} · ${outcome} · ${when}`;
  }

  async function refreshScheduleNotices(opts?: { toastNewestUnreadFail?: boolean }) {
    try {
      const items = await listScheduleNotices({ limit: 20 });
      setScheduleNotices(items);
      const acked = loadAckedRunIds();
      setAckedRunIds(new Set(acked));
      if (opts?.toastNewestUnreadFail) {
        const fails = unreadFailures(items, acked);
        if (fails[0]) showSchedToast(fails[0]);
      }
    } catch {
      /* soft: notices are non-blocking */
    }
  }

  function showSchedToast(notice: ScheduleNotice) {
    setSchedToast(notice);
    if (schedToastTimer.current) clearTimeout(schedToastTimer.current);
    schedToastTimer.current = setTimeout(() => setSchedToast(null), 14000);
  }

  function dismissSchedToast() {
    if (schedToastTimer.current) clearTimeout(schedToastTimer.current);
    setSchedToast(null);
  }

  function markNoticesRead(runIds: string[]) {
    const next = ackRunIds(runIds);
    setAckedRunIds(new Set(next));
  }

  function openNotice(notice: ScheduleNotice) {
    markNoticesRead([notice.run_id]);
    dismissSchedToast();
    if (notice.task_id) {
      void selectTask(notice.task_id, { backTo: "schedules" });
    } else {
      setPanel("schedules");
      setShowSchedForm(false);
    }
  }

  async function toggleScheduleRuns(scheduleId: string) {
    if (expandedRunScheduleId === scheduleId) {
      setExpandedRunScheduleId(null);
      setScheduleRuns([]);
      return;
    }
    setExpandedRunScheduleId(scheduleId);
    setRunsLoading(true);
    setError("");
    try {
      const items = await listScheduleRuns(scheduleId, 20);
      setScheduleRuns(items);
    } catch (e: any) {
      setError(e.message || String(e));
      setExpandedRunScheduleId(null);
      setScheduleRuns([]);
    } finally {
      setRunsLoading(false);
    }
  }

  async function refreshExpandedRuns() {
    if (!expandedRunScheduleId) return;
    try {
      setScheduleRuns(await listScheduleRuns(expandedRunScheduleId, 20));
    } catch {
      /* keep existing list on soft refresh failure */
    }
  }

  async function refresh(selectId?: string | null) {
    const q = taskQuery.trim();
    const items = await listTasks({
      includeMerged: true,
      q: q || undefined,
    });
    // Backend is source of truth for q (title / prompt / report); keep defense only for empty q.
    setTasks(items);
    if (selectId === null) {
      setSelected(null);
      setReport("");
      return;
    }
    const id = selectId ?? selected?.id;
    if (id) {
      const t = items.find((x) => x.id === id);
      if (!t) {
        setSelected(null);
        setReport("");
        return;
      }
      setSelected(t);
      if (t.merged_into_id) {
        setExpandedMergeIds((prev) =>
          prev.includes(t.merged_into_id!) ? prev : [...prev, t.merged_into_id!]
        );
      } else if ((t.merged_from_ids || []).length > 0) {
        setExpandedMergeIds((prev) => (prev.includes(t.id) ? prev : [...prev, t.id]));
      }
      if (t.has_report) {
        setReport(await getReport(t.id));
      } else {
        setReport("");
      }
    }
  }

  useEffect(() => {
    refresh().catch((e) => setError(String(e.message || e)));
    refreshWorkspace().catch(() => undefined);
    refreshSchedules().catch(() => undefined);
    refreshFeishuNotify().catch(() => undefined);
    refreshFeishuOAuth().catch(() => undefined);
    try {
      setAckedRunIds(loadAckedRunIds());
    } catch {
      /* ignore */
    }
    refreshScheduleNotices({ toastNewestUnreadFail: true }).catch(() => undefined);
    getRuntimeHealth()
      .then(setRuntime)
      .catch(() => setRuntime(null));
    Promise.all([listSkills(), listExperts()])
      .then(([s, e]) => {
        setSkills(s);
        setExperts(e);
      })
      .catch(() => undefined);
    listScenes()
      .then((sc) => setScenes(sc))
      .catch(() => undefined);
    try {
      if (window.localStorage.getItem("ai_office_task_rail_open") === "0") {
        setTaskRailOpen(false);
      }
    } catch {
      /* ignore */
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* schedule-notice-poll: soft refresh so interval 跑次失败可站内可见 */
  useEffect(() => {
    const tick = () => {
      refreshScheduleNotices().catch(() => undefined);
    };
    const id = window.setInterval(tick, 45000);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    return () => {
      if (schedToastTimer.current) clearTimeout(schedToastTimer.current);
    };
  }, []);

  function toggleTaskRail(next?: boolean) {
    setTaskRailOpen((prev) => {
      const value = typeof next === "boolean" ? next : !prev;
      try {
        window.localStorage.setItem("ai_office_task_rail_open", value ? "1" : "0");
      } catch {
        /* ignore */
      }
      return value;
    });
  }

  function startNewCompose() {
    setTaskBackTo(null);
    setPanel("compose");
    setSelected(null);
    setReport("");
    setPrompt("");
    setUrls("");
    setActiveSceneId("");
    setDetectHint(null);
    setSkillId("");
    setExpertId("");
    setShelfLocked(false);
    setNeedsTableUpload(false);
    clearTableSelection();
    setShowMore(false);
    setShowShelf(false);
    setError("");
    setFeishuExport(null);
    setFeishuChooserOpen(false);
    setFeishuMoreOpen(false);
    setCopyReportTip("");
    setShowMoreExports(false);
    setActiveExportKind("md");
  }

  const sidebarToggleIcon = (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <rect
        x="2.25"
        y="3"
        width="13.5"
        height="12"
        rx="1.5"
        stroke="currentColor"
        strokeWidth="1.4"
      />
      <path d="M7 3v12" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  );

  const iconRailHome = (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path
        d="M3.5 9.2 10 3.5l6.5 5.7V16a1 1 0 0 1-1 1h-3.4v-4.2H7.9V17H4.5a1 1 0 0 1-1-1V9.2Z"
        stroke="currentColor"
        strokeWidth="1.45"
        strokeLinejoin="round"
      />
    </svg>
  );
  const iconRailClock = (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <circle cx="10" cy="10" r="6.6" stroke="currentColor" strokeWidth="1.45" />
      <path
        d="M10 6.4V10l2.6 1.7"
        stroke="currentColor"
        strokeWidth="1.45"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
  const iconRailLibrary = (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <rect x="3.2" y="4.2" width="3.1" height="11.6" rx="0.7" stroke="currentColor" strokeWidth="1.4" />
      <rect x="8.35" y="3.2" width="3.1" height="12.6" rx="0.7" stroke="currentColor" strokeWidth="1.4" />
      <rect x="13.5" y="5.4" width="3.1" height="10.4" rx="0.7" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  );
  const iconRailAutomate = (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <rect
        x="3.4"
        y="3.4"
        width="8.4"
        height="8.4"
        rx="1.4"
        stroke="currentColor"
        strokeWidth="1.45"
      />
      <rect
        x="8.2"
        y="8.2"
        width="8.4"
        height="8.4"
        rx="1.4"
        stroke="currentColor"
        strokeWidth="1.45"
      />
    </svg>
  );
  const iconRailMore = (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <circle cx="5" cy="10" r="1.15" fill="currentColor" />
      <circle cx="10" cy="10" r="1.15" fill="currentColor" />
      <circle cx="15" cy="10" r="1.15" fill="currentColor" />
    </svg>
  );

  function goToTaskPanel() {
    toggleTaskRail(true);
    setTaskBackTo(null);
    if (selected) {
      setPanel("task");
      return;
    }
    const first = tasks.find((t) => t.status !== "merged");
    if (first) void selectTask(first.id);
    else setPanel("task");
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setTaskQuery(taskQueryDraft.trim());
    }, 280);
    return () => window.clearTimeout(timer);
  }, [taskQueryDraft]);

  useEffect(() => {
    refresh(selected?.id).catch((e) => setError(String(e.message || e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskQuery]);

  useEffect(() => {
    if (!selected || !["running", "planning"].includes(selected.status)) return;
    const timer = setInterval(() => {
      refresh(selected.id).catch(() => undefined);
    }, 1000);
    return () => clearInterval(timer);
  }, [selected?.id, selected?.status]);

  useEffect(() => {
    const text = prompt.trim();
    if (!text || text.length < 2) {
      setDetectHint(null);
      return;
    }
    const timer = setTimeout(() => {
      detectScene(text)
        .then((d) => {
          if (!(d.scene_id && d.confidence >= 0.5)) {
            setDetectHint(null);
            return;
          }
          setDetectHint(d);
          // Free-typing: keep skill/expert in sync with latest detect.
          // Shelf picks stay until user clears them.
          if (!shelfLocked) {
            setSkillId(d.skill_id || "");
            setExpertId(d.expert_id || "");
            setActiveSceneId(d.scene_id || "");
            setNeedsTableUpload(Boolean(d.needs_table_upload));
            if (!d.needs_table_upload) clearTableSelection();
            const matched = scenes.find((s) => s.id === d.scene_id);
            if (matched?.category) setPinnedSceneCategory(matched.category);
          }
        })
        .catch(() => setDetectHint(null));
    }, 350);
    return () => clearTimeout(timer);
  }, [prompt, scenes, shelfLocked]);

  async function selectTask(id: string, opts?: { backTo?: Panel }) {
    const backTo = opts?.backTo ?? null;
    setTaskBackTo(backTo);
    if (backTo) {
      // 压入历史，使浏览器返回也能回到来源页（如自动化）
      window.history.pushState({ aiCompanion: { panel: "task", backTo } }, "");
    }
    setPanel("task");
    setFeishuExport(null);
    setFeishuCopyTip("");
    setFeishuChooserOpen(false);
    setFeishuMoreOpen(false);
    setCopyReportTip("");
    setShowMoreExports(false);
    setActiveExportKind("md");
    await refresh(id);
  }

  function handleHeaderBack() {
    if (panel === "task" && taskBackTo) {
      const st = window.history.state as { aiCompanion?: { panel?: string; backTo?: Panel } } | null;
      if (st?.aiCompanion?.panel === "task" && st.aiCompanion.backTo === taskBackTo) {
        window.history.back();
        return;
      }
      const dest = taskBackTo;
      setTaskBackTo(null);
      setPanel(dest);
      if (dest === "schedules") setShowSchedForm(false);
      return;
    }
    startNewCompose();
  }

  useEffect(() => {
    taskBackToRef.current = taskBackTo;
  }, [taskBackTo]);

  useEffect(() => {
    const onPopState = () => {
      const dest = taskBackToRef.current;
      if (!dest) return;
      setTaskBackTo(null);
      setPanel(dest);
      if (dest === "schedules") setShowSchedForm(false);
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  function toggleMergeId(id: string) {
    setMergeIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  function toggleExpandMerge(id: string) {
    setExpandedMergeIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  }

  async function onMergeTasks() {
    if (mergeIds.length < 2) return;
    const ok = window.confirm(
      `将合并 ${mergeIds.length} 条任务：保留最新报告作为主任务，其余收纳到主任务下（点开可分别查看）。确定？`
    );
    if (!ok) return;
    setBusy(true);
    setError("");
    try {
      const primary = await mergeTasks(mergeIds);
      setManageMode(false);
      setMergeIds([]);
      setExpandedMergeIds((prev) =>
        prev.includes(primary.id) ? prev : [...prev, primary.id]
      );
      await refresh(primary.id);
      setTaskBackTo(null);
      setPanel("task");
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onCreate() {
    setBusy(true);
    setError("");
    try {
      const urlList = urls
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean)
        .slice(0, 3);
      const effectiveSkill = skillId || detectHint?.skill_id || undefined;
      const effectiveExpert = expertId || detectHint?.expert_id || undefined;
      const wantTable =
        needsTableUpload ||
        effectiveSkill === "table_analysis" ||
        Boolean(detectHint?.needs_table_upload);
      if (wantTable && pendingTableFiles.length === 0 && pendingWsTables.length === 0) {
        setError("表格分析请先上传 CSV/Excel，或从资料库选一张表。");
        setBusy(false);
        return;
      }
      const t = await createTask(prompt, urlList, {
        skill_id: effectiveSkill,
        expert_id: effectiveExpert,
      });
      for (const file of pendingTableFiles.slice(0, 3)) {
        await uploadFile(t.id, file);
      }
      if (pendingWsTables.length > 0) {
        await attachWorkspaceRefs(t.id, pendingWsTables.slice(0, 3));
      }
      if (wantTable) {
        await replanTask(t.id);
      }
      setPrompt("");
      setUrls("");
      setActiveSceneId("");
      setDetectHint(null);
      setPendingTableFiles([]);
      setPendingWsTables([]);
      setNeedsTableUpload(wantTable);
      setTaskBackTo(null);
      setPanel("task");
      await refresh(t.id);
      // 简洁交付：默认自动开跑，用户只等成品（费用超限仍会停住提示确认）
      try {
        await confirmTask(t.id, false);
        await refresh(t.id);
      } catch (e: any) {
        const msg = e.message || String(e);
        setError(msg);
        await refresh(t.id);
      }
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  function clearTableSelection() {
    setPendingTableFiles([]);
    setPendingWsTables([]);
  }

  async function applyScene(scene: Scene) {
    setActiveSceneId(scene.id);
    setPinnedSceneCategory(scene.category || "writing");
    setPrompt(scene.prompt_template);
    setSkillId(scene.skill_id || "");
    setExpertId(scene.expert_id || "");
    setNeedsTableUpload(Boolean(scene.needs_table_upload));
    setDetectHint(null);
    setShelfLocked(true);
    if (!scene.needs_table_upload) clearTableSelection();
  }

  function pickTableForAnalysis(rel: string) {
    const tableScene = scenes.find((s) => s.id === "table_analysis");
    if (tableScene) {
      void applyScene(tableScene);
    } else {
      setNeedsTableUpload(true);
      setSkillId("table_analysis");
      setActiveSceneId("table_analysis");
    }
    setPendingWsTables((prev) => (prev.includes(rel) ? prev : [...prev, rel].slice(0, 3)));
    setPendingTableFiles([]);
    setPanel("compose");
  }

  async function onWorkspaceUpload(file: File | null) {
    if (!file) return;
    if (!isTableFileName(file.name)) {
      setError("资料库表格上传仅支持 CSV 或 Excel（.xlsx）");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await uploadWorkspaceTable(file, wsRel);
      await refreshWorkspace(wsRel);
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onConfirm(confirmCost = false) {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      await confirmTask(selected.id, confirmCost);
      await refresh(selected.id);
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onUpload(file: File | null) {
    if (!selected || !file) return;
    setBusy(true);
    setError("");
    try {
      await uploadFile(selected.id, file);
      const isTable = /\.(csv|xlsx)$/i.test(file.name) || skillId === "table_analysis" || needsTableUpload;
      if (isTable && ["plan_ready", "failed", "paused"].includes(selected.status)) {
        await replanTask(selected.id);
      }
      await refresh(selected.id);
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  function reportFileStem() {
    const raw = (selected?.title || "report").trim() || "report";
    return raw.replace(/[\\/:*?"<>|\r\n\t]+/g, "_").replace(/\s+/g, " ").trim().slice(0, 80) || "report";
  }

  function downloadReport() {
    if (!report || !selected) return;
    const blob = new Blob([report], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${reportFileStem()}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function downloadActiveExport() {
    if (!selected) return;
    const kind = activeExportKind;
    if (kind === "md") {
      downloadReport();
      return;
    }
    const href =
      kind === "docx"
        ? reportDocxUrl(selected.id)
        : kind === "xlsx"
          ? reportXlsxUrl(selected.id)
          : reportPptxUrl(selected.id);
    const a = document.createElement("a");
    a.href = href;
    a.download = `${reportFileStem()}.${kind === "docx" ? "docx" : kind === "xlsx" ? "xlsx" : "pptx"}`;
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  async function copyReportText() {
    if (!report) return;
    try {
      await navigator.clipboard.writeText(report);
      setCopyReportTip("已复制正文");
      window.setTimeout(() => setCopyReportTip(""), 2000);
    } catch {
      setError("复制失败，请手动全选报告正文。");
    }
  }

  function onExportFeishuClick() {
    if (!selected) return;
    setFeishuMoreOpen(false);
    if (!feishuOAuth?.connected) {
      setFeishuChooserOpen(true);
      return;
    }
    void doExportFeishu(false);
  }

  async function doExportFeishu(asApp: boolean) {
    if (!selected) return;
    setFeishuChooserOpen(false);
    setFeishuMoreOpen(false);
    const where = asApp ? "应用空间" : "「我的」云文档";
    if (
      !window.confirm(
        `确认导出到飞书？文档将写到${where}，并尽量开通「有链接可阅读」。打开链接后若未登录，请先登录飞书再查看。`
      )
    ) {
      return;
    }
    setBusy(true);
    setError("");
    setFeishuCopyTip("");
    try {
      const r = await exportToFeishu(selected.id, true, { asApp });
      setFeishuExport(r);
      await refreshFeishuOAuth();
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onChooserConnect() {
    setFeishuChooserOpen(false);
    await onConnectFeishu();
  }

  async function copyFeishuLink() {
    if (!feishuExport?.url) return;
    try {
      await navigator.clipboard.writeText(feishuExport.url);
      setFeishuCopyTip("已复制，可粘贴到浏览器打开");
    } catch {
      try {
        const ta = document.createElement("textarea");
        ta.value = feishuExport.url;
        ta.style.position = "fixed";
        ta.style.left = "-9999px";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
        setFeishuCopyTip("已复制，可粘贴到浏览器打开");
      } catch {
        setFeishuCopyTip("复制失败，请手动选中下方链接");
      }
    }
  }

  async function onCreateSchedule() {
    if (!schedPrompt.trim()) return;
    if (schedTriggerMode === "on_task_succeeded" && !schedListenId) {
      setError("请选择要监听的自动化（某条成功后再跑本条）");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await createSchedule({
        name: schedName.trim() || "自动化",
        prompt: schedPrompt.trim(),
        interval_minutes: Math.max(1, Number(schedInterval) || 60),
        skill_id: schedSkillId || undefined,
        expert_id: schedExpertId || undefined,
        trigger_mode: schedTriggerMode,
        listen_schedule_id:
          schedTriggerMode === "on_task_succeeded" ? schedListenId || undefined : undefined,
        feishu_notify: schedFeishuNotify,
      });
      setSchedPrompt("");
      setSchedName("自动化周报");
      setSchedInterval(60);
      setSchedTriggerMode("interval");
      setSchedListenId("");
      setSchedFeishuNotify(false);
      setShowSchedForm(false);
      await refreshSchedules();
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  function openSchedForm() {
    setSchedTriggerMode("interval");
    setSchedListenId("");
    setSchedFeishuNotify(false);
    setShowSchedForm(true);
  }

  function closeSchedForm() {
    setShowSchedForm(false);
  }

  async function onReplan(seed: string) {
    if (!selected) return;
    const next = window.prompt("可修改任务描述后重新生成计划", seed);
    if (next === null) return;
    setBusy(true);
    setError("");
    try {
      await replanTask(selected.id, { prompt: next });
      await refresh(selected.id);
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onDeleteSelected() {
    if (!selected) return;
    if (!window.confirm("确定删除这条任务？删除后无法恢复。")) return;
    setBusy(true);
    setError("");
    try {
      await deleteTask(selected.id);
      await refresh(null);
      setPanel("compose");
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  function openShelf() {
    setShelfDraftExpertId(expertId);
    setShelfDraftSkillId(skillId);
    setShelfQuery("");
    setShowShelf(true);
  }

  function closeShelf() {
    setShowShelf(false);
    setShelfQuery("");
  }

  function clearShelfSelection() {
    setExpertId("");
    setSkillId("");
    setShelfLocked(false);
    setShelfDraftExpertId("");
    setShelfDraftSkillId("");
  }

  function applyShelfChoice(nextSkillId: string, nextExpertId: string = "") {
    const matchedScene = scenes.find((s) => s.skill_id === nextSkillId);
    if (matchedScene) {
      void applyScene(matchedScene);
      if (nextExpertId) setExpertId(nextExpertId);
    } else {
      const skill = skills.find((s) => s.id === nextSkillId);
      setSkillId(nextSkillId);
      setExpertId(nextExpertId);
      setActiveSceneId("");
      setNeedsTableUpload(nextSkillId === "table_analysis");
      setShelfLocked(true);
      if (nextSkillId !== "table_analysis") clearTableSelection();
      if (!prompt.trim() && skill) {
        setPrompt(`请按「${skill.name}」帮我完成：……`);
      }
    }
    closeShelf();
  }

  function confirmShelf() {
    if (shelfTab === "experts") {
      if (!shelfDraftExpertId) return;
      const ex = experts.find((x) => x.id === shelfDraftExpertId);
      const nextSkill = shelfDraftSkillId || ex?.default_skill_id || "";
      if (!nextSkill) {
        setExpertId(shelfDraftExpertId);
        closeShelf();
        return;
      }
      applyShelfChoice(nextSkill, shelfDraftExpertId);
      return;
    }
    if (!shelfDraftSkillId) return;
    applyShelfChoice(shelfDraftSkillId, "");
  }

  function pickExpertDraft(id: string) {
    setShelfDraftExpertId(id);
    const ex = experts.find((x) => x.id === id);
    if (ex?.default_skill_id) setShelfDraftSkillId(ex.default_skill_id);
  }

  function pickSkillDraft(id: string) {
    setShelfDraftSkillId(id);
    setShelfDraftExpertId("");
  }

  useEffect(() => {
    if (!showShelf) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeShelf();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [showShelf]);

  const shelfQ = shelfQuery.trim().toLowerCase();
  const matchShelf = (parts: Array<string | undefined>) => {
    if (!shelfQ) return true;
    return parts.some((p) => (p || "").toLowerCase().includes(shelfQ));
  };
  const filteredExperts = experts.filter((e) =>
    matchShelf([e.name, e.description, e.strength, e.best_for, e.output_shape])
  );
  const filteredSkills = skills.filter((s) =>
    matchShelf([s.name, s.description, s.strength, s.best_for, s.output_shape])
  );
  const shelfCanConfirm =
    shelfTab === "experts" ? Boolean(shelfDraftExpertId) : Boolean(shelfDraftSkillId);
  const shelfDraftLabel =
    shelfTab === "experts"
      ? experts.find((e) => e.id === shelfDraftExpertId)?.name
      : skills.find((s) => s.id === shelfDraftSkillId)?.name;
  const sceneCategories = SCENE_CATEGORY_ORDER.filter((id) =>
    scenes.some((s) => (s.category || "writing") === id)
  );
  const openSceneCategory = hoverSceneCategory || pinnedSceneCategory;
  const openCategoryScenes = openSceneCategory
    ? scenes.filter((s) => (s.category || "writing") === openSceneCategory)
    : [];

  function updateSceneScroll() {
    const el = sceneChildrenRef.current;
    if (!el) {
      setSceneScroll({ canUp: false, canDown: false, moreCount: 0 });
      return;
    }
    const { scrollTop, scrollHeight, clientHeight } = el;
    const eps = 2;
    const canUp = scrollTop > eps;
    const canDown = scrollTop + clientHeight < scrollHeight - eps;
    let moreCount = 0;
    if (canDown) {
      const box = el.getBoundingClientRect();
      el.querySelectorAll<HTMLElement>(".scene-child").forEach((child) => {
        const r = child.getBoundingClientRect();
        if (r.top + r.height * 0.35 > box.bottom) moreCount += 1;
      });
    }
    setSceneScroll({ canUp, canDown, moreCount });
  }

  function scrollScenePage(dir: 1 | -1) {
    const el = sceneChildrenRef.current;
    if (!el) return;
    const step = Math.max(el.clientHeight * 0.85, 72);
    el.scrollBy({ top: dir * step, behavior: "smooth" });
  }

  useEffect(() => {
    const el = sceneChildrenRef.current;
    if (el) el.scrollTop = 0;
    const measure = () => updateSceneScroll();
    const raf = requestAnimationFrame(measure);
    window.addEventListener("resize", measure);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", measure);
    };
  }, [openSceneCategory, openCategoryScenes.length]);

  const unreadFailNotices = unreadFailures(scheduleNotices, ackedRunIds);
  const unreadFailCount = unreadFailNotices.length;

  const panelTitle: Record<Panel, string> = {
    compose: "新建任务",
    task: selected?.title || "当前任务",
    workspace: "资料库",
    schedules: "自动化",
  };

  const intervalPresets: { label: string; minutes: number }[] = [
    { label: "每小时", minutes: 60 },
    { label: "每天", minutes: 1440 },
    { label: "每周", minutes: 10080 },
  ];

  function formatInterval(minutes: number): string {
    if (minutes === 60) return "每小时";
    if (minutes === 1440) return "每天";
    if (minutes === 10080) return "每周";
    if (minutes % 1440 === 0) return `每 ${minutes / 1440} 天`;
    if (minutes % 60 === 0) return `每 ${minutes / 60} 小时`;
    return `每 ${minutes} 分钟`;
  }

  function formatTriggerMode(s: Schedule): string {
    if (s.trigger_mode === "on_task_succeeded") {
      const src = schedules.find((x) => x.id === s.listen_schedule_id);
      const label = src?.name || "某条自动化";
      return `「${label}」成功后`;
    }
    return formatInterval(s.interval_minutes);
  }

  function formatRunTrigger(trigger?: string | null): string {
    if (trigger === "task_done") return "任务成功后";
    if (trigger === "interval") return "到点";
    if (trigger === "manual") return "立即跑";
    if (trigger === "webhook") return "Webhook";
    return trigger || "—";
  }

  function toggleScheduleHook(scheduleId: string) {
    if (expandedHookScheduleId === scheduleId) {
      setExpandedHookScheduleId(null);
      setHookReveal(null);
      setHookCopyTip("");
      return;
    }
    setExpandedHookScheduleId(scheduleId);
    setHookReveal(null);
    setHookCopyTip("");
  }

  async function copyHookText(label: string, value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setHookCopyTip(`已复制${label}`);
      window.setTimeout(() => setHookCopyTip(""), 2000);
    } catch {
      setHookCopyTip("复制失败，请手动全选");
      window.setTimeout(() => setHookCopyTip(""), 2500);
    }
  }

  async function onRotateHookToken(scheduleId: string) {
    setBusy(true);
    setError("");
    setHookCopyTip("");
    try {
      const rotated = await rotateHookToken(scheduleId);
      setHookReveal(rotated);
      setExpandedHookScheduleId(scheduleId);
      await refreshSchedules();
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  const visibleWorkspaceEntries = wsEntries
    .filter((e) => {
      if (e.is_dir) return true;
      if (wsFilter === "tables" && !isTableFileName(e.name)) return false;
      const q = wsSearch.trim().toLowerCase();
      if (q && !e.name.toLowerCase().includes(q)) return false;
      return true;
    })
    .sort(compareWorkspaceEntries);

  const schedFormCard = (
    <div className="panel-card mx-auto max-w-xl space-y-4 p-5">
      <p className="text-sm text-[var(--muted)]">
        选好触发方式：到点重复，或等另一条自动化成功后再跑本条。
      </p>
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="text-sm text-[var(--muted)] sm:col-span-2">
          名称
          <input className="field" value={schedName} onChange={(e) => setSchedName(e.target.value)} />
        </label>
        <label className="text-sm text-[var(--muted)] sm:col-span-2">
          自动执行内容
          <textarea
            className="field"
            rows={3}
            placeholder="例如：生成本周行业速览，并整理成可转发草稿……"
            value={schedPrompt}
            onChange={(e) => setSchedPrompt(e.target.value)}
          />
        </label>
        <div className="text-sm text-[var(--muted)] sm:col-span-2">
          <span>触发方式</span>
          <div className="mt-2 flex flex-wrap gap-2">
            <button
              type="button"
              className={`btn-ghost !px-3 !py-1.5 text-xs ${
                schedTriggerMode === "interval" ? "!border-[var(--accent)] !text-[var(--accent)]" : ""
              }`}
              onClick={() => setSchedTriggerMode("interval")}
            >
              到点重复
            </button>
            <button
              type="button"
              className={`btn-ghost !px-3 !py-1.5 text-xs ${
                schedTriggerMode === "on_task_succeeded"
                  ? "!border-[var(--accent)] !text-[var(--accent)]"
                  : ""
              }`}
              onClick={() => setSchedTriggerMode("on_task_succeeded")}
            >
              某条成功后再跑
            </button>
          </div>
          <p className="mt-2 text-xs text-[var(--faint)]">
            {schedTriggerMode === "interval"
              ? "按设定间隔自动开跑（与以前一样）。"
              : "当选中的那条自动化跑成功后，自动再跑本条。不会连环触发（只跟一层）。"}
          </p>
        </div>
        {schedTriggerMode === "interval" ? (
          <div className="text-sm text-[var(--muted)] sm:col-span-2">
            <span>多久跑一次</span>
            <div className="mt-2 flex flex-wrap gap-2">
              {intervalPresets.map((p) => (
                <button
                  key={p.minutes}
                  type="button"
                  className={`btn-ghost !px-3 !py-1.5 text-xs ${
                    schedInterval === p.minutes ? "!border-[var(--accent)] !text-[var(--accent)]" : ""
                  }`}
                  onClick={() => setSchedInterval(p.minutes)}
                >
                  {p.label}
                </button>
              ))}
            </div>
            <label className="mt-3 block">
              自定义（分钟）
              <input
                type="number"
                min={1}
                className="field"
                value={schedInterval}
                onChange={(e) => setSchedInterval(Number(e.target.value))}
              />
            </label>
          </div>
        ) : (
          <label className="text-sm text-[var(--muted)] sm:col-span-2">
            监听哪条自动化（成功后触发本条）
            <select
              className="field"
              value={schedListenId}
              onChange={(e) => setSchedListenId(e.target.value)}
            >
              <option value="">请选择…</option>
              {schedules.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
            {schedules.length === 0 ? (
              <span className="mt-1 block text-xs text-[var(--faint)]">
                还没有可监听的自动化，请先建一条「到点重复」的上游。
              </span>
            ) : null}
          </label>
        )}
        <label className="text-sm text-[var(--muted)]">
          技能（可选）
          <select className="field" value={schedSkillId} onChange={(e) => setSchedSkillId(e.target.value)}>
            <option value="">通用调研</option>
            {skills.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm text-[var(--muted)]">
          专家（可选）
          <select className="field" value={schedExpertId} onChange={(e) => setSchedExpertId(e.target.value)}>
            <option value="">不选专家</option>
            {experts.map((e) => (
              <option key={e.id} value={e.id}>
                {e.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-start gap-2 text-sm text-[var(--muted)]">
          <input
            type="checkbox"
            className="mt-1"
            checked={schedFeishuNotify}
            onChange={(e) => setSchedFeishuNotify(e.target.checked)}
          />
          <span>
            这条也发飞书群
            <span className="mt-0.5 block text-xs text-[var(--faint)]">
              跟上方设置走；可先模拟
            </span>
          </span>
        </label>
      </div>
      <div className="flex flex-wrap gap-2 pt-1">
        <button
          className="btn-primary"
          disabled={
            busy ||
            !schedPrompt.trim() ||
            (schedTriggerMode === "on_task_succeeded" && !schedListenId)
          }
          onClick={onCreateSchedule}
        >
          创建自动化
        </button>
        <button className="btn-ghost" type="button" disabled={busy} onClick={closeSchedForm}>
          取消
        </button>
      </div>
    </div>
  );

  return (
    <div className="desk">
      <nav className="icon-rail" aria-label="主导航">
        <div className="icon-rail-top">
          <button
            type="button"
            className={`icon-rail-btn ${panel === "compose" ? "icon-rail-btn-active" : ""}`}
            data-tip="首页"
            aria-label="首页"
            aria-current={panel === "compose" ? "page" : undefined}
            onClick={startNewCompose}
          >
            {iconRailHome}
          </button>
          <button
            type="button"
            className={`icon-rail-btn ${panel === "task" ? "icon-rail-btn-active" : ""}`}
            data-tip="当前任务"
            aria-label="当前任务"
            aria-current={panel === "task" ? "page" : undefined}
            onClick={goToTaskPanel}
          >
            {iconRailClock}
          </button>
          <button
            type="button"
            className={`icon-rail-btn ${panel === "workspace" ? "icon-rail-btn-active" : ""}`}
            data-tip="资料库"
            aria-label="资料库"
            aria-current={panel === "workspace" ? "page" : undefined}
            onClick={() => setPanel("workspace")}
          >
            {iconRailLibrary}
          </button>
          <button
            type="button"
            className={`icon-rail-btn ${panel === "schedules" ? "icon-rail-btn-active" : ""}`}
            data-tip={unreadFailCount > 0 ? `自动化（${unreadFailCount} 条失败未读）` : "自动化"}
            aria-label={unreadFailCount > 0 ? `自动化，${unreadFailCount} 条失败未读` : "自动化"}
            aria-current={panel === "schedules" ? "page" : undefined}
            onClick={() => {
              setPanel("schedules");
              refreshScheduleNotices().catch(() => undefined);
            }}
          >
            {iconRailAutomate}
            {unreadFailCount > 0 ? (
              <span className="icon-rail-badge" aria-hidden>
                {unreadFailCount > 9 ? "9+" : unreadFailCount}
              </span>
            ) : null}
          </button>
          <button
            type="button"
            className="icon-rail-btn icon-rail-btn-muted"
            data-tip="更多"
            aria-label="更多"
            disabled
          >
            {iconRailMore}
          </button>
        </div>
      </nav>

      {taskRailOpen ? (
        <aside className="app-sidebar task-rail flex w-[15.5rem] shrink-0 flex-col border-r soft-divider lg:w-64">
          <div className="flex items-center justify-between gap-2 px-3 pb-2 pt-3">
            <span className="section-label">任务</span>
            <button
              className="btn-text !text-xs"
              type="button"
              onClick={() => {
                setManageMode((v) => !v);
                setMergeIds([]);
              }}
            >
              {manageMode ? "完成" : "管理"}
            </button>
          </div>
          <div className="px-3 pb-2">
            <input
              className="field !mt-0 !py-1.5 text-xs"
              placeholder="搜索任务标题或内容…"
              value={taskQueryDraft}
              onChange={(e) => setTaskQueryDraft(e.target.value)}
              aria-label="搜索任务"
            />
            {taskQuery ? (
              <p className="mt-1 text-[10px] text-[var(--faint)]">
                含匹配的已归档 ·{" "}
                <button type="button" className="btn-text !text-[10px]" onClick={() => setTaskQueryDraft("")}>
                  清除
                </button>
              </p>
            ) : null}
          </div>
          {manageMode ? (
            <div className="flex items-center justify-between gap-2 px-3 pb-2">
              <span className="text-[11px] text-[var(--faint)]">勾选 ≥2 条后合并</span>
              <button
                className="btn-text !text-xs"
                type="button"
                disabled={busy || mergeIds.length < 2}
                onClick={() => onMergeTasks()}
              >
                合并{mergeIds.length >= 2 ? ` (${mergeIds.length})` : ""}
              </button>
            </div>
          ) : null}
          <div className="min-h-0 flex-1 space-y-0.5 overflow-y-auto px-2 pb-3">
            {(() => {
              const searching = Boolean(taskQuery.trim());
              // Search: show every hit flat (including merged children). Nesting under a
              // non-matching parent would hide real hits or surface unrelated primaries.
              const topTasks = searching
                ? tasks
                : tasks.filter((t) => t.status !== "merged");
              const childrenOf = (parentId: string) =>
                searching
                  ? []
                  : tasks.filter((t) => t.status === "merged" && t.merged_into_id === parentId);
              if (topTasks.length === 0) {
                return (
                  <p className="px-2 text-xs leading-relaxed text-[var(--faint)]">
                    {taskQuery ? "没有匹配的任务" : "还没有任务"}
                  </p>
                );
              }
              return topTasks.map((t) => {
                const kids = childrenOf(t.id);
                const hasBundle = !searching && (kids.length > 0 || (t.merged_from_ids || []).length > 0);
                const expanded = expandedMergeIds.includes(t.id);
                const canPick = manageMode;
                const label = taskRailLabel(t, taskQuery);
                const fullPrompt = searchablePrompt(t.user_prompt || "");
                const tip = fullPrompt ? `${label}\n${fullPrompt.slice(0, 120)}` : label;
                return (
                  <div key={t.id} className="space-y-0.5">
                    <div
                      className={`task-row flex w-full items-center gap-1.5 ${
                        panel === "task" && selected?.id === t.id ? "task-row-active" : ""
                      }`}
                    >
                      {canPick ? (
                        <input
                          type="checkbox"
                          className="shrink-0"
                          checked={mergeIds.includes(t.id)}
                          onChange={() => toggleMergeId(t.id)}
                          aria-label={`选择 ${label}`}
                        />
                      ) : null}
                      {hasBundle ? (
                        <button
                          type="button"
                          className="shrink-0 px-0.5 text-[10px] text-[var(--faint)]"
                          aria-label={expanded ? "收起已并入" : "展开已并入"}
                          onClick={() => toggleExpandMerge(t.id)}
                        >
                          {expanded ? "▾" : "▸"}
                        </button>
                      ) : (
                        <span className="inline-block w-3 shrink-0" />
                      )}
                      <button
                        type="button"
                        className="flex min-w-0 flex-1 items-center gap-2 text-left"
                        onClick={() => {
                          if (hasBundle && !expanded) toggleExpandMerge(t.id);
                          selectTask(t.id);
                        }}
                        title={tip}
                      >
                        <span className={`status-dot ${statusTone(t.status)}`} />
                        <span className="min-w-0 flex-1 truncate text-sm">
                          {label}
                        </span>
                        {t.status === "archived" ? (
                          <span className="shrink-0 text-[10px] text-[var(--faint)]">归档</span>
                        ) : t.status === "merged" && searching ? (
                          <span className="shrink-0 text-[10px] text-[var(--faint)]">已并入</span>
                        ) : hasBundle ? (
                          <span className="shrink-0 text-[10px] text-[var(--faint)]">
                            {kids.length || (t.merged_from_ids || []).length}
                          </span>
                        ) : null}
                      </button>
                    </div>
                    {expanded && kids.length > 0
                      ? kids.map((child) => {
                          const childLabel = taskRailLabel(child, taskQuery);
                          return (
                          <button
                            key={child.id}
                            type="button"
                            className={`task-row ml-4 flex w-[calc(100%-1rem)] items-center gap-2 ${
                              panel === "task" && selected?.id === child.id ? "task-row-active" : ""
                            }`}
                            onClick={() => selectTask(child.id)}
                            title={childLabel}
                          >
                            <span className={`status-dot ${statusTone(child.status)}`} />
                            <span className="min-w-0 flex-1 truncate text-xs text-[var(--muted)]">
                              {childLabel}
                            </span>
                          </button>
                          );
                        })
                      : null}
                  </div>
                );
              });
            })()}
          </div>
        </aside>
      ) : null}

      <div className="app-frame flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="app-topbar shrink-0 border-b soft-divider">
          <div className="flex items-center gap-2.5 px-3 py-2.5 lg:px-4">
            <button
              type="button"
              className="rail-toggle"
              title={taskRailOpen ? "收起侧边栏" : "展开侧边栏"}
              aria-label={taskRailOpen ? "收起侧边栏" : "展开侧边栏"}
              aria-pressed={taskRailOpen}
              onClick={() => toggleTaskRail()}
            >
              {sidebarToggleIcon}
            </button>
            <div className="min-w-0">
              <p className="font-display truncate text-[15px] font-semibold tracking-tight text-[var(--ink)] leading-tight">
                AI办公搭子
              </p>
              <p className="hidden text-[11px] leading-tight text-[var(--muted)] sm:block">本机调研工作台</p>
            </div>
            {!taskRailOpen ? (
              <button
                type="button"
                className="new-chat-btn new-chat-btn-compact ml-1"
                onClick={startNewCompose}
                title="新建"
              >
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                  <path
                    d="M8 3.2v9.6M3.2 8h9.6"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                  />
                </svg>
                新建
              </button>
            ) : null}
            <div className="min-w-0 flex-1" />
            <p className="hidden text-[11px] leading-relaxed text-[var(--faint)] sm:block sm:max-w-md sm:truncate sm:text-right">
              {runtime
                ? [
                    runtime.llm_mock || !runtime.llm_configured ? "模型：模拟/未配置" : `模型：${runtime.llm_model || "已接通"}`,
                    runtime.search_mock
                      ? "检索：模拟"
                      : runtime.search_configured
                        ? "检索：真实"
                        : "检索：未配 Key（研类会报错）",
                  ].join(" · ")
                : "内容会发给已配置的云端模型推理；本产品不用于训练。"}
            </p>
          </div>
        </header>

        <main className="content-area flex min-h-0 min-w-0 flex-1 flex-col">
        {panel !== "compose" ? (
        <header className="flex items-end justify-between gap-4 px-6 py-5 lg:px-10">
          <div>
            <div className="flex items-center gap-3">
              <BackHomeArrow
                onClick={handleHeaderBack}
                label={panel === "task" && taskBackTo === "schedules" ? "返回自动化" : panel === "task" && taskBackTo ? "返回" : "返回首页"}
              />
              <h1 className="font-display text-2xl font-semibold tracking-tight text-[var(--ink)]">
                {panelTitle[panel]}
              </h1>
            </div>
            {panel === "workspace" ? (
              <p className="mt-1 text-sm text-[var(--muted)]">上传或选用表格。</p>
            ) : null}
            {panel === "schedules" && !showSchedForm ? (
              <p className="mt-1 text-sm text-[var(--muted)]">让自动化按时跑；跑完后把结果发到飞书群提醒你（现在可先模拟）。</p>
            ) : null}
          </div>
          {panel === "schedules" && schedules.length > 0 && !showSchedForm ? (
            <button className="btn-primary shrink-0" type="button" onClick={openSchedForm}>
              + 添加自动化
            </button>
          ) : null}
        </header>
        ) : null}

        <div className={`flex min-h-0 flex-1 flex-col ${panel === "compose" ? "px-4 pb-4 lg:px-6 lg:pb-5" : "px-6 pb-6 lg:px-10 lg:pb-8"}`}>
          {error ? (
            <div className="alert-error mb-4 rounded-md px-4 py-3 text-sm">
              {error}
              {error.includes("COST_CONFIRM_REQUIRED") && selected ? (
                <button className="ml-3 underline" onClick={() => onConfirm(true)}>
                  确认费用并继续
                </button>
              ) : null}
            </div>
          ) : null}

          {panel === "compose" ? (
            <div className="compose-stage">
              <div className="compose-stage-center">
                <h1 className="compose-welcome font-display">今天想办哪件差事？</h1>
                <p className="compose-welcome-sub">选场景或直接说需求；左侧可进任务、资料库与自动化。</p>
                <div
                  className="scene-picker"
                  onMouseLeave={() => setHoverSceneCategory("")}
                >
                  <div className="scene-cats" role="tablist" aria-label="场景大类">
                    {sceneCategories.map((cat) => {
                      const active = openSceneCategory === cat;
                      return (
                        <button
                          key={cat}
                          type="button"
                          role="tab"
                          aria-selected={active}
                          className={active ? "scene-cat scene-cat-active" : "scene-cat"}
                          onMouseEnter={() => setHoverSceneCategory(cat)}
                          onFocus={() => setHoverSceneCategory(cat)}
                          onClick={() =>
                            setPinnedSceneCategory((prev) => (prev === cat ? "" : cat))
                          }
                        >
                          {SCENE_CATEGORY_LABEL[cat] || cat}
                        </button>
                      );
                    })}
                  </div>
                  {openCategoryScenes.length > 0 ? (
                    <div className="scene-children-wrap">
                      {sceneScroll.canUp ? (
                        <button
                          type="button"
                          className="scene-scroll-btn scene-scroll-up"
                          aria-label="向上查看更多场景"
                          onClick={() => scrollScenePage(-1)}
                        >
                          <span aria-hidden>⌃</span>
                        </button>
                      ) : null}
                      <div
                        ref={sceneChildrenRef}
                        className={
                          "scene-children" +
                          (sceneScroll.canUp ? " scene-children-has-prev" : "") +
                          (sceneScroll.canDown ? " scene-children-has-more" : "")
                        }
                        role="tabpanel"
                        onScroll={updateSceneScroll}
                      >
                        {openCategoryScenes.map((sc) => (
                          <button
                            key={sc.id}
                            type="button"
                            title={sc.blurb}
                            className={
                              activeSceneId === sc.id
                                ? "scene-child scene-child-active"
                                : "scene-child"
                            }
                            onClick={() => {
                              if (activeSceneId === sc.id) {
                                setDetectHint(null);
                                setActiveSceneId("");
                                setSkillId("");
                                setExpertId("");
                                setNeedsTableUpload(false);
                                setShelfLocked(false);
                                return;
                              }
                              void applyScene(sc);
                            }}
                          >
                            <span className="scene-child-name">{sc.name}</span>
                            <span className="scene-child-blurb">{sc.blurb}</span>
                          </button>
                        ))}
                      </div>
                      {sceneScroll.canDown ? (
                        <>
                          <div className="scene-children-fade" aria-hidden />
                          <button
                            type="button"
                            className="scene-scroll-btn scene-scroll-down"
                            aria-label="向下查看更多场景"
                            onClick={() => scrollScenePage(1)}
                          >
                            <span aria-hidden>⌄</span>
                          </button>
                          {sceneScroll.moreCount > 0 ? (
                            <p className="scene-more-hint">
                              还有 {sceneScroll.moreCount} 个 · 下滑或点箭头
                            </p>
                          ) : null}
                        </>
                      ) : null}
                    </div>
                  ) : (
                    <p className="scene-picker-hint">把鼠标移到「调研 / 写稿 / 数据」上看下级场景</p>
                  )}
                </div>

                {needsTableUpload || skillId === "table_analysis" ? (
                  <div className="compose-extra mx-auto mt-4 w-full max-w-2xl space-y-3 rounded-md border soft-divider p-3">
                    <div>
                      <p className="text-sm font-medium text-[var(--ink)]">表格（开始前准备）</p>
                      <p className="mt-1 text-xs text-[var(--muted)]">
                        上传挂到本任务，或从资料库选表；报告请在任务页下载。
                      </p>
                    </div>
                    <input
                      type="file"
                      accept=".csv,.xlsx"
                      className="block w-full text-xs text-[var(--ink)]"
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (!f) return;
                        setPendingTableFiles([f]);
                        setPendingWsTables([]);
                        e.target.value = "";
                      }}
                    />
                    {pendingTableFiles.length > 0 ? (
                      <ul className="space-y-1 text-xs text-[var(--muted)]">
                        {pendingTableFiles.map((f) => (
                          <li key={f.name}>待上传：{f.name}</li>
                        ))}
                      </ul>
                    ) : null}
                    {wsRoot ? (
                      <div className="space-y-2">
                        <p className="text-xs text-[var(--faint)]">从资料库选表</p>
                        <ul className="max-h-28 space-y-1 overflow-auto text-xs">
                          {wsEntries
                            .filter((e) => !e.is_dir && isTableFileName(e.name))
                            .map((e) => {
                              const on = pendingWsTables.includes(e.rel);
                              return (
                                <li key={e.rel}>
                                  <button
                                    type="button"
                                    className={
                                      on
                                        ? "text-[var(--accent)] underline"
                                        : "text-[var(--ink)] underline-offset-2 hover:underline"
                                    }
                                    onClick={() => {
                                      setPendingWsTables((prev) =>
                                        prev.includes(e.rel)
                                          ? prev.filter((x) => x !== e.rel)
                                          : [...prev, e.rel].slice(0, 3)
                                      );
                                      setPendingTableFiles([]);
                                    }}
                                  >
                                    {on ? "已选 · " : ""}
                                    {e.name}
                                  </button>
                                </li>
                              );
                            })}
                          {wsEntries.filter((e) => !e.is_dir && isTableFileName(e.name)).length === 0 ? (
                            <li className="text-[var(--faint)]">当前文件夹没有 csv/xlsx，可先去「资料库」上传。</li>
                          ) : null}
                        </ul>
                      </div>
                    ) : (
                      <p className="text-xs text-[var(--faint)]">
                        尚未设置资料库。可先上传本地文件，或到「资料库」设置文件夹后再选表。
                      </p>
                    )}
                    {pendingWsTables.length > 0 ? (
                      <p className="text-xs text-[var(--muted)]">已选资料库：{pendingWsTables.join("、")}</p>
                    ) : null}
                  </div>
                ) : null}

                {showMore ? (
                  <div className="mx-auto mt-3 w-full max-w-2xl space-y-2 rounded-md border soft-divider p-3">
                    <p className="text-xs text-[var(--muted)]">可选，每行一个公开网页，最多 3 个。</p>
                    <textarea
                      className="field"
                      rows={2}
                      placeholder={"https://example.com/a\nhttps://example.com/b"}
                      value={urls}
                      onChange={(e) => setUrls(e.target.value)}
                    />
                  </div>
                ) : null}
              </div>

              <div className="compose-bar-wrap">
                <div className="compose-bar">
                  <textarea
                    className="compose-bar-input"
                    rows={1}
                    placeholder="用一句话说清要办的差事…"
                    value={prompt}
                    onChange={(e) => {
                      setPrompt(e.target.value);
                      setActiveSceneId("");
                      setShelfLocked(false);
                    }}
                    onKeyDown={(e) => {
                      // Enter 提交；Shift+Enter 换行。IME 组字/选词确认的 Enter 不得触发创建Task。
                      if (e.key !== "Enter" || e.shiftKey) return;
                      if (e.nativeEvent.isComposing || e.keyCode === 229) return;
                      e.preventDefault();
                      if (!busy && prompt.trim()) onCreate();
                    }}
                  />
                  <div className="compose-bar-actions">
                    <button type="button" className="btn-text !text-xs" onClick={() => setShowMore((v) => !v)}>
                      {showMore ? "收起链接" : "上传链接"}
                    </button>
                    <button type="button" className="btn-text !text-xs" onClick={openShelf}>
                      能力货架
                    </button>
                    <button
                      type="button"
                      disabled={busy || !prompt.trim()}
                      onClick={onCreate}
                      className="compose-send"
                      aria-label="开始生成"
                    >
                      开始
                    </button>
                  </div>
                </div>
              </div>

              {showShelf && typeof document !== "undefined"
                ? createPortal(
                    <div className="shelf-overlay" role="dialog" aria-modal="true" aria-label="能力货架">
                      <button
                        type="button"
                        className="shelf-overlay-backdrop"
                        aria-label="关闭"
                        onClick={closeShelf}
                      />
                      <div className="shelf-overlay-panel">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <h2 className="font-display text-lg font-semibold text-[var(--ink)]">能力货架</h2>
                            <p className="mt-1 text-xs text-[var(--muted)]">
                              先点选专家或技能，再点「确定」带回新建页。
                            </p>
                          </div>
                          <button type="button" className="btn-ghost !py-1.5 text-xs" onClick={closeShelf}>
                            关闭
                          </button>
                        </div>
                        <div className="mt-4 flex flex-wrap items-center gap-2">
                          <button
                            type="button"
                            className={shelfTab === "experts" ? "scene-pill scene-pill-active" : "scene-pill"}
                            onClick={() => setShelfTab("experts")}
                          >
                            专家 · {filteredExperts.length === experts.length
                              ? `共 ${experts.length}`
                              : `筛选 ${filteredExperts.length}/${experts.length}`}
                          </button>
                          <button
                            type="button"
                            className={shelfTab === "skills" ? "scene-pill scene-pill-active" : "scene-pill"}
                            onClick={() => setShelfTab("skills")}
                          >
                            技能 · {filteredSkills.length === skills.length
                              ? `共 ${skills.length}`
                              : `筛选 ${filteredSkills.length}/${skills.length}`}
                          </button>
                          <input
                            className="field !mt-0 min-w-[12rem] flex-1 text-sm"
                            placeholder="搜索名称、擅长、适合场景…"
                            value={shelfQuery}
                            onChange={(e) => setShelfQuery(e.target.value)}
                          />
                        </div>
                        <div className="mt-4 grid max-h-[min(24rem,48vh)] gap-3 overflow-y-auto lg:grid-cols-2">
                          {experts.length + skills.length === 0 ? (
                            <p className="text-xs text-[var(--faint)] lg:col-span-2">
                              货架还没加载到内容，请稍后重试或刷新页面。
                            </p>
                          ) : shelfTab === "experts" ? (
                            filteredExperts.length === 0 ? (
                              <p className="text-xs text-[var(--faint)] lg:col-span-2">没有匹配的专家</p>
                            ) : (
                              filteredExperts.map((e) => (
                                <button
                                  key={e.id}
                                  type="button"
                                  className={`shelf-card ${
                                    shelfDraftExpertId === e.id ? "shelf-card-active" : ""
                                  }`}
                                  onClick={() => pickExpertDraft(e.id)}
                                >
                                  <span className="shelf-item-title">{e.name}</span>
                                  <span className="shelf-meta">擅长：{e.strength || e.description}</span>
                                  <span className="shelf-meta">适合：{e.best_for || "一般办公成稿"}</span>
                                  <span className="shelf-meta">成品：{e.output_shape || "书面草稿"}</span>
                                </button>
                              ))
                            )
                          ) : filteredSkills.length === 0 ? (
                            <p className="text-xs text-[var(--faint)] lg:col-span-2">没有匹配的技能</p>
                          ) : (
                            filteredSkills.map((s) => (
                              <button
                                key={s.id}
                                type="button"
                                className={`shelf-card ${
                                  shelfDraftSkillId === s.id ? "shelf-card-active" : ""
                                }`}
                                onClick={() => pickSkillDraft(s.id)}
                              >
                                <span className="shelf-item-title">{s.name}</span>
                                <span className="shelf-meta">擅长：{s.strength || s.description}</span>
                                <span className="shelf-meta">适合：{s.best_for || "一般办公成稿"}</span>
                                <span className="shelf-meta">成品：{s.output_shape || "书面草稿"}</span>
                              </button>
                            ))
                          )}
                        </div>
                        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t soft-divider pt-4">
                          <p className="text-xs text-[var(--muted)]">
                            {shelfDraftLabel ? `已选：${shelfDraftLabel}` : "尚未选择"}
                          </p>
                          <div className="flex flex-wrap gap-2">
                            <button
                              type="button"
                              className="btn-text !py-1.5 text-xs"
                              disabled={!expertId && !skillId && !shelfDraftExpertId && !shelfDraftSkillId}
                              onClick={clearShelfSelection}
                            >
                              清除选择
                            </button>
                            <button type="button" className="btn-ghost !py-1.5 text-xs" onClick={closeShelf}>
                              取消
                            </button>
                            <button
                              type="button"
                              className="btn-primary !py-1.5 text-xs"
                              disabled={!shelfCanConfirm}
                              onClick={confirmShelf}
                            >
                              确定
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>,
                    document.body
                  )
                : null}
            </div>
          ) : null}

          {panel === "task" ? (
            selected ? (
              <div className="task-detail-stage mx-auto w-full max-w-3xl space-y-6">
                {!(report || selected.has_report) ? (
                  <div className="flex flex-wrap items-center gap-2 text-sm text-[var(--muted)]">
                    <span className="inline-flex items-center gap-1.5">
                      <span className={`status-dot ${statusTone(selected.status)}`} />
                      {STATUS_LABEL[selected.status] || selected.status}
                    </span>
                  </div>
                ) : null}

                {selected.status === "plan_ready" ||
                selected.status === "running" ||
                selected.status === "paused" ||
                selected.status === "failed" ||
                selected.status === "archived" ||
                !(report || selected.has_report) ? (
                  <div className="flex flex-wrap items-center gap-2">
                    {selected.status === "plan_ready" ? (
                      <>
                        <button className="btn-primary" disabled={busy} onClick={() => onConfirm(false)}>
                          开始生成成品
                        </button>
                        <button className="btn-ghost" disabled={busy} onClick={() => onReplan(selected.user_prompt)}>
                          换个写法
                        </button>
                      </>
                    ) : null}
                    {selected.status === "running" ? (
                      <button
                        className="btn-ghost"
                        onClick={async () => {
                          await pauseTask(selected.id);
                          await refresh(selected.id);
                        }}
                      >
                        暂停
                      </button>
                    ) : null}
                    {selected.status === "paused" ? (
                      <>
                        <button
                          className="btn-primary"
                          onClick={async () => {
                            await resumeTask(selected.id);
                            await refresh(selected.id);
                          }}
                        >
                          继续生成
                        </button>
                        <button className="btn-ghost" disabled={busy} onClick={() => onReplan(selected.user_prompt)}>
                          换个写法
                        </button>
                      </>
                    ) : null}
                    {selected.status === "failed" ? (
                      <>
                        <button className="btn-primary" disabled={busy} onClick={() => onConfirm(true)}>
                          重新生成
                        </button>
                        <button className="btn-ghost" disabled={busy} onClick={() => onReplan(selected.user_prompt)}>
                          换个写法
                        </button>
                      </>
                    ) : null}
                    {selected.status === "archived" ? (
                      <button
                        className="btn-primary"
                        disabled={busy}
                        onClick={async () => {
                          setBusy(true);
                          setError("");
                          try {
                            await unarchiveTask(selected.id);
                            await refresh(selected.id);
                          } catch (e: any) {
                            setError(e.message || String(e));
                          } finally {
                            setBusy(false);
                          }
                        }}
                      >
                        恢复到列表
                      </button>
                    ) : null}
                    {!(report || selected.has_report) ? (
                      <button className="btn-danger ml-auto" type="button" disabled={busy} onClick={onDeleteSelected}>
                        删除
                      </button>
                    ) : null}
                  </div>
                ) : null}

                {selected.status === "running" || selected.status === "planning" ? (
                  <div className="panel-card space-y-2 p-5">
                    <p className="font-display text-lg font-semibold text-[var(--ink)]">正在生成成品…</p>
                    <p className="text-sm text-[var(--muted)]">
                      中间步骤已自动进行。完成后可在下方预览并导出（Word / Excel / Markdown / 飞书等）。
                    </p>
                  </div>
                ) : null}

                {selected.status === "plan_ready" && !report ? (
                  <div className="panel-card space-y-2 p-5">
                    <p className="font-display text-lg font-semibold text-[var(--ink)]">即将生成成品</p>
                    <p className="text-sm text-[var(--muted)]">
                      点「开始生成成品」即可；一般新建后会自动开始。超费用时会先请你确认。
                    </p>
                  </div>
                ) : null}

                {selected.error_message ? (
                  <div className="alert-error rounded-md px-4 py-3 text-sm">
                    {selected.error_code ? `${selected.error_code}: ` : ""}
                    {selected.error_message}
                  </div>
                ) : null}

                {selected.status === "plan_ready" ? (
                  <div className="space-y-4 text-sm">
                    {needsTableUpload || selected.skill_id === "table_analysis" ? (
                      <div className="panel-card space-y-3 p-4">
                        <div>
                          <p className="text-sm font-medium text-[var(--ink)]">补充表格（可选）</p>
                          <p className="mt-1 text-xs text-[var(--muted)]">
                            若新建时已选表可直接开始；也可在此再传 CSV/Excel。
                          </p>
                        </div>
                        <input
                          type="file"
                          accept=".csv,.xlsx"
                          className="block w-full text-xs text-[var(--ink)]"
                          onChange={(e) => onUpload(e.target.files?.[0] || null)}
                        />
                        {selected.uploads && selected.uploads.length > 0 ? (
                          <ul className="space-y-1 text-xs text-[var(--muted)]">
                            {selected.uploads.map((u) => (
                              <li key={u.id}>已上传：{u.filename}</li>
                            ))}
                          </ul>
                        ) : null}
                      </div>
                    ) : (
                      <label className="block text-[var(--muted)]">
                        可选：上传参考材料（≤20MB，最多 3 个）
                        <input
                          type="file"
                          accept=".txt,.md,.markdown,.pdf,.docx,.csv,.xlsx"
                          className="mt-2 block text-xs text-[var(--ink)]"
                          onChange={(e) => onUpload(e.target.files?.[0] || null)}
                        />
                      </label>
                    )}
                    {!(needsTableUpload || selected.skill_id === "table_analysis") &&
                    selected.uploads &&
                    selected.uploads.length > 0 ? (
                      <ul className="space-y-1 text-xs text-[var(--muted)]">
                        {selected.uploads.map((u) => (
                          <li key={u.id}>已添加：{u.filename}</li>
                        ))}
                      </ul>
                    ) : null}
                    {wsRoot ? (
                      <details className="text-xs text-[var(--muted)]">
                        <summary className="cursor-pointer select-none">从资料库添加</summary>
                        <ul className="mt-2 max-h-32 space-y-1 overflow-auto">
                          {wsEntries
                            .filter((e) => !e.is_dir)
                            .map((e) => (
                              <li key={e.rel}>
                                <button
                                  type="button"
                                  className="text-left text-[var(--accent)] underline-offset-2 hover:underline disabled:opacity-40"
                                  disabled={busy || (selected.uploads?.length || 0) >= 3}
                                  onClick={async () => {
                                    setBusy(true);
                                    setError("");
                                    try {
                                      await attachWorkspaceRefs(selected.id, [e.rel]);
                                      await refresh(selected.id);
                                    } catch (err: any) {
                                      setError(err.message || String(err));
                                    } finally {
                                      setBusy(false);
                                    }
                                  }}
                                >
                                  {e.name}
                                </button>
                              </li>
                            ))}
                        </ul>
                      </details>
                    ) : null}
                  </div>
                ) : null}

                {(selected.user_prompt ||
                  selected.plan ||
                  (selected.steps && selected.steps.length > 0)) &&
                selected.status !== "succeeded" ? (
                  <details className="text-sm text-[var(--muted)]">
                    <summary className="cursor-pointer select-none text-xs text-[var(--faint)]">
                      过程详情（可选，一般不用看）
                    </summary>
                    {selected.user_prompt ? (
                      <div className="mt-3">
                        <h3 className="section-label mb-2">你的需求</h3>
                        <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-[var(--ink)]">
                          {selected.user_prompt}
                        </p>
                      </div>
                    ) : null}
                    {selected.plan ? (
                      <div className="mt-3">
                        <h3 className="section-label mb-2">计划</h3>
                        <ol className="list-decimal space-y-1 pl-5 leading-relaxed">
                          {selected.plan.steps.map((s, i) => (
                            <li key={i}>
                              <span className="font-medium text-[var(--ink)]">{s.name}</span>
                              {s.goal ? <span> — {s.goal}</span> : null}
                            </li>
                          ))}
                        </ol>
                      </div>
                    ) : null}
                    {selected.steps?.length > 0 ? (
                      <div className="mt-3">
                        <h3 className="section-label mb-2">进度</h3>
                        <ul className="space-y-1.5">
                          {selected.steps.map((s) => (
                            <li key={s.seq} className="flex items-center gap-2.5">
                              <span className={`status-dot ${statusTone(s.status)}`} />
                              <span>
                                #{s.seq} {s.name}
                                <span className="ml-2 text-[11px]">{STATUS_LABEL[s.status] || s.status}</span>
                              </span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                  </details>
                ) : null}

                {!(report || selected.has_report) &&
                selected.status !== "running" &&
                selected.status !== "planning" &&
                selected.status !== "plan_ready" ? (
                  <p className="text-sm text-[var(--faint)]">成品生成后会出现在这里，可直接导出。</p>
                ) : null}

                {report || selected.has_report ? (
                  <div className="panel-card task-report-card space-y-4 p-5">
                    <div className="space-y-3">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <h3 className="section-label">成品报告</h3>
                            <span className="task-report-status">
                              <span className={`status-dot ${statusTone(selected.status)}`} />
                              {STATUS_LABEL[selected.status] || selected.status}
                            </span>
                          </div>
                          <p className="mt-1 text-[11px] text-[var(--faint)]">
                            预览为 Markdown；主按钮跟随下方所选格式。
                          </p>
                        </div>
                        <button
                          type="button"
                          className="btn-danger shrink-0 !py-1.5 text-xs"
                          disabled={busy}
                          onClick={onDeleteSelected}
                        >
                          删除
                        </button>
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        {(["md", "docx", "xlsx", "pptx"] as ExportKind[]).map((kind) => (
                          <button
                            key={kind}
                            type="button"
                            className={
                              activeExportKind === kind ? "scene-pill scene-pill-active" : "scene-pill"
                            }
                            onClick={() => setActiveExportKind(kind)}
                          >
                            {exportLabel(kind)}
                          </button>
                        ))}
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        <button
                          type="button"
                          className="btn-primary !py-1.5 text-xs"
                          disabled={
                            activeExportKind === "md"
                              ? !report
                              : !report && !selected.has_report
                          }
                          onClick={downloadActiveExport}
                        >
                          下载·{exportLabel(activeExportKind)}
                        </button>
                        <button
                          type="button"
                          className="btn-ghost !py-1.5 text-xs"
                          disabled={!report}
                          onClick={copyReportText}
                        >
                          复制正文
                        </button>
                        <span className="relative inline-flex items-center gap-1">
                          <button
                            type="button"
                            className="btn-ghost !py-1.5 text-xs"
                            disabled={busy || feishuOAuthBusy || !report || selected.status !== "succeeded"}
                            onClick={onExportFeishuClick}
                            title={
                              feishuOAuth?.connected
                                ? "导出到「我的」云文档"
                                : "未连接时可去连接，或先用应用空间导出"
                            }
                          >
                            {feishuOAuthBusy ? "连接中…" : "导出到飞书"}
                          </button>
                          {feishuOAuth?.connected ? (
                            <>
                              <button
                                type="button"
                                className="btn-text !text-xs"
                                disabled={busy || feishuOAuthBusy}
                                aria-expanded={feishuMoreOpen}
                                aria-haspopup="menu"
                                title="更多飞书选项"
                                onClick={() => setFeishuMoreOpen((v) => !v)}
                              >
                                已连接{feishuOAuth.user_name ? `·${feishuOAuth.user_name}` : ""} ▾
                              </button>
                              {feishuMoreOpen ? (
                                <div
                                  className="feishu-more-menu"
                                  role="menu"
                                  aria-label="飞书导出选项"
                                >
                                  <button
                                    type="button"
                                    role="menuitem"
                                    className="feishu-more-item"
                                    disabled={busy || !report || selected.status !== "succeeded"}
                                    onClick={() => void doExportFeishu(true)}
                                  >
                                    改用应用空间
                                  </button>
                                  <button
                                    type="button"
                                    role="menuitem"
                                    className="feishu-more-item"
                                    disabled={busy || feishuOAuthBusy}
                                    onClick={() => {
                                      setFeishuMoreOpen(false);
                                      void onDisconnectFeishu();
                                    }}
                                  >
                                    断开连接
                                  </button>
                                  {feishuOAuth.redirect_uri ? (
                                    <button
                                      type="button"
                                      role="menuitem"
                                      className="feishu-more-item"
                                      title="须与开放平台「安全设置→重定向 URL」完全一致"
                                      onClick={async () => {
                                        const u = feishuOAuth.redirect_uri;
                                        try {
                                          await navigator.clipboard.writeText(u);
                                          setFeishuCopyTip("已复制回调地址，去开放平台粘贴登记");
                                          window.setTimeout(() => setFeishuCopyTip(""), 2500);
                                          setFeishuMoreOpen(false);
                                        } catch {
                                          setError(`请手动复制回调地址：${u}`);
                                        }
                                      }}
                                    >
                                      复制回调地址
                                    </button>
                                  ) : null}
                                </div>
                              ) : null}
                            </>
                          ) : null}
                        </span>
                        <button
                          type="button"
                          className="btn-text !text-xs"
                          onClick={() => setShowMoreExports((v) => !v)}
                        >
                          {showMoreExports ? "收起更多" : "更多"}
                        </button>
                        {copyReportTip ? (
                          <span className="text-xs text-[var(--accent)]">{copyReportTip}</span>
                        ) : null}
                      </div>
                      {showMoreExports ? (
                        <div className="flex flex-wrap gap-2 border-t soft-divider pt-3">
                          <button
                            type="button"
                            className="btn-ghost !py-1.5 text-xs"
                            disabled={busy || !report || selected.status !== "succeeded"}
                            onClick={async () => {
                              const instruction = window.prompt(
                                "改写指令（例如：写得更短、加强竞品对比）",
                                "写得更短一些，突出结论"
                              );
                              if (!instruction || !instruction.trim()) return;
                              setBusy(true);
                              setError("");
                              try {
                                await rewriteReport(selected.id, instruction.trim());
                                await refresh(selected.id);
                              } catch (e: any) {
                                setError(e.message || String(e));
                              } finally {
                                setBusy(false);
                              }
                            }}
                          >
                            改写报告
                          </button>
                        </div>
                      ) : null}
                      {feishuExport ? (
                        <div className="panel-card space-y-2 p-3 text-sm">
                          <p className="font-medium text-[var(--ink)]">
                            {feishuExport.mock ? "已模拟导出到飞书" : "已导出到飞书"}
                            <span className="ml-2 text-xs font-normal text-[var(--muted)]">
                              身份：
                              {feishuExport.identity === "user" || feishuExport.space === "my"
                                ? "「我的」云文档"
                                : "应用空间"}
                            </span>
                          </p>
                          <p className="text-xs text-[var(--muted)]">标题：{feishuExport.title}</p>
                          <p className="text-xs leading-relaxed text-[var(--muted)]">
                            未登录时可先复制链接，到浏览器打开后再登录飞书查看。
                            {feishuExport.identity === "user" || feishuExport.space === "my"
                              ? " 本次写入「我的」云文档。"
                              : " 本次写入应用空间。"}
                            {!feishuOAuth?.connected ? (
                              <>
                                {" "}
                                想写到自己的文档？再点「导出到飞书」并选择「去连接」。
                              </>
                            ) : null}
                          </p>
                          <input
                            className="field w-full text-xs"
                            readOnly
                            value={feishuExport.url}
                            onFocus={(e) => e.currentTarget.select()}
                            aria-label="飞书文档链接"
                          />
                          <div className="flex flex-wrap gap-2">
                            <button className="btn-primary !py-1.5 text-xs" type="button" onClick={copyFeishuLink}>
                              复制链接
                            </button>
                            <a
                              className="btn-ghost !py-1.5 text-xs"
                              href={feishuExport.url}
                              target="_blank"
                              rel="noreferrer"
                            >
                              打开
                            </a>
                          </div>
                          {feishuCopyTip ? (
                            <p className="text-xs text-[var(--accent)]">{feishuCopyTip}</p>
                          ) : null}
                        </div>
                      ) : null}
                    </div>
                    {report ? (
                      <div className="task-report-body text-[14px] leading-relaxed text-[var(--ink)]">{linkifyReport(report)}</div>
                    ) : (
                      <p className="text-sm text-[var(--faint)]">报告加载中…</p>
                    )}
                  </div>
                ) : null}
              </div>
            ) : (
              <div className="mx-auto max-w-2xl py-16 text-center text-sm text-[var(--muted)]">
                还没有选中任务。从左侧任务列表点选，或先「新建」。
              </div>
            )
          ) : null}

          {panel === "workspace" ? (
            <div className="mx-auto w-full max-w-2xl space-y-8 pt-2">
              {wsRoot ? (
                <section className="space-y-2">
                  <p className="text-sm font-medium text-[var(--ink)]">上传表格</p>
                  <p className="text-xs text-[var(--muted)]">支持 csv / xlsx，上传后可「用此表分析」。</p>
                  <input
                    type="file"
                    accept=".csv,.xlsx"
                    className="block w-full text-sm text-[var(--ink)]"
                    disabled={busy}
                    onChange={(e) => {
                      void onWorkspaceUpload(e.target.files?.[0] || null);
                      e.target.value = "";
                    }}
                  />
                </section>
              ) : null}

              <section className="space-y-3">
                <p className="text-sm font-medium text-[var(--ink)]">文件列表</p>
                {wsRoot ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      className={wsFilter === "tables" ? "scene-pill scene-pill-active" : "scene-pill"}
                      onClick={() => setWsFilter("tables")}
                    >
                      仅表格
                    </button>
                    <button
                      type="button"
                      className={wsFilter === "all" ? "scene-pill scene-pill-active" : "scene-pill"}
                      onClick={() => setWsFilter("all")}
                    >
                      全部
                    </button>
                    <input
                      className="field !mt-0 max-w-xs flex-1 text-sm"
                      placeholder="搜索文件名"
                      value={wsSearch}
                      onChange={(e) => setWsSearch(e.target.value)}
                    />
                  </div>
                ) : null}
                {wsRoot && wsRel ? (
                  <button
                    type="button"
                    className="btn-text !text-xs"
                    onClick={() => {
                      const parent = wsRel.includes("/") ? wsRel.replace(/\/[^/]+$/, "") : "";
                      void refreshWorkspace(parent);
                      setWsPreview("");
                    }}
                  >
                    ← 返回上级
                  </button>
                ) : null}
                <ul className="max-h-72 space-y-1 overflow-auto text-sm">
                  {visibleWorkspaceEntries.map((e) => (
                    <li key={e.rel} className="flex flex-wrap items-center gap-2">
                      <button
                        className="task-row min-w-0 flex-1 text-[var(--ink)]"
                        onClick={async () => {
                          if (e.is_dir) {
                            await refreshWorkspace(e.rel);
                            setWsPreview("");
                          } else {
                            try {
                              if (/\.xlsx$/i.test(e.name)) {
                                setWsPreview("Excel 文件不在此预览正文；可点「用此表分析」。");
                                return;
                              }
                              const f = await readWorkspaceFile(e.rel);
                              setWsPreview(f.content.slice(0, 2000));
                            } catch (err: any) {
                              setError(err.message || String(err));
                            }
                          }
                        }}
                      >
                        <span className="text-[var(--faint)]">{e.is_dir ? "文件夹 · " : "文件 · "}</span>
                        {e.name}
                      </button>
                      {!e.is_dir && isTableFileName(e.name) ? (
                        <button
                          type="button"
                          className="btn-text shrink-0 !text-xs"
                          onClick={() => pickTableForAnalysis(e.rel)}
                        >
                          用此表分析
                        </button>
                      ) : null}
                    </li>
                  ))}
                  {visibleWorkspaceEntries.length === 0 ? (
                    <li className="text-xs text-[var(--faint)]">
                      {wsRoot
                        ? wsFilter === "tables"
                          ? "没有表格。可上传 csv/xlsx，或切到「全部」。"
                          : "没有匹配的材料。"
                        : "资料目录尚未配置。"}
                    </li>
                  ) : null}
                </ul>
                {wsPreview ? (
                  <pre className="max-h-40 overflow-auto whitespace-pre-wrap pt-1 text-xs leading-relaxed text-[var(--muted)]">
                    {wsPreview}
                  </pre>
                ) : null}
              </section>
            </div>
          ) : null}

          {panel === "schedules" ? (
            <div className="flex min-h-0 flex-1 flex-col">
              {unreadFailNotices.length > 0 && !showSchedForm ? (
                <div className="sched-notice-banner mb-4" role="status">
                  <div className="sched-notice-banner-head">
                    <span className="sched-notice-banner-title">
                      {unreadFailNotices.length} 条自动化失败未读
                    </span>
                    <button
                      type="button"
                      className="btn-text !text-xs"
                      onClick={() =>
                        markNoticesRead(unreadFailNotices.map((n) => n.run_id))
                      }
                    >
                      全部标为已读
                    </button>
                  </div>
                  <ul className="sched-notice-banner-list">
                    {unreadFailNotices.slice(0, 5).map((n) => (
                      <li key={n.run_id} className="sched-notice-banner-item">
                        <span className="sched-notice-banner-text" title={n.error || ""}>
                          {formatNoticeLine(n)}
                        </span>
                        {n.task_id ? (
                          <button
                            type="button"
                            className="text-xs text-[var(--accent)] underline-offset-2 hover:underline"
                            onClick={() => openNotice(n)}
                          >
                            打开任务
                          </button>
                        ) : (
                          <button
                            type="button"
                            className="btn-text !text-xs"
                            onClick={() => markNoticesRead([n.run_id])}
                          >
                            已读
                          </button>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {!showSchedForm ? (
                <div className="mb-4 rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4 space-y-3">
                  <p className="text-sm text-[var(--ink)]">
                    跑完后要不要把结果发到飞书群
                    <span className="ml-1 text-xs text-[var(--muted)]">（现在可先模拟，不进真群）</span>
                  </p>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs text-[var(--muted)]">何时发</span>
                    {(
                      [
                        ["off", "关闭"],
                        ["failed", "只失败发"],
                        ["always", "成功失败都发"],
                      ] as const
                    ).map(([value, label]) => (
                      <button
                        key={value}
                        type="button"
                        className={
                          (feishuNotify?.notify_on || "failed") === value
                            ? "btn-primary !px-2.5 !py-1 text-xs"
                            : "btn-ghost !px-2.5 !py-1 text-xs"
                        }
                        disabled={feishuNotifySaving || busy}
                        onClick={() => saveFeishuNotify({ notify_on: value })}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  <div className="flex flex-wrap items-end gap-2">
                    <label className="min-w-[16rem] flex-1 text-xs text-[var(--muted)]">
                      发给哪个群
                      <span className="mt-0.5 block text-xs text-[var(--faint)]">
                        模拟时可随便填；真发再填群 ID
                      </span>
                      <input
                        className="field mt-1"
                        value={feishuNotifyChatDraft}
                        placeholder="群 ID，例如 oc_xxxx"
                        onChange={(e) => setFeishuNotifyChatDraft(e.target.value)}
                      />
                    </label>
                    <button
                      type="button"
                      className="btn-ghost !px-3 !py-2 text-xs"
                      disabled={feishuNotifySaving || busy}
                      onClick={() => saveFeishuNotify({ chat_id: feishuNotifyChatDraft.trim() })}
                    >
                      {feishuNotifySaving ? "保存中…" : "保存群设置"}
                    </button>
                  </div>
                  <p
                    className={`text-xs ${feishuNotify?.recent?.[0] ? "text-[var(--muted)]" : "text-[var(--faint)]"}`}
                    title={feishuNotify?.recent?.[0]?.text_preview || feishuNotify?.recent?.[0]?.message || ""}
                  >
                    {formatFeishuLatestLine()}
                  </p>
                </div>
              ) : null}
              {showSchedForm ? (
                <div className="space-y-4">{schedFormCard}</div>
              ) : schedules.length === 0 ? (
                <div className="flex flex-1 flex-col items-center justify-center py-16 text-center">
                  <svg
                    className="mb-5 h-14 w-14 text-[var(--faint)]"
                    viewBox="0 0 48 48"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    aria-hidden
                  >
                    <circle cx="24" cy="24" r="16" />
                    <path d="M24 14v11l7 4" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  <p className="mb-6 text-sm text-[var(--muted)]">开启你的第一条自动化吧</p>
                  <button className="btn-primary" type="button" onClick={openSchedForm}>
                    + 添加自动化
                  </button>
                </div>
              ) : (
                <div className="mx-auto w-full max-w-5xl overflow-x-auto">
                  <table className="sched-table">
                    <thead>
                      <tr>
                        <th>名称</th>
                        <th>触发</th>
                        <th>上次跑</th>
                        <th>下次执行</th>
                        <th>最近一次</th>
                        <th>状态</th>
                        <th>操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {schedules.map((s) => (
                        <Fragment key={s.id}>
                          <tr>
                            <td className="max-w-[14rem]">
                              <div className="truncate font-medium" title={s.name}>
                                {s.name}
                              </div>
                              <div className="mt-0.5 truncate text-xs text-[var(--faint)]" title={s.prompt}>
                                {s.prompt}
                              </div>
                            </td>
                            <td className="whitespace-nowrap text-[var(--muted)]" title={formatTriggerMode(s)}>
                              {formatTriggerMode(s)}
                            </td>
                            <td className="whitespace-nowrap text-[var(--muted)]">
                              {formatNextRun(s.last_run_at)}
                            </td>
                            <td className="whitespace-nowrap text-[var(--muted)]">
                              {s.trigger_mode === "on_task_succeeded" ? "—" : formatNextRun(s.next_run_at)}
                            </td>
                            <td className="max-w-[16rem]">
                              {s.last_task_id ? (
                                <button
                                  className="text-xs text-[var(--accent)] underline-offset-2 hover:underline"
                                  onClick={() => selectTask(s.last_task_id || "", { backTo: "schedules" })}
                                >
                                  最近一次
                                </button>
                              ) : (
                                <span className="text-xs text-[var(--faint)]">—</span>
                              )}
                              {s.last_error ? (
                                <div
                                  className="sched-last-error mt-1 text-xs leading-snug text-[var(--danger)]"
                                  title={s.last_error}
                                >
                                  {s.last_error}
                                </div>
                              ) : null}
                            </td>
                            <td className="whitespace-nowrap">
                              <span className={s.enabled ? "text-[var(--accent)]" : "text-[var(--faint)]"}>
                                {s.enabled ? "启用" : "停用"}
                              </span>
                            </td>
                            <td>
                              <div className="flex flex-wrap gap-1.5">
                                <button
                                  className="btn-ghost !px-2 !py-1 text-xs"
                                  disabled={busy}
                                  onClick={async () => {
                                    setBusy(true);
                                    setError("");
                                    try {
                                      const row = await runScheduleNow(s.id);
                                      await refreshSchedules();
                                      if (expandedRunScheduleId === s.id) await refreshExpandedRuns();
                                      await refreshScheduleNotices();
                                      await refreshFeishuNotify();
                                      const notices = await listScheduleNotices({ limit: 5 });
                                      const mine = notices.find((n) => n.schedule_id === s.id);
                                      if (mine) showSchedToast(mine);
                                      if (row.last_task_id) await selectTask(row.last_task_id, { backTo: "schedules" });
                                    } catch (e: any) {
                                      setError(e.message || String(e));
                                      await refreshSchedules();
                                      if (expandedRunScheduleId === s.id) await refreshExpandedRuns();
                                      await refreshScheduleNotices();
                                      await refreshFeishuNotify();
                                      try {
                                        const notices = await listScheduleNotices({
                                          limit: 5,
                                          status: "failed",
                                        });
                                        const mine = notices.find((n) => n.schedule_id === s.id);
                                        if (mine) showSchedToast(mine);
                                      } catch {
                                        /* ignore */
                                      }
                                    } finally {
                                      setBusy(false);
                                    }
                                  }}
                                >
                                  立即跑
                                </button>
                                <button
                                  className="btn-ghost !px-2 !py-1 text-xs"
                                  disabled={busy || runsLoading}
                                  onClick={() => toggleScheduleRuns(s.id)}
                                >
                                  {expandedRunScheduleId === s.id ? "收起历史" : "跑次历史"}
                                </button>
                                <button
                                  className="btn-ghost !px-2 !py-1 text-xs"
                                  disabled={busy}
                                  onClick={() => toggleScheduleHook(s.id)}
                                >
                                  {expandedHookScheduleId === s.id ? "收起 Webhook" : "Webhook"}
                                </button>
                                <button
                                  className="btn-ghost !px-2 !py-1 text-xs"
                                  disabled={busy}
                                  title={
                                    s.feishu_notify
                                      ? "开：这条跑完按上方设置发飞书"
                                      : "关：这条跑完不发飞书"
                                  }
                                  onClick={async () => {
                                    setBusy(true);
                                    setError("");
                                    try {
                                      await patchSchedule(s.id, {
                                        feishu_notify: !s.feishu_notify,
                                      });
                                      await refreshSchedules();
                                    } catch (e: any) {
                                      setError(e.message || String(e));
                                    } finally {
                                      setBusy(false);
                                    }
                                  }}
                                >
                                  {s.feishu_notify ? "飞书·开" : "飞书·关"}
                                </button>
                                <button
                                  className="btn-ghost !px-2 !py-1 text-xs"
                                  disabled={busy}
                                  onClick={async () => {
                                    await patchSchedule(s.id, { enabled: !s.enabled });
                                    await refreshSchedules();
                                  }}
                                >
                                  {s.enabled ? "停用" : "启用"}
                                </button>
                                <button
                                  className="btn-danger !px-2 !py-1 text-xs"
                                  disabled={busy}
                                  onClick={async () => {
                                    setBusy(true);
                                    setError("");
                                    try {
                                      await deleteSchedule(s.id);
                                      if (expandedRunScheduleId === s.id) {
                                        setExpandedRunScheduleId(null);
                                        setScheduleRuns([]);
                                      }
                                      if (expandedHookScheduleId === s.id) {
                                        setExpandedHookScheduleId(null);
                                        setHookReveal(null);
                                      }
                                      await refreshSchedules();
                                    } catch (e: any) {
                                      setError(e.message || String(e));
                                    } finally {
                                      setBusy(false);
                                    }
                                  }}
                                >
                                  删除
                                </button>
                              </div>
                            </td>
                          </tr>
                          {expandedRunScheduleId === s.id ? (
                            <tr className="sched-runs-row">
                              <td colSpan={7}>
                                <div className="sched-runs-panel">
                                  <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--faint)]">
                                    最近跑次{runsLoading ? "（加载中…）" : `（${scheduleRuns.length}）`}
                                  </div>
                                  {!runsLoading && scheduleRuns.length === 0 ? (
                                    <p className="text-xs text-[var(--muted)]">还没有跑次记录</p>
                                  ) : null}
                                  {!runsLoading && scheduleRuns.length > 0 ? (
                                    <ul className="sched-runs-list">
                                      {scheduleRuns.map((run) => (
                                        <li key={run.id} className="sched-runs-item">
                                          <span className="sched-runs-time">{formatNextRun(run.finished_at)}</span>
                                          <span
                                            className={
                                              run.status === "success"
                                                ? "sched-runs-ok"
                                                : "sched-runs-fail"
                                            }
                                          >
                                            {run.status === "success" ? "成功" : "失败"}
                                          </span>
                                          <span className="text-xs text-[var(--faint)]">
                                            {formatRunTrigger(run.trigger)}
                                          </span>
                                          {run.task_id ? (
                                            <button
                                              className="text-xs text-[var(--accent)] underline-offset-2 hover:underline"
                                              onClick={() => selectTask(run.task_id || "", { backTo: "schedules" })}
                                            >
                                              打开任务
                                            </button>
                                          ) : (
                                            <span className="text-xs text-[var(--faint)]">无任务</span>
                                          )}
                                          {run.error ? (
                                            <span className="sched-runs-error" title={run.error}>
                                              {run.error}
                                            </span>
                                          ) : (
                                            <span className="text-xs text-[var(--faint)]">—</span>
                                          )}
                                        </li>
                                      ))}
                                    </ul>
                                  ) : null}
                                </div>
                              </td>
                            </tr>
                          ) : null}
                          {expandedHookScheduleId === s.id ? (
                            <tr className="sched-runs-row">
                              <td colSpan={7}>
                                <div className="sched-runs-panel space-y-3">
                                  <div className="text-xs font-semibold uppercase tracking-wide text-[var(--faint)]">
                                    入站 Webhook（带密钥）
                                  </div>
                                  <p className="text-xs leading-relaxed text-[var(--muted)]">
                                    给 Shortcuts / 本机脚本用：用 POST 打下面的地址，带上密钥，就会像「立即跑」一样触发本条自动化。
                                    跑次来源会显示为 Webhook。只做入站，不会把结果推到外部。密钥请当密码保管，轮换后旧的立刻失效。
                                  </p>
                                  <div className="space-y-1">
                                    <div className="text-xs text-[var(--faint)]">触发地址（可复制）</div>
                                    <div className="flex flex-wrap items-center gap-2">
                                      <code className="max-w-full break-all rounded bg-[var(--panel-2,rgba(0,0,0,0.04))] px-2 py-1 text-xs">
                                        {scheduleWebhookUrl(s.id)}
                                      </code>
                                      <button
                                        type="button"
                                        className="btn-ghost !px-2 !py-1 text-xs"
                                        onClick={() => copyHookText("地址", scheduleWebhookUrl(s.id))}
                                      >
                                        复制地址
                                      </button>
                                    </div>
                                  </div>
                                  <div className="text-xs leading-relaxed text-[var(--muted)]">
                                    鉴权方式（二选一）：
                                    <br />
                                    1）Header：<code className="text-[var(--accent)]">X-Hook-Token: &lt;密钥&gt;</code>
                                    <br />
                                    2）查询参数：<code className="text-[var(--accent)]">?token=&lt;密钥&gt;</code>
                                  </div>
                                  <div className="flex flex-wrap items-center gap-2">
                                    <button
                                      type="button"
                                      className="btn-primary !py-1.5 text-xs"
                                      disabled={busy}
                                      onClick={() => onRotateHookToken(s.id)}
                                    >
                                      {s.hook_configured ? "轮换密钥" : "生成密钥"}
                                    </button>
                                    <span className="text-xs text-[var(--faint)]">
                                      {s.hook_configured
                                        ? "已配置密钥（列表不显示明文；轮换后旧密钥失效）"
                                        : "尚未生成密钥，外部调用会返回 401"}
                                    </span>
                                    {hookCopyTip && expandedHookScheduleId === s.id ? (
                                      <span className="text-xs text-[var(--accent)]">{hookCopyTip}</span>
                                    ) : null}
                                  </div>
                                  {hookReveal && hookReveal.id === s.id ? (
                                    <div className="rounded border border-[var(--accent)]/30 bg-[var(--panel-2,rgba(0,0,0,0.03))] p-3 space-y-2">
                                      <div className="text-xs font-medium text-[var(--accent)]">
                                        新密钥（只显示这一次，请立即复制保存）
                                      </div>
                                      <div className="flex flex-wrap items-center gap-2">
                                        <code className="max-w-full break-all rounded bg-black/5 px-2 py-1 text-xs">
                                          {hookReveal.hook_token}
                                        </code>
                                        <button
                                          type="button"
                                          className="btn-ghost !px-2 !py-1 text-xs"
                                          onClick={() => copyHookText("密钥", hookReveal.hook_token)}
                                        >
                                          复制密钥
                                        </button>
                                      </div>
                                      <p className="text-xs text-[var(--muted)]">{hookReveal.usage_hint}</p>
                                      <div className="text-xs text-[var(--faint)]">
                                        示例：
                                        <code className="ml-1 break-all">
                                          {`curl -X POST '${scheduleWebhookUrl(s.id)}' -H 'X-Hook-Token: ${hookReveal.hook_token}'`}
                                        </code>
                                      </div>
                                    </div>
                                  ) : null}
                                </div>
                              </td>
                            </tr>
                          ) : null}
                        </Fragment>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ) : null}
        </div>
      </main>
      </div>

      {feishuChooserOpen && typeof document !== "undefined"
        ? createPortal(
            <div className="shelf-overlay" role="dialog" aria-modal="true" aria-label="导出到飞书">
              <button
                type="button"
                className="shelf-overlay-backdrop"
                aria-label="关闭"
                onClick={() => setFeishuChooserOpen(false)}
              />
              <div className="shelf-overlay-panel feishu-chooser-panel">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h2 className="font-display text-base font-semibold text-[var(--ink)]">导出到飞书</h2>
                    <p className="mt-1 text-xs leading-relaxed text-[var(--muted)]">
                      还未连接飞书账号。可先去连接，导出写到「我的」云文档；也可先用应用空间导出。
                    </p>
                  </div>
                  <button
                    type="button"
                    className="btn-ghost !py-1.5 text-xs"
                    onClick={() => setFeishuChooserOpen(false)}
                  >
                    关闭
                  </button>
                </div>
                <div className="mt-4 flex flex-col gap-2">
                  <button
                    type="button"
                    className="btn-primary w-full !py-2 text-sm"
                    disabled={busy || feishuOAuthBusy}
                    onClick={() => void onChooserConnect()}
                  >
                    {feishuOAuthBusy ? "连接中…" : "去连接"}
                  </button>
                  <button
                    type="button"
                    className="btn-ghost w-full !py-2 text-sm"
                    disabled={busy || !report || selected?.status !== "succeeded"}
                    onClick={() => void doExportFeishu(true)}
                  >
                    先用应用空间导出
                  </button>
                </div>
                {feishuOAuth?.redirect_uri ? (
                  <p className="mt-3 text-[11px] leading-relaxed text-[var(--faint)]">
                    开放平台需登记回调：
                    <button
                      type="button"
                      className="btn-text !text-[11px] ml-1"
                      onClick={async () => {
                        const u = feishuOAuth.redirect_uri;
                        try {
                          await navigator.clipboard.writeText(u);
                          setFeishuCopyTip("已复制回调地址，去开放平台粘贴登记");
                          window.setTimeout(() => setFeishuCopyTip(""), 2500);
                        } catch {
                          setError(`请手动复制回调地址：${u}`);
                        }
                      }}
                    >
                      复制回调地址
                    </button>
                  </p>
                ) : null}
                {feishuCopyTip ? (
                  <p className="mt-2 text-xs text-[var(--accent)]">{feishuCopyTip}</p>
                ) : null}
              </div>
            </div>,
            document.body
          )
        : null}

      {schedToast ? (
        <div
          className={`sched-toast ${schedToast.status === "failed" ? "sched-toast-fail" : "sched-toast-ok"}`}
          role="status"
        >
          <div className="sched-toast-body">
            <div className="sched-toast-title">
              {schedToast.status === "failed" ? "自动化失败" : "自动化完成"}
            </div>
            <div className="sched-toast-text" title={schedToast.error || ""}>
              {formatNoticeLine(schedToast)}
            </div>
          </div>
          <div className="sched-toast-actions">
            {schedToast.task_id ? (
              <button type="button" className="btn-ghost !px-2 !py-1 text-xs" onClick={() => openNotice(schedToast)}>
                打开任务
              </button>
            ) : null}
            <button
              type="button"
              className="btn-text !text-xs"
              onClick={() => {
                markNoticesRead([schedToast.run_id]);
                dismissSchedToast();
              }}
            >
              关闭
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
