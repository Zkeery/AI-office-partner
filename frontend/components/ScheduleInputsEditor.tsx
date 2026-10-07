"use client";

import { useEffect, useState } from "react";
import { listWorkspaceEntries } from "@/lib/api";

export type ScheduleInputs = {
  token_budget: number;
  urls: string[];
  workspace_paths: string[];
  material_mode: "snapshot" | "latest";
  include_upstream_result: boolean;
};

export const emptyScheduleInputs = (): ScheduleInputs => ({
  token_budget: 0, urls: [], workspace_paths: [], material_mode: "snapshot", include_upstream_result: false,
});

export function ScheduleInputsEditor({ value, onChange, eventMode, disabled, admin = false }: {
  value: ScheduleInputs; onChange: (value: ScheduleInputs) => void; eventMode: boolean; disabled: boolean; admin?: boolean;
}) {
  const [rel, setRel] = useState("");
  const [entries, setEntries] = useState<Awaited<ReturnType<typeof listWorkspaceEntries>>>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(false);
  useEffect(() => {
    if (!admin && !expanded) return;
    let active = true;
    setLoading(true);
    listWorkspaceEntries(rel).then(items => { if (active) { setEntries(items); setError(""); } })
      .catch(e => { if (active) { setEntries([]); setError(admin ? e.message || "资料库尚未配置" : "资料库暂不可用，请联系管理员。"); } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [rel, admin, expanded]);
  const maxFiles = value.include_upstream_result && eventMode ? 2 : 3;
  const linkCount = value.urls.filter(url => url.trim()).length;
  const materialSummary = [
    value.workspace_paths.length ? `${value.workspace_paths.length} 份资料` : "",
    linkCount ? `${linkCount} 个链接` : "",
  ].filter(Boolean).join(" · ");
  const fields = <>
    {admin && <label className="block text-sm">每次执行的 token 上限（必填）
      <input className="field" type="number" min={1024} max={1000000} step={1}
        placeholder="例如 50000" value={value.token_budget || ""}
        onChange={e => onChange({ ...value, token_budget: Number(e.target.value) })} />
      <span className="mt-1 block text-xs text-[var(--muted)]">包含生成计划、执行及重试。每次调用前预留额度，超过上限即停止；供应商未返回用量时保留预留值。</span>
    </label>}
    <label className="block text-sm">参考链接（每行一条，最多 3 条）
      <textarea className="field" aria-label="参考链接（每行一条，最多 3 条）" rows={3} value={value.urls.join("\n")}
        onChange={e => onChange({ ...value, urls: e.target.value.split("\n") })} />
    </label>
    {admin && <label className="block text-sm">资料读取方式
      <select className="field" value={value.material_mode} onChange={e => onChange({ ...value, material_mode: e.target.value as "snapshot" | "latest" })}>
        <option value="snapshot">保存时冻结材料副本</option>
        <option value="latest">每次读取所选文件的最新版</option>
      </select>
    </label>}
    {admin && eventMode && <label className="flex gap-2 text-sm">
      <input type="checkbox" checked={value.include_upstream_result}
        onChange={e => onChange({ ...value, include_upstream_result: e.target.checked })} />
      将触发本次执行的上游成果作为材料（占用 1 个文件名额）
    </label>}
    <div className="text-sm">
      <p>已选文件 {value.workspace_paths.length}/{maxFiles}</p>
      <div className="mt-2 flex flex-wrap gap-2">{value.workspace_paths.map(path => <button type="button" className="btn-ghost text-xs" key={path}
        onClick={() => onChange({ ...value, workspace_paths: value.workspace_paths.filter(item => item !== path) })}>移除 {path}</button>)}</div>
      <div className="mt-3 flex items-center gap-2"><span>资料库 / {rel || "根目录"}</span>
        {rel && <button type="button" className="btn-ghost text-xs" onClick={() => setRel(rel.split("/").slice(0, -1).join("/"))}>上一级</button>}
      </div>
      {error && <p className="mt-2 text-xs text-[var(--muted)]">{error}</p>}
      {loading ? <p>正在读取…</p> : <div className="mt-2 flex max-h-40 flex-col gap-1 overflow-auto">
        {entries.filter(entry => entry.is_dir || /\.(txt|md|docx|pdf|csv|xlsx)$/i.test(entry.name)).map(entry =>
          <button key={entry.rel} type="button" className="btn-ghost text-left text-xs"
            disabled={!entry.is_dir && (value.workspace_paths.includes(entry.rel) || value.workspace_paths.length >= maxFiles)}
            onClick={() => entry.is_dir ? setRel(entry.rel) : onChange({ ...value, workspace_paths: [...value.workspace_paths, entry.rel] })}>
            {entry.is_dir ? "打开文件夹：" : "选择："}{entry.name}
          </button>)}
      </div>}
    </div>
  </>;
  return <fieldset disabled={disabled} aria-label={admin ? undefined : "执行材料"} className="space-y-4 rounded-xl border border-[var(--line)] p-4 sm:col-span-2">
    {admin ? <legend className="px-2 text-sm font-semibold">执行材料与预算</legend> : null}
    {admin ? fields : <details onToggle={event => setExpanded(event.currentTarget.open)}>
      <summary className="cursor-pointer text-sm font-semibold">添加资料或链接（可选）
        {materialSummary ? <span className="ml-2 font-normal text-[var(--muted)]">已选 {materialSummary}</span> : null}
      </summary>
      <div className="space-y-4 pt-4">{fields}</div>
    </details>}
  </fieldset>;
}
