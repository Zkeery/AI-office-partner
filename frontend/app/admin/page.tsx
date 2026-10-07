"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getRuntimeHealth, getTask, getWorkspace, setWorkspace, listExperts, listModels, listScheduleRuns,
  listSchedules, listSkills, listTasks,
  type Expert, type ModelOption, type RuntimeHealth, type Schedule,
  type ScheduleRun, type Skill, type Task,
} from "@/lib/api";
import { ScheduleEditor } from "@/components/ScheduleEditor";

type AdminRuntime = RuntimeHealth & {
  default_model_id?: string | null;
  default_schedule_token_budget?: number;
};

export default function AdminPage() {
  const [tab, setTab] = useState<"runtime" | "schedules" | "diagnostics">("runtime");
  const [health, setHealth] = useState<AdminRuntime | null>(null);
  const [models, setModels] = useState<ModelOption[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [experts, setExperts] = useState<Expert[]>([]);
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [editing, setEditing] = useState<Schedule | null>(null);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [runScheduleId, setRunScheduleId] = useState("");
  const [runs, setRuns] = useState<ScheduleRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [workspaceRoot, setWorkspaceRoot] = useState("");
  const [workspaceBusy, setWorkspaceBusy] = useState(false);
  const [workspaceSaved, setWorkspaceSaved] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [runtime, modelList, skillList, expertList, scheduleList, taskList, workspace] = await Promise.all([
        getRuntimeHealth(), listModels(), listSkills(), listExperts(), listSchedules(), listTasks(), getWorkspace(),
      ]);
      setHealth(runtime);
      setModels(modelList);
      setSkills(skillList);
      setExperts(expertList);
      setSchedules(scheduleList);
      setTasks(taskList);
      setWorkspaceRoot(workspace.root);
    } catch (e) {
      setError(e instanceof Error ? e.message : "管理数据读取失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  async function selectTask(id: string) {
    setSelectedTask(null);
    setError("");
    if (!id) return;
    try { setSelectedTask(await getTask(id)); }
    catch (e) { setError(e instanceof Error ? e.message : "诊断读取失败"); }
  }

  async function saveWorkspace() {
    setWorkspaceBusy(true);
    setWorkspaceSaved(false);
    setError("");
    try {
      const workspace = await setWorkspace(workspaceRoot.trim());
      setWorkspaceRoot(workspace.root);
      setWorkspaceSaved(true);
    } catch (e) { setError(e instanceof Error ? e.message : "资料库配置保存失败"); }
    finally { setWorkspaceBusy(false); }
  }

  async function selectRuns(id: string) {
    setRunScheduleId(id);
    setRuns([]);
    setError("");
    if (!id) return;
    try { setRuns(await listScheduleRuns(id)); }
    catch (e) { setError(e instanceof Error ? e.message : "跑次读取失败"); }
  }

  return (
    <main className="mx-auto max-w-5xl space-y-6 p-6 sm:p-10">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm text-[var(--muted)]">AI办公搭子 · 本机管理</p>
          <h1 className="font-display mt-1 text-3xl">管理工作台</h1>
          <p className="mt-2 text-sm text-[var(--muted)]">运行参数、自动化配置与执行诊断集中在这里维护。</p>
        </div>
        <div className="flex gap-2">
          <button className="btn-ghost" disabled={loading} onClick={() => void refresh()}>刷新</button>
          <a className="btn-ghost" href="/">返回工作台</a>
        </div>
      </header>
      <nav aria-label="管理导航" className="flex flex-wrap gap-2 border-b border-[var(--line)] pb-3">
        {([
          ["runtime", "运行配置"], ["schedules", "自动化配置"], ["diagnostics", "执行诊断"],
        ] as const).map(([value, label]) => (
          <button key={value} className={tab === value ? "btn-primary" : "btn-ghost"} onClick={() => { setTab(value); setEditing(null); }}>{label}</button>
        ))}
      </nav>
      {error && <p role="alert" className="text-sm text-[var(--danger)]">{error}</p>}
      {loading && <p role="status" className="text-sm text-[var(--muted)]">正在读取管理数据…</p>}

      {tab === "runtime" && <div className="space-y-5">
        <section className="panel-card space-y-3 p-5">
          <h2 className="text-lg font-semibold">服务默认配置</h2>
          <dl className="grid gap-3 text-sm sm:grid-cols-2">
            <div><dt className="text-[var(--muted)]">默认模型</dt><dd className="mt-1 font-semibold">{health?.default_model_id || (health?.llm_mock ? "mock" : "未配置")} · {health?.llm_model || "—"}</dd></div>
            <div><dt className="text-[var(--muted)]">自动化单次内部上限</dt><dd className="mt-1 font-semibold">{health?.default_schedule_token_budget?.toLocaleString() || "—"} tokens</dd></div>
            <div><dt className="text-[var(--muted)]">模型运行方式</dt><dd>{health?.llm_mock ? "工程模拟" : health?.llm_configured ? "真实调用已配置" : "待配置"}</dd></div>
            <div><dt className="text-[var(--muted)]">检索运行方式</dt><dd>{health?.search_mock ? "工程模拟" : health?.search_configured ? "真实检索已配置" : "待配置"}</dd></div>
          </dl>
          <p className="text-sm text-[var(--muted)]">全局默认模型与接入凭据由本项目 .env 维护；这里展示配置状态。单条自动化的覆盖参数在「自动化配置」中管理。</p>
        </section>
        <section className="panel-card space-y-3 p-5">
          <h2 className="text-lg font-semibold">资料库目录</h2>
          <label className="block text-sm">本机授权根目录<input className="field mt-2" value={workspaceRoot} onChange={e => { setWorkspaceRoot(e.target.value); setWorkspaceSaved(false); }} placeholder="本机目录的绝对路径" /></label>
          <div className="flex items-center gap-3"><button className="btn-ghost" disabled={workspaceBusy || !workspaceRoot.trim()} onClick={() => void saveWorkspace()}>{workspaceBusy ? "保存中…" : "保存目录"}</button>{workspaceSaved && <p role="status" className="text-sm">目录已保存</p>}</div>
        </section>
        <section className="panel-card space-y-3 p-5">
          <h2 className="text-lg font-semibold">模型接入</h2>
          <div className="grid gap-3 sm:grid-cols-2">{models.map(model => <div key={model.id} className="rounded-lg border border-[var(--line)] p-3 text-sm">
            <div className="flex justify-between gap-2"><strong>{model.label}</strong><span>{model.available ? "可用" : "待配置"}</span></div>
            <p className="mt-1 text-[var(--muted)]">{model.provider} · {model.model}</p>
            <p className="mt-1 text-xs text-[var(--muted)]">{model.hint}</p>
          </div>)}</div>
        </section>
        <section className="panel-card space-y-3 p-5">
          <h2 className="text-lg font-semibold">技能与专家</h2>
          <p className="text-sm text-[var(--muted)]">普通任务根据需求自动匹配；以下为当前运行配置。</p>
          <div className="grid gap-4 sm:grid-cols-2">
            <div><h3 className="mb-2 font-semibold">技能</h3><ul className="space-y-2 text-sm">{skills.map(skill => <li key={skill.id}><strong>{skill.name}</strong><p className="text-[var(--muted)]">{skill.description}</p></li>)}</ul></div>
            <div><h3 className="mb-2 font-semibold">专家</h3><ul className="space-y-2 text-sm">{experts.map(expert => <li key={expert.id}><strong>{expert.name}</strong><p className="text-[var(--muted)]">{expert.description}</p></li>)}</ul></div>
          </div>
        </section>
      </div>}

      {tab === "schedules" && (editing ? <div className="space-y-4">
        <h2 className="text-xl font-semibold">管理：{editing.name}</h2>
        <ScheduleEditor admin initial={editing} schedules={schedules} skills={skills} experts={experts} onClose={() => setEditing(null)} onSaved={async () => { setEditing(null); await refresh(); }} />
      </div> : <section className="panel-card space-y-3 p-5">
        <h2 className="text-lg font-semibold">自动化内部配置</h2>
        <p className="text-sm text-[var(--muted)]">管理模型、技能、专家、执行上限、触发依赖和材料读取策略。修改后保留规则原有启停状态。</p>
        <div className="space-y-3">{schedules.map(schedule => <div key={schedule.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[var(--line)] p-3">
          <div><p className="font-semibold">{schedule.name}</p><p className="text-sm text-[var(--muted)]">{schedule.model_id || "历史未配置"} · {schedule.token_budget?.toLocaleString() || "服务默认"} tokens · {schedule.enabled ? "启用" : "停用"}</p></div>
          <button className="btn-ghost" onClick={() => setEditing(schedule)}>管理配置</button>
        </div>)}</div>
        {!schedules.length && <p className="text-sm text-[var(--muted)]">暂无自动化。</p>}
      </section>)}

      {tab === "diagnostics" && <div className="space-y-5">
        <section className="panel-card space-y-3 p-5">
          <h2 className="text-lg font-semibold">任务执行诊断</h2>
          <label className="block text-sm">选择任务<select className="field mt-2" value={selectedTask?.id || ""} onChange={e => void selectTask(e.target.value)}><option value="">请选择</option>{tasks.map(task => <option key={task.id} value={task.id}>{task.title}</option>)}</select></label>
          {selectedTask && <div className="space-y-3 text-sm">
            <p>任务 ID：{selectedTask.id}</p><p>模型：{selectedTask.model_id || "历史任务"} · {selectedTask.model_name || "—"}</p>
            <p>状态：{selectedTask.status} · 调用：{selectedTask.usage?.calls || 0} 次 · 返回用量：{selectedTask.usage?.total_tokens || 0} tokens · 未知：{selectedTask.usage?.unknown_calls || 0} 次 · 模拟：{selectedTask.usage?.simulated_calls || 0} 次</p>
            {selectedTask.error_message && <p className="text-[var(--danger)]">{selectedTask.error_code}: {selectedTask.error_message}</p>}
            <ol className="space-y-2">{selectedTask.steps.map(step => <li key={step.seq} className="rounded-lg border border-[var(--line)] p-3">{step.seq}. {step.name} · {step.status}{step.detail?.error_code && <p className="text-[var(--danger)]">{step.detail.error_code}</p>}</li>)}</ol>
          </div>}
        </section>
        <section className="panel-card space-y-3 p-5">
          <h2 className="text-lg font-semibold">自动化跑次诊断</h2>
          <label className="block text-sm">选择自动化<select className="field mt-2" value={runScheduleId} onChange={e => void selectRuns(e.target.value)}><option value="">请选择</option>{schedules.map(schedule => <option key={schedule.id} value={schedule.id}>{schedule.name}</option>)}</select></label>
          <div className="space-y-3">{runs.map(run => <div key={run.id} className="rounded-lg border border-[var(--line)] p-3 text-sm">
            <p>{run.started_at || "—"} · {run.status} · {run.trigger || "—"}</p><p className="text-xs text-[var(--muted)]">跑次 ID：{run.id}</p>
            <p>内部上限：{run.token_budget?.toLocaleString() || "—"} tokens · 已用/预留：{run.budget_used_tokens || 0} · 实际返回：{run.usage?.total_tokens || 0} · 未知：{run.usage?.unknown_calls || 0} 次</p>
            {run.error && <p className="text-[var(--danger)]">{run.error}</p>}
          </div>)}</div>
          {runScheduleId && !runs.length && <p className="text-sm text-[var(--muted)]">暂无跑次。</p>}
        </section>
      </div>}
    </main>
  );
}
