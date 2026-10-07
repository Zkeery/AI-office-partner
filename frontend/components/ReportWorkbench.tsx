"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AnalysisSummary, DataChart, ReportDocument, ReportVersion, ReportVersionPreview,
  getReportDocument, getTableAnalysis, listReportVersions, previewReportVersion,
  restoreReportVersion, rewriteReport,
} from "@/lib/api";

const REASONS: Record<string, string> = {
  generated: "生成", legacy: "原始报告", rewrite: "全文改写",
  section_rewrite: "章节改写", restore: "恢复", merge: "合并",
};

function numeric(value: number | null, digits = 2): string {
  return value === null ? "—" : value.toLocaleString("zh-CN", { maximumFractionDigits: digits });
}

function formatted(value: number, kind?: string): string {
  return kind === "percent" ? numeric(value * 100) + "%" : numeric(value);
}

function timestamp(value: string): string {
  return new Date(/Z$|[+-]\d{2}:\d{2}$/.test(value) ? value : value + "Z").toLocaleString("zh-CN");
}

function Chart({ chart }: { chart: DataChart }) {
  const trimmed = chart.kind === "line" && chart.labels.length > 24;
  const labels = trimmed ? chart.labels.slice(-24) : chart.labels;
  const values = trimmed ? chart.values.slice(-24) : chart.values;
  const low = Math.min(0, ...values);
  const high = Math.max(0, ...values) || 1;
  const span = high - low || 1;
  const y = (value: number) => 214 - ((value - low) / span) * 182;
  const step = 550 / Math.max(values.length, 1);
  const x = (index: number) => 70 + step * (index + 0.5);
  const axisY = y(0);
  return (
    <figure className="rounded-xl border soft-divider bg-white/40 p-3">
      <figcaption className="mb-2 text-sm font-medium text-[var(--ink)]">
        {chart.title}{trimmed ? "（最近 24 个月）" : ""}
      </figcaption>
      <svg viewBox="0 0 640 278" className="w-full" role="img" aria-label={chart.title}>
        <title>{chart.title}，数值由完整数据计算</title>
        {[0, 0.5, 1].map((ratio) => {
          const value = low + ratio * span;
          return (
            <g key={ratio}>
              <line x1="65" x2="620" y1={y(value)} y2={y(value)} stroke="#d9e5e5" strokeDasharray="3 4" />
              <text x="58" y={y(value) + 4} textAnchor="end" fontSize="11" fill="#617779">{formatted(value, chart.value_format)}</text>
            </g>
          );
        })}
        <line x1="65" x2="620" y1={axisY} y2={axisY} stroke="#91aaaa" />
        {chart.kind === "line" ? (
          <polyline points={values.map((value, index) => x(index) + "," + y(value)).join(" ")} fill="none" stroke="#167d8d" strokeWidth="3" />
        ) : null}
        {values.map((value, index) => (
          <g key={index}>
            {chart.kind === "bar" ? (
              <rect x={x(index) - step * 0.28} y={Math.min(y(value), axisY)} width={step * 0.56} height={Math.max(1, Math.abs(y(value) - axisY))} rx="3" fill="#167d8d">
                <title>{labels[index] + "：" + formatted(value, chart.value_format)}</title>
              </rect>
            ) : (
              <circle cx={x(index)} cy={y(value)} r="4" fill="#167d8d"><title>{labels[index] + "：" + formatted(value, chart.value_format)}</title></circle>
            )}
            {values.length <= 12 || index % Math.ceil(values.length / 8) === 0 ? (
              <text x={x(index)} y="243" textAnchor="middle" fontSize="10" fill="#617779">
                {labels[index].length > 9 ? labels[index].slice(0, 8) + "…" : labels[index]}
              </text>
            ) : null}
          </g>
        ))}
      </svg>
      <details className="text-xs text-[var(--muted)]">
        <summary className="cursor-pointer">查看图表数值</summary>
        <div className="mt-2 max-h-44 overflow-auto">
          <table className="w-full text-left"><thead><tr><th className="p-1">分类 / 时间</th><th className="p-1">{chart.metric}</th></tr></thead>
            <tbody>{chart.labels.map((label, index) => <tr key={index}><td className="p-1">{label}</td><td className="p-1 tabular-nums">{formatted(chart.values[index], chart.value_format)}</td></tr>)}</tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}

function AnalysisPanel({ analysis }: { analysis: AnalysisSummary }) {
  const [tableId, setTableId] = useState(analysis.tables[0]?.id || "");
  const table = analysis.tables.find((item) => item.id === tableId) || analysis.tables[0];
  if (!table) return null;
  return (
    <section className="space-y-4 rounded-xl border soft-divider p-4" aria-label="完整数据分析">
      <div>
        <h4 className="text-sm font-semibold text-[var(--ink)]">数据已完整计算</h4>
        <p className="mt-1 text-xs leading-relaxed text-[var(--muted)]">
          {analysis.source_count} 个文件 · {analysis.sheet_count} 个工作表 · {numeric(analysis.row_count, 0)} 行。
          下载 Excel 可查看全部数据、复算公式与图表。
        </p>
      </div>
      <label className="block text-xs text-[var(--muted)]">
        查看工作表
        <select className="field mt-1 w-full" value={table.id} onChange={(event) => setTableId(event.target.value)}>
          {analysis.tables.map((item) => <option key={item.id} value={item.id}>{item.source} / {item.sheet}（{item.row_count} 行）</option>)}
        </select>
      </label>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[470px] text-left text-xs">
          <caption className="mb-2 text-left text-[var(--muted)]">{table.sheet} · {table.row_count} 行 × {table.column_count} 列</caption>
          <thead className="border-b soft-divider text-[var(--muted)]"><tr>{["指标", "有效数", "求和", "均值", "最小 / 最大"].map((name) => <th key={name} className="px-2 py-2 font-medium">{name}</th>)}</tr></thead>
          <tbody>{table.metrics.map((metric) => (
            <tr key={metric.index} className="border-b soft-divider">
              <th className="px-2 py-2 font-medium">{metric.column}</th>
              <td className="px-2 py-2 tabular-nums">{numeric(metric.count, 0)}</td>
              <td className="px-2 py-2 tabular-nums">{metric.aggregation === "mean" ? "—" : formatted(metric.sum, metric.kind)}</td>
              <td className="px-2 py-2 tabular-nums">{formatted(metric.mean, metric.kind)}</td>
              <td className="px-2 py-2 tabular-nums">{formatted(metric.min, metric.kind)} / {formatted(metric.max, metric.kind)}</td>
            </tr>
          ))}</tbody>
        </table>
        {!table.metrics.length ? <p className="mt-2 text-xs text-[var(--muted)]">此表没有可计算的数字列，完整数据仍保存在 Excel 中。</p> : null}
      </div>
      {table.charts.map((chart, index) => <Chart key={table.id + "-" + index} chart={chart} />)}
      {table.periods.length ? (
        <details className="text-xs text-[var(--muted)]">
          <summary className="cursor-pointer">月度汇总与同比环比</summary>
          <p className="my-2">基期缺失或为 0 时显示「—」。</p>
          <div className="max-h-72 overflow-auto">
            <table className="w-full min-w-[400px] text-left">
              <thead><tr>{["月份", "指标", "计算值", "环比", "同比"].map((name) => <th className="p-2" key={name}>{name}</th>)}</tr></thead>
              <tbody>{table.periods.map((period, index) => <tr key={index}>
                <td className="p-2">{period.period}</td><td className="p-2">{period.metric}{period.aggregation === "mean" ? "（均值）" : ""}</td><td className="p-2">{formatted(period.value, table.metrics.find((metric) => metric.column === period.metric)?.kind)}</td>
                <td className="p-2">{period.mom_pct === null ? "—" : numeric(period.mom_pct) + "%"}</td><td className="p-2">{period.yoy_pct === null ? "—" : numeric(period.yoy_pct) + "%"}</td>
              </tr>)}</tbody>
            </table>
          </div>
        </details>
      ) : null}
      {table.warnings.length || table.issue_count ? (
        <details className="rounded-lg bg-amber-50 p-3 text-xs text-amber-900">
          <summary className="cursor-pointer">数据提示 · {table.issue_count} 条需核对记录</summary>
          {table.warnings.length ? <ul className="mt-2 list-disc space-y-1 pl-4">{table.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul> : null}
          {table.issues.length ? <div className="mt-3 max-h-48 overflow-auto">
            <p className="mb-2">离群值仍参与统计。下方显示 {table.issues.length} 条，原始行号可在上传文件中核对。</p>
            <table className="w-full min-w-[400px] text-left"><thead><tr><th className="p-1">行号</th><th className="p-1">字段</th><th className="p-1">值</th><th className="p-1">说明</th></tr></thead>
              <tbody>{table.issues.map((issue, index) => <tr key={index}><td className="p-1">{issue.row}</td><td className="p-1">{issue.column}</td><td className="max-w-28 break-all p-1">{issue.value}</td><td className="p-1">{issue.message}</td></tr>)}</tbody>
            </table>
          </div> : null}
        </details>
      ) : null}
    </section>
  );
}

export function ReportWorkbench({
  taskId, report, editable, busy, onBusyChange, onChanged,
}: {
  taskId: string; report: string; editable: boolean; busy: boolean;
  onBusyChange: (value: boolean) => void; onChanged: () => Promise<void>;
}) {
  const [document, setDocument] = useState<ReportDocument | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisSummary | null>(null);
  const [openEditor, setOpenEditor] = useState(false);
  const [openHistory, setOpenHistory] = useState(false);
  const [target, setTarget] = useState("");
  const [instruction, setInstruction] = useState("");
  const [versions, setVersions] = useState<ReportVersion[]>([]);
  const [previewNumber, setPreviewNumber] = useState<number | null>(null);
  const [preview, setPreview] = useState<ReportVersionPreview | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [working, setWorking] = useState("");
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  const reload = useCallback(async () => {
    const [doc, data] = await Promise.all([getReportDocument(taskId), getTableAnalysis(taskId)]);
    if (!mounted.current) return doc;
    setDocument(doc);
    setAnalysis(data);
    setTarget((previous) => previous === "full" || doc.sections.some((part) => part.id === previous) ? previous : doc.sections[0]?.id || "full");
    return doc;
  }, [taskId]);

  // biome-ignore lint/correctness/useExhaustiveDependencies: A changed parent report invalidates the document endpoint even when taskId is unchanged.
  useEffect(() => {
    reload().catch((failure: Error) => { if (mounted.current) setError(failure.message); });
  }, [reload, report]);

  // biome-ignore lint/correctness/useExhaustiveDependencies: A new report version must refresh the available version list.
  useEffect(() => {
    if (!openHistory) return;
    let active = true;
    listReportVersions(taskId).then((data) => {
      if (!active) return;
      setVersions(data.items);
      setPreviewNumber((previous) => previous && data.items.some((item) => item.version === previous) ? previous : data.items[1]?.version || data.current_version);
    }).catch((failure: Error) => { if (active) setError(failure.message); });
    return () => { active = false; };
  }, [openHistory, taskId, document?.version]);

  // biome-ignore lint/correctness/useExhaustiveDependencies: Diff output depends on the latest report version as well as the selected historical version.
  useEffect(() => {
    if (!openHistory || previewNumber === null) return;
    let active = true;
    setLoadingPreview(true);
    setPreview(null);
    previewReportVersion(taskId, previewNumber).then((data) => {
      if (active) setPreview(data);
    }).catch((failure: Error) => { if (active) setError(failure.message); })
      .finally(() => { if (active) setLoadingPreview(false); });
    return () => { active = false; };
  }, [openHistory, previewNumber, taskId, document?.version]);

  async function rewrite() {
    if (!document || !instruction.trim()) return;
    setWorking("正在修改选定内容…");
    onBusyChange(true);
    setError(""); setNotice("");
    try {
      await rewriteReport(taskId, instruction.trim(), {
        scope: target === "full" ? "full" : "section",
        section_id: target === "full" ? undefined : target,
        expected_version: document.version,
      });
      if (mounted.current) {
        await onChanged();
        const doc = await reload();
        setInstruction("");
        setNotice("已保存 v" + doc.version + "，上一版本仍可查看和恢复。");
      }
    } catch (failure) {
      if (mounted.current) setError(failure instanceof Error ? failure.message : "改写失败，原版本已保留");
    } finally {
      setWorking(""); onBusyChange(false);
    }
  }

  async function restore() {
    if (!document || !preview) return;
    setWorking("正在恢复版本…");
    onBusyChange(true);
    setError(""); setNotice("");
    try {
      await restoreReportVersion(taskId, preview.version, document.version);
      if (mounted.current) {
        await onChanged();
        const doc = await reload();
        setNotice("已将 v" + preview.version + " 恢复为 v" + doc.version + "，所有版本均保留。");
      }
    } catch (failure) {
      if (mounted.current) setError(failure instanceof Error ? failure.message : "恢复失败");
    } finally {
      setWorking(""); onBusyChange(false);
    }
  }

  return (
    <div className="space-y-4">
      {analysis ? <AnalysisPanel key={analysis.id} analysis={analysis} /> : null}
      <div className="flex flex-wrap items-center gap-2 border-t soft-divider pt-3">
        <span className="mr-auto text-xs text-[var(--muted)]">{document ? "当前 v" + document.version : "正在读取版本…"}</span>
        <button className="btn-ghost !py-1.5 text-xs" type="button" disabled={!editable || busy || !document} aria-expanded={openEditor} onClick={() => setOpenEditor((value) => !value)}>
          {openEditor ? "收起修改" : "修改内容"}
        </button>
        <button className="btn-ghost !py-1.5 text-xs" type="button" disabled={busy || !document} aria-expanded={openHistory} onClick={() => setOpenHistory((value) => !value)}>
          {openHistory ? "收起版本" : "版本记录"}
        </button>
      </div>
      {error ? <p role="alert" className="rounded-lg bg-red-50 p-3 text-xs text-[var(--danger)]">{error} <button type="button" className="underline" disabled={busy} onClick={() => { setError(""); void reload().catch((failure: Error) => setError(failure.message)); }}>刷新版本</button></p> : null}
      {notice ? <p role="status" className="text-xs text-[var(--accent)]">{notice}</p> : null}
      {working ? <p role="status" className="text-xs text-[var(--muted)]">{working}</p> : null}
      {openEditor && document ? (
        <form className="space-y-3 rounded-xl border soft-divider p-4" onSubmit={(event) => { event.preventDefault(); void rewrite(); }}>
          <label className="block text-xs text-[var(--muted)]">修改范围
            <select className="field mt-1 w-full" value={target} disabled={busy} onChange={(event) => setTarget(event.target.value)}>
              {document.sections.map((part) => <option key={part.id} value={part.id}>仅此章节 · {part.title}</option>)}
              <option value="full">全文</option>
            </select>
          </label>
          <label className="block text-xs text-[var(--muted)]">修改要求
            <textarea className="field mt-1 min-h-24 w-full" placeholder="例如：把这节压缩成三条建议，保留数字和来源" value={instruction} onChange={(event) => setInstruction(event.target.value)} maxLength={2000} required disabled={busy} />
          </label>
          <p className="text-xs text-[var(--faint)]">{target === "full" ? "全文改写会保存为新版本，原稿保留。" : "只替换选中章节，其余正文保持原样；修改后保存新版本。"}</p>
          <button type="submit" className="btn-primary !py-2 text-xs" disabled={busy || !instruction.trim()}>保存为新版本</button>
        </form>
      ) : null}
      {openHistory ? (
        <section className="space-y-3 rounded-xl border soft-divider p-4" aria-label="报告版本记录">
          <label className="block text-xs text-[var(--muted)]">选择版本
            <select className="field mt-1 w-full" value={previewNumber ?? ""} disabled={busy || !versions.length} onChange={(event) => setPreviewNumber(Number(event.target.value))}>
              {!versions.length ? <option value="">加载中…</option> : null}
              {versions.map((version) => <option key={version.version} value={version.version}>
                {"v" + version.version + " · " + (REASONS[version.reason] || version.reason) + " · " + timestamp(version.created_at)}
              </option>)}
            </select>
          </label>
          {loadingPreview ? <p className="text-xs text-[var(--muted)]">正在读取版本差异…</p> : null}
          {preview ? <>
            <p className="text-xs text-[var(--muted)]">{preview.instruction || REASONS[preview.reason]} · {numeric(preview.characters, 0)} 字符</p>
            <p className="text-xs text-[var(--faint)]">与当前版本比较：红色「−」为当前内容，绿色「＋」为选中版本内容。</p>
            <pre className="max-h-72 overflow-auto rounded-lg bg-white/60 p-3 text-xs leading-relaxed" aria-label="版本差异">
              {preview.diff ? preview.diff.split("\n").map((line, index) => <span key={index} className={"block whitespace-pre-wrap break-all " + (line.startsWith("+") ? "text-emerald-800" : line.startsWith("-") ? "text-red-700" : "text-[var(--muted)]")}>{line || " "}</span>) : "与当前版本内容相同。"}
            </pre>
            {preview.diff_truncated ? <p className="text-xs text-[var(--faint)]">差异较长，仅显示前 2,000 行；下方可查看完整版本正文。</p> : null}
            <details className="text-xs text-[var(--muted)]"><summary className="cursor-pointer">查看此版本全文</summary><pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-white/60 p-3">{preview.markdown}</pre></details>
            <button type="button" className="btn-ghost !py-2 text-xs" disabled={busy || !editable || preview.version === document?.version} onClick={() => void restore()}>恢复此版（保留现有版本）</button>
          </> : null}
        </section>
      ) : null}
    </div>
  );
}
