"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import type { Scene, Schedule, Task } from "@/lib/api";
import { ModelPicker } from "./ModelPicker";
import s from "@/app/design-lab/lilac/lilac.module.css";
import ui from "./FusionWorkspace.module.css";

export type WorkspacePanel = "compose" | "tasks" | "task" | "workspace" | "schedules";

function Icon({ name, size = 19 }: { name: string; size?: number }) {
  const shapes: Record<string, ReactNode> = {
    home: <><path d="m3 10 9-7 9 7v10H3Z" /><path d="M9 20v-7h6v7" /></>,
    files: <><rect x="7" y="3" width="13" height="16" rx="2" /><path d="M4 7v13a2 2 0 0 0 2 2h11M11 8h5M11 12h5" /></>,
    folder: <path d="M3 6h7l2 2h9v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1Z" />,
    bolt: <path d="m13 3-9 11h7l-1 7L20 9h-7Z" />,
    search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></>,
    plus: <path d="M12 5v14M5 12h14" />,
    arrow: <path d="M5 12h14m-5-5 5 5-5 5" />,
    up: <path d="M12 20V4m-6 6 6-6 6 6" />,
    chart: <><path d="M4 3v17h17M8 15v-4M13 15V6M18 15V9" /></>,
    pen: <><path d="m4 16-1 5 5-1L20 8l-4-4Zm10-10 4 4" /><path d="m17 3 1-1a2 2 0 0 1 3 3l-1 1" /></>,
    check: <path d="m5 12 4 4L19 6" />,
    menu: <path d="M4 6h16M4 12h16M4 18h16" />,
    close: <path d="m6 6 12 12M18 6 6 18" />,
    mic: <><rect x="8" y="2" width="8" height="13" rx="4" /><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3m-4 0h8" /></>,
    layout: <><rect x="3" y="3" width="18" height="18" rx="2" /><path d="M3 9h18M9 9v12" /></>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{shapes[name] || shapes.files}</svg>;
}

function BrandMark() {
  return <span className={s.brandMark} aria-hidden="true"><svg viewBox="0 0 36 36" fill="none"><path d="M7 10.5 18 5v13L7 24Z" fill="currentColor" opacity=".45" /><path d="m18 5 11 5.5V24l-11-6Z" fill="currentColor" opacity=".7" /><path d="m7 24 11-6 11 6-11 6Z" fill="currentColor" /></svg></span>;
}

const navigation: [WorkspacePanel, string, string][] = [["compose", "home", "工作台"], ["tasks", "files", "我的任务"], ["workspace", "folder", "资料库"], ["schedules", "bolt", "自动化"]];
const statusNames: Record<string, string> = { planning: "规划中", plan_ready: "待执行", running: "处理中", paused: "已暂停", succeeded: "已完成", failed: "失败", archived: "已归档", merged: "已合并" };

export function FusionShell({ panel, title, tasks, onNavigate, onTask, onNew, onSearch, children }: {
  panel: WorkspacePanel; title?: string; tasks: Task[]; onNavigate: (panel: WorkspacePanel) => void;
  onTask: (id: string) => void; onNew: () => void; onSearch: () => void; children: ReactNode;
}) {
  const [drawer, setDrawer] = useState(false);
  useEffect(() => {
    function keydown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); onSearch(); }
      if (event.key === "Escape") setDrawer(false);
    }
    window.addEventListener("keydown", keydown);
    return () => window.removeEventListener("keydown", keydown);
  }, [onSearch]);
  const recent = tasks.filter(task => task.status !== "merged").slice(0, 5);
  function navigate(next: WorkspacePanel) { setDrawer(false); onNavigate(next); }
  return <div className={`${s.shell} ${ui.liveShell}`}>
    {drawer ? <button className={s.navBackdrop} aria-label="关闭导航遮罩" onClick={() => setDrawer(false)} /> : null}
    <aside className={`${s.sidebar} ${drawer ? s.sidebarOpen : ""}`}>
      <button className={`${s.brand} ${ui.brandButton}`} onClick={() => navigate("compose")}><BrandMark /><span>办公搭子<small>任务 · 分析 · 交付</small></span></button>
      <div className={s.workspace}><span className={s.workspaceAvatar}>Z</span><span>我的工作空间<small>个人空间</small></span></div>
      <button className={s.createButton} onClick={() => { setDrawer(false); onNew(); }}><Icon name="plus" size={17} />新建任务</button>
      <nav className={s.navigation} aria-label="主导航">
        {navigation.map(([next, icon, label]) => <button key={next} aria-current={panel === next || (next === "tasks" && panel === "task") ? "page" : undefined} className={panel === next || (next === "tasks" && panel === "task") ? s.navSelected : ""} onClick={() => navigate(next)}><Icon name={icon} /><span>{label}</span></button>)}
      </nav>
      <div className={s.recentNav}><div><span>最近的任务</span></div>{recent.map(task => <button key={task.id} title={task.title} onClick={() => { setDrawer(false); onTask(task.id); }}><span className={s.recentDot} />{task.title}</button>)}</div>
      <div className={s.sidebarNote}><span className={s.noteSpark}><Icon name="bolt" size={18} /></span><strong>按计划完成重复工作</strong><p>设置周期与执行内容，<br />自动整理报告和文稿。</p><button onClick={() => navigate("schedules")}>查看自动化<Icon name="arrow" size={14} /></button></div>
      <div className={s.user}><span className={s.userAvatar}>Z</span><span><strong>我的空间</strong><small>今天也从容一点。</small></span></div>
    </aside>
    <div className={s.main}>
      <header className={s.topbar}><div><button className={s.mobileMenu} aria-label="打开导航" onClick={() => setDrawer(true)}><Icon name="menu" /></button><span>我的空间</span><span className={s.slash}>/</span><strong className={ui.breadcrumb}>{panel === "task" ? title || "任务详情" : navigation.find(item => item[0] === panel)?.[2]}</strong></div><div><button className={s.searchButton} aria-label="搜索任务" onClick={onSearch}><Icon name="search" size={17} /><span>搜索任务或报告</span><kbd>⌘ K</kbd></button><span className={ui.localBadge}>本机工作台</span></div></header>
      {children}
    </div>
  </div>;
}

