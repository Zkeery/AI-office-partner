"use client";

import { useState } from "react";
import { createSchedule, patchSchedule, type Schedule, type Skill, type Expert } from "@/lib/api";
import { ModelPicker } from "./ModelPicker";
import { ScheduleInputsEditor, type ScheduleInputs } from "./ScheduleInputsEditor";

export function ScheduleEditor({ initial, schedules, skills, experts, onClose, onSaved, admin = false }: {
  initial?: Schedule; schedules: Schedule[]; skills: Skill[]; experts: Expert[];
  onClose: () => void; onSaved: () => Promise<void>; admin?: boolean;
}) {
  const editingScheduleId = initial?.id;
  const closeSchedForm = onClose;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [schedName, setSchedName] = useState<string>(initial?.name || "自动化周报");
  const [schedPrompt, setSchedPrompt] = useState<string>(initial?.prompt || "");
  const [schedInterval, setSchedInterval] = useState<number>(initial?.interval_minutes || 60);
  const [customInterval, setCustomInterval] = useState(![60, 1440, 10080].includes(initial?.interval_minutes || 60));
  const [schedTriggerMode, setSchedTriggerMode] = useState<"interval" | "on_task_succeeded">(initial?.trigger_mode === "on_task_succeeded" ? "on_task_succeeded" : "interval");
  const [schedListenId, setSchedListenId] = useState<string>(initial?.listen_schedule_id || "");
  const [schedSkillId, setSchedSkillId] = useState<string>(initial?.skill_id || "");
  const [schedModelId, setSchedModelId] = useState<string>(initial?.model_id || "");
  const [schedExpertId, setSchedExpertId] = useState<string>(initial?.expert_id || "");
  const [schedInputs, setSchedInputs] = useState<ScheduleInputs>({ token_budget: initial?.token_budget || 0, urls: initial?.urls || [], workspace_paths: initial?.workspace_paths || [], material_mode: initial?.material_mode || "snapshot", include_upstream_result: initial?.include_upstream_result || false });
  const intervalPresets: { label: string; minutes: number }[] = [
    { label: "每小时", minutes: 60 },
    { label: "每天", minutes: 1440 },
    { label: "每周", minutes: 10080 },
  ];
  async function onCreateSchedule() {
    if (!schedPrompt.trim()) return;
    if (admin && !schedModelId) { setError("请先选择自动化使用的模型。"); return; }
    if (admin && (!Number.isInteger(schedInputs.token_budget) || schedInputs.token_budget < 1024 || schedInputs.token_budget > 1000000)) {
      setError("请填写 1024–1000000 之间的整数 token 预算。"); return;
    }
    if (admin && schedTriggerMode === "on_task_succeeded" && !schedListenId) {
      setError("请选择要监听的自动化（某条成功后再跑本条）");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const body = {
        workspace_paths: schedInputs.workspace_paths,
        urls: schedInputs.urls.map(url => url.trim()).filter(Boolean),
        name: schedName.trim() || "自动化",
        prompt: schedPrompt.trim(),
        interval_minutes: Math.max(1, Number(schedInterval) || 60),
        ...(admin ? {
          token_budget: schedInputs.token_budget,
          material_mode: schedInputs.material_mode,
          include_upstream_result: schedTriggerMode === "on_task_succeeded" && schedInputs.include_upstream_result,
          model_id: schedModelId,
          skill_id: schedSkillId || undefined,
          expert_id: schedExpertId || undefined,
          trigger_mode: schedTriggerMode,
          listen_schedule_id: schedTriggerMode === "on_task_succeeded" ? schedListenId || undefined : undefined,
        } : {}),
      };
      if (editingScheduleId) await patchSchedule(editingScheduleId, { ...body, ...(admin ? { skill_id: schedSkillId || null, expert_id: schedExpertId || null } : {}) });
      else await createSchedule(body);
      await onSaved();
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }


  return (
    <div className="panel-card mx-auto max-w-xl space-y-4 p-5">
      <p className="text-sm text-[var(--muted)]">
        {admin ? "选好触发方式：到点重复，或等另一条自动化成功后再跑本条。" : "写下要重复完成的工作，选择执行时间和需要的材料。"}
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
            aria-label="自动执行内容"
            rows={3}
            placeholder="例如：生成本周行业速览，并整理成可转发草稿……"
            value={schedPrompt}
            onChange={(e) => setSchedPrompt(e.target.value)}
          />
        </label>
        {admin && <div className="text-sm text-[var(--muted)] sm:col-span-2">
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
        </div>}
        {schedTriggerMode === "interval" ? (
          <div className="text-sm text-[var(--muted)] sm:col-span-2">
            <span>执行时间</span>
            <div className="mt-2 flex flex-wrap gap-2">
              {intervalPresets.map((p) => (
                <button
                  key={p.minutes}
                  type="button"
                  className={`btn-ghost !px-3 !py-1.5 text-xs ${
                    !customInterval && schedInterval === p.minutes ? "!border-[var(--accent)] !text-[var(--accent)]" : ""
                  }`}
                  onClick={() => { setSchedInterval(p.minutes); setCustomInterval(false); }}
                >
                  {p.label}
                </button>
              ))}
              {!admin && <button type="button"
                className={`btn-ghost !px-3 !py-1.5 text-xs ${customInterval ? "!border-[var(--accent)] !text-[var(--accent)]" : ""}`}
                onClick={() => setCustomInterval(true)}>自定义</button>}
            </div>
            {admin || customInterval ? <label className="mt-3 block">
              执行间隔（分钟）
              <input
                type="number"
                min={1}
                className="field"
                value={schedInterval}
                onChange={(e) => setSchedInterval(Number(e.target.value))}
              />
            </label> : null}
          </div>
        ) : admin ? (
          <label className="text-sm text-[var(--muted)] sm:col-span-2">
            监听哪条自动化（成功后触发本条）
            <select
              className="field"
              value={schedListenId}
              onChange={(e) => setSchedListenId(e.target.value)}
            >
              <option value="">请选择…</option>
              {schedules.filter(s => s.id !== editingScheduleId).map((s) => (
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
        ) : <p className="text-sm text-[var(--muted)] sm:col-span-2">执行时间：在“{schedules.find(schedule => schedule.id === schedListenId)?.name || "已关联任务"}”完成后运行。</p>}
        {admin && <label className="text-sm text-[var(--muted)]">
          技能（可选）
          <select className="field" value={schedSkillId} onChange={(e) => setSchedSkillId(e.target.value)}>
            <option value="">通用调研</option>
            {skills.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>}
        {admin && <div className="text-sm text-[var(--muted)]">
          <p className="mb-2">运行模型（必选）</p>
          <ModelPicker value={schedModelId} onChange={setSchedModelId} disabled={busy} />
        </div>}
        <ScheduleInputsEditor value={schedInputs} onChange={setSchedInputs} eventMode={schedTriggerMode === "on_task_succeeded"} disabled={busy} admin={admin} />
        {admin && <label className="text-sm text-[var(--muted)]">
          专家（可选）
          <select className="field" value={schedExpertId} onChange={(e) => setSchedExpertId(e.target.value)}>
            <option value="">不选专家</option>
            {experts.map((e) => (
              <option key={e.id} value={e.id}>
                {e.name}
              </option>
            ))}
          </select>
        </label>}
      </div>
      {error ? <p role="alert" className="text-sm text-[var(--danger)]">{error}</p> : null}
      <div className="flex flex-wrap gap-2 pt-1">
        <button
          className="btn-primary"
          disabled={
            busy ||
            !schedPrompt.trim() ||
            (admin && schedTriggerMode === "on_task_succeeded" && !schedListenId)
          }
          onClick={onCreateSchedule}
        >
          {busy ? (editingScheduleId ? "保存中…" : "创建中…") : (editingScheduleId ? "保存自动化" : "创建自动化")}
        </button>
        <button className="btn-ghost" type="button" disabled={busy} onClick={closeSchedForm}>
          取消
        </button>
      </div>
    </div>
  );

}
