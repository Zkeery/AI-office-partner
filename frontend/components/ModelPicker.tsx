"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { listModels, type ModelOption } from "@/lib/api";
import s from "./model-picker.module.css";

const marks: Record<string, string> = { deepseek: "D", openai: "G", qwen: "千", doubao: "豆", mock: "M" };

export function ModelPicker({ value, onChange, disabled = false, variant = "default" }: {
  value: string;
  onChange: (id: string) => void;
  disabled?: boolean;
  variant?: "default" | "composer";
}) {
  const [models, setModels] = useState<ModelOption[]>([]);
  const [open, setOpen] = useState(false);
  const [above, setAbove] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const id = useId();
  const selected = models.find(m => m.id === value);
  const modelTags: Record<string, string> = { "deepseek-chat": "Chat", "deepseek-reasoner": "Reasoner", "qwen-plus": "Plus", "qwen-turbo": "Turbo", "gpt-4.1-mini": "Mini" };
  const selectedTag = selected ? modelTags[selected.model] : undefined;
  const selectedLabel = selected?.model === "gpt-4.1-mini" ? "GPT-4.1" : selected?.label;

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(false);
    try { setModels((await listModels()).filter(model => model.available)); }
    catch { setError(true); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    if (!open) return;
    function outside(e: PointerEvent) { if (!root.current?.contains(e.target as Node)) setOpen(false); }
    function escape(e: KeyboardEvent) {
      if (e.key === "Escape") { setOpen(false); trigger.current?.focus(); }
    }
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("pointerdown", outside); document.removeEventListener("keydown", escape); };
  }, [open]);

  return <div className={s.root} data-variant={variant} ref={root}>
    <button ref={trigger} type="button" className={s.trigger} disabled={disabled}
      aria-label={selected ? `选择模型，当前 ${selected.label}` : "选择模型"}
      title={selected ? `${selected.label} · ${selected.model}` : "选择本次任务使用的模型"}
      aria-expanded={open} aria-controls={id} onClick={() => {
        setAbove(window.innerHeight - (trigger.current?.getBoundingClientRect().bottom || 0) < 350);
        setOpen(v => !v);
      }}>
      {variant === "composer" ? <svg className={s.bolt} width="19" height="19" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M13.4 2.3 4.2 13.1a1 1 0 0 0 .8 1.7h5.2l-.7 6a.8.8 0 0 0 1.4.6l9.2-10.5a1 1 0 0 0-.8-1.7h-5.2l.7-6.2a.8.8 0 0 0-1.4-.7Z" /></svg> : <span className={s.dot} data-ready={Boolean(selected?.available)} />}
      <span className={s.modelName}>{variant === "composer" ? selectedLabel || "选择模型" : selected?.label || "选择模型"}</span>
      {variant === "composer" && selectedTag ? <span className={s.modelTag}>{selectedTag}</span> : null}
      <svg className={s.chevron} width="14" height="14" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m5 8 5 5 5-5" /></svg>
    </button>
    {open ? <div className={s.panel} id={id} data-above={above}>
      <div className={s.heading}><strong>本次使用的模型</strong><span>由你决定</span></div>
      {loading ? <p className={s.notice} role="status">正在读取模型…</p> : error ? <div className={s.notice} role="alert">暂时无法读取模型列表。<button type="button" onClick={() => void refresh()}>重试</button></div> :
        <div className={s.options} role="group" aria-label="可选模型">
          {!models.length ? <p className={s.notice}>暂时没有可用模型，请稍后再试。</p> : null}
          {models.map(model => <button type="button" className={s.option} key={model.id}
            aria-pressed={value === model.id} disabled={!model.available}
            onClick={() => { onChange(model.id); setOpen(false); trigger.current?.focus(); }}>
            <span className={s.mark} data-provider={model.id}>{marks[model.id] || "AI"}</span>
            <span className={s.copy}><strong>{model.label}</strong><small>{model.model || "型号待配置"}</small></span>
            <span className={s.state} data-ready={model.available}>{value === model.id ? "✓ 已选" : model.status === "mock" ? "模拟" : "可用"}</span>
          </button>)}
        </div>}
      <p className={s.foot}>任务全程沿用你的选择。</p>
    </div> : null}
  </div>;
}