type Composer = {
  prompt: string; onPrompt: (value: string) => void; modelId: string; onModel: (value: string) => void;
  files: File[]; refs: string[]; onFiles: (files: File[]) => void; onRemoveRef: (path: string) => void;
  urls: string; onUrls: (value: string) => void; busy: boolean; onSubmit: () => void;
  onError: (message: string) => void; onShelf: () => void; choice: string;
};

function taskCategory(task: Task) {
  if (task.skill_id === "table_analysis") return "数据分析";
  if (/research|policy|industry|market/.test(task.skill_id || "")) return "调研";
  return "写作";
}

export function FusionHome({ composer, tasks, loading, schedules, scenes, onScene, onTask, onNavigate }: {
  composer: Composer; tasks: Task[]; loading: boolean; schedules: Schedule[]; scenes: Scene[];
  onScene: (scene: Scene) => void; onTask: (id: string) => void; onNavigate: (panel: WorkspacePanel) => void;
}) {
  const [filter, setFilter] = useState("全部");
  const [links, setLinks] = useState(false);
  const [allScenes, setAllScenes] = useState(false);
  const [date, setDate] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);
  useEffect(() => { setDate(new Intl.DateTimeFormat("zh-CN", { month: "long", day: "numeric", weekday: "long", timeZone: "Asia/Shanghai" }).format(new Date())); }, []);
  const visible = tasks.filter(task => task.status !== "merged");
  const completed = visible.filter(task => task.has_report);
  const running = visible.filter(task => ["planning", "running"].includes(task.status));
  const cards = completed.filter(task => filter === "全部" || taskCategory(task) === filter).slice(0, 6);
  const enabledSchedules = schedules.filter(schedule => schedule.enabled);
  const ratio = visible.length ? completed.length / visible.length : 0;
  function addFiles(files: File[]) {
    if (files.some(file => !/\.(txt|md|markdown|pdf|docx|csv|xlsx)$/i.test(file.name))) { composer.onError("支持 TXT、Markdown、PDF、Word、CSV 和 XLSX 文件。"); return; }
    if (files.some(file => file.size > 20 * 1024 * 1024)) { composer.onError("每份文件不能超过 20 MB。"); return; }
    if (composer.files.length + composer.refs.length + files.length > 3) { composer.onError("每个任务最多添加 3 份材料，请先移除不需要的文件。"); return; }
    composer.onFiles([...composer.files, ...files]);
  }
  function shortcut(id: string, fallback: string) {
    const scene = scenes.find(item => item.id === id);
    if (scene) onScene(scene); else composer.onPrompt(fallback);
    textarea.current?.focus();
  }
  return <div className={s.content}>
    <section className={s.welcome}><div className={s.greeting}><span>你好，今天也从容一点</span><span>{date}</span></div><h1>今天，专注<span>重要的工作。</span></h1><p>分析数据、整理文稿、生成报告，在这里开始。</p></section>
    <div className={s.startGrid}><div className={s.startMain}>
      <form className={s.composer} aria-label="新建任务" onSubmit={event => { event.preventDefault(); if (!composer.busy) composer.onSubmit(); }}>
        <textarea ref={textarea} aria-label="告诉搭子你想做什么" placeholder="描述任务，或添加文件开始…" value={composer.prompt} onChange={event => composer.onPrompt(event.target.value)} disabled={composer.busy} rows={3} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) { event.preventDefault(); if (!composer.busy) event.currentTarget.form?.requestSubmit(); } }} />
        <input ref={fileInput} className={ui.fileInput} type="file" aria-label="上传任务材料" accept=".txt,.md,.markdown,.pdf,.docx,.csv,.xlsx" multiple disabled={composer.busy} onChange={event => { addFiles(Array.from(event.target.files || [])); event.target.value = ""; }} />
        {composer.files.map((file, index) => <div className={s.attachment} key={`${file.name}-${index}`}><span><Icon name="files" size={13} /></span><strong title={file.name}>{file.name}</strong><button type="button" disabled={composer.busy} aria-label={`移除 ${file.name}`} onClick={() => composer.onFiles(composer.files.filter((_, i) => i !== index))}><Icon name="close" size={13} /></button></div>)}
        {composer.refs.map(path => <div className={s.attachment} key={path}><span><Icon name="folder" size={13} /></span><strong title={path}>{path.split("/").pop()}</strong><button type="button" disabled={composer.busy} aria-label={`移除 ${path}`} onClick={() => composer.onRemoveRef(path)}><Icon name="close" size={13} /></button></div>)}
        <div className={s.composerBottom}><div className={s.composerTools}><button className={s.attachButton} type="button" aria-label="添加材料" title="添加材料" disabled={composer.busy} onClick={() => fileInput.current?.click()}><Icon name="plus" size={21} /></button><ModelPicker value={composer.modelId} onChange={composer.onModel} variant="composer" disabled={composer.busy} /></div><div className={s.composerActions}><span className={`${s.micButton} ${ui.pendingVoice}`} aria-label="语音输入尚未接入" title="语音输入尚未接入"><Icon name="mic" size={22} /></span><button className={s.send} type="submit" aria-label="发送任务" title="发送任务" disabled={composer.busy || !composer.prompt.trim()}>{composer.busy ? <span className={ui.spinner} /> : <Icon name="up" size={22} />}</button></div></div>
      </form>
      <div className={ui.composerOptions}><button onClick={() => setLinks(value => !value)}>{links ? "收起链接" : "添加参考链接"}</button><button onClick={composer.onShelf}>能力货架{composer.choice ? ` · ${composer.choice}` : ""}</button><button onClick={() => setAllScenes(value => !value)}>{allScenes ? "收起场景" : "更多场景"}</button><span>{composer.busy ? "正在准备任务…" : "内容将发送给所选模型处理"}</span></div>
      {links ? <label className={ui.extraField}>参考链接（每行一个，最多 3 个）<textarea className="field" rows={2} aria-label="参考链接" value={composer.urls} onChange={event => composer.onUrls(event.target.value)} disabled={composer.busy} placeholder="https://example.com" /></label> : null}
      <div className={s.shortcuts}>{[["chart", "分析表格", "table_analysis", "分析这份表格，整理关键指标和趋势。"], ["pen", "起草文稿", "weekly_report", "根据以下事实整理本周工作总结。"], ["search", "调研资料", "competitor_research", "整理产品调研资料，标注来源。"], ["layout", "生成演示", "proposal", "把以下内容整理成演示文稿大纲。"]].map(([icon, label, id, prompt]) => <button key={label} disabled={composer.busy} onClick={() => shortcut(id, prompt)}><span><Icon name={icon} size={16} /></span>{label}<Icon name="arrow" size={13} /></button>)}</div>
      {allScenes ? <div className={ui.sceneGrid}>{scenes.map(scene => <button key={scene.id} disabled={composer.busy} onClick={() => onScene(scene)}><strong>{scene.name}</strong><small>{scene.blurb}</small></button>)}</div> : null}
    </div><aside className={s.progressCard}><div className={s.progressHeading}><span>当前任务</span><Icon name="files" size={16} /></div><div className={s.progressOverview}><div className={s.progressRing}><svg viewBox="0 0 70 70" aria-hidden="true"><circle cx="35" cy="35" r="28" fill="none" stroke="#ebe5f6" strokeWidth="5" /><circle cx="35" cy="35" r="28" fill="none" stroke="var(--progress-purple)" strokeWidth="5" strokeLinecap="round" strokeDasharray={`${ratio * 176} 176`} transform="rotate(-90 35 35)" /></svg><span>{completed.length}<small>/ {visible.length}</small></span></div><div><strong>{loading ? "正在读取任务…" : `已有 ${completed.length} 份成果`}</strong><p>{running.length ? `${running.length} 项任务处理中` : "准备好，开始下一件事"}</p></div></div><div className={s.progressFoot}><button onClick={() => onNavigate("tasks")}>查看全部任务</button><Icon name="arrow" size={14} /></div></aside></div>
    <section className={s.results}><div className={s.sectionHeading}><h2>最近的成果<span>来自你的真实任务</span></h2><button onClick={() => onNavigate("tasks")}>查看全部<Icon name="arrow" size={14} /></button></div><div className={s.filters} aria-label="按成果类型筛选">{["全部", "数据分析", "写作", "调研"].map(value => <button key={value} aria-pressed={filter === value} onClick={() => setFilter(value)}>{value}</button>)}<span className={s.resultCount}>{completed.filter(task => filter === "全部" || taskCategory(task) === filter).length} 份成果</span></div>
      {loading ? <p className={ui.empty} role="status">正在加载成果…</p> : cards.length ? <div className={s.resultGrid}>{cards.map(task => { const category = taskCategory(task); const icon = category === "数据分析" ? "chart" : category === "调研" ? "search" : "pen"; return <button key={task.id} className={s.resultCard} onClick={() => onTask(task.id)}><div className={`${s.cover} ${category === "写作" ? s.weeklyCover : category === "调研" ? s.researchCover : s.salesCover}`}><div className={ui.realCover}><Icon name={icon} size={23} /><strong>{task.title}</strong><span>{category} · 查看报告</span><i /><i /><i /></div></div><div className={s.cardBody}><div className={s.cardTitle}><span><Icon name={icon} size={15} /></span><h3>{task.title}</h3><Icon name="arrow" size={16} /></div><p>{task.model_label || "历史任务"}{task.model_name ? ` · ${task.model_name}` : ""}</p><div className={s.cardMeta}><span>{category}</span><span className={s.completed}><Icon name="check" size={11} />{statusNames[task.status] || task.status}</span></div></div></button>; })}</div> : <div className={ui.empty}>这里还没有{filter === "全部" ? "" : filter}成果。完成任务后，报告会出现在这里。</div>}
    </section>
    <section className={s.bottomGrid}><div className={s.activity}><div className={s.sectionHeading}><h2>工作足迹</h2><span>最近任务</span></div>{visible.slice(0, 3).map(task => <div className={s.activityRow} key={task.id}><span className={s.activityIcon}><Icon name={task.has_report ? "check" : "files"} size={14} /></span><p><strong>{task.title}</strong>{statusNames[task.status] || task.status}</p><button aria-label={`打开 ${task.title}`} onClick={() => onTask(task.id)}><Icon name="arrow" size={15} /></button></div>)}{!visible.length && !loading ? <p className={ui.empty}>从上方描述你的第一项任务。</p> : null}</div><div className={s.automation}><span className={s.automationIcon}><Icon name="bolt" size={21} /></span><div><h3>{enabledSchedules.length ? `已启用 ${enabledSchedules.length} 条自动化` : "让重复工作自动完成"}</h3><p>设置执行周期，查看每次运行的结果。</p><button onClick={() => onNavigate("schedules")}>查看自动化<Icon name="arrow" size={13} /></button></div></div></section>
    <footer className={s.footer}><span>有条理地完成工作，也给自己留点余地。</span></footer>
  </div>;
}
