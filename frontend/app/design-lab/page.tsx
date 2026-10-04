"use client";

import { useEffect, useRef, useState } from "react";
import s from "./design-lab.module.css";
import { StudioArtwork, studioFlavors, type StudioFlavor } from "./StudioIdentity";

type Theme = "clear" | "orbit" | "paper" | "studio";
type Screen = "home" | "report";
const directions: { id: Theme; letter: string; name: string; english: string; subtitle: string; detail: string; sources: { name: string; url: string }[] }[] = [
  { id: "clear", letter: "A", name: "清透协作", english: "CLEAR", subtitle: "飞书 × Microsoft Fluent", detail: "蓝色主行动、轻盈层次、清晰的任务分区。适合每天长时间使用的办公工作台。", sources: [{ name: "飞书文档", url: "https://www.feishu.cn/product/docs" }, { name: "Microsoft Fluent 2", url: "https://fluent2.microsoft.design/" }] },
  { id: "orbit", letter: "B", name: "专业深色", english: "ORBIT", subtitle: "Linear", detail: "石墨色界面、细边界和紧凑列表。把执行进度、数据和结果放在同一视野里。", sources: [{ name: "Linear", url: "https://linear.app/" }] },
  { id: "paper", letter: "C", name: "文档极简", english: "PAPER", subtitle: "Notion", detail: "纸面留白、安静的工具栏、内容优先。适合写作、研究与长报告阅读。", sources: [{ name: "Notion", url: "https://www.notion.com/product" }] },
  { id: "studio", letter: "D", name: "活力创作", english: "STUDIO", subtitle: "Figma × Stripe", detail: "有力的标题、鲜明的色块和作品式卡片。让创作入口与办公成果更有辨识度。", sources: [{ name: "Figma", url: "https://www.figma.com/" }, { name: "Stripe", url: "https://stripe.com/" }] },
];

function Icon({ name, size = 20 }: { name: string; size?: number }) {
  const paths: Record<string, React.ReactNode> = {
    home: <><path d="m3 10 9-7 9 7v10H3Z" /><path d="M9 20v-7h6v7" /></>,
    grid: <><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>,
    file: <><path d="M6 3h8l4 4v14H6Z" /><path d="M14 3v5h5M9 12h6M9 16h6" /></>,
    folder: <path d="M3 6h7l2 2h9v12H3Z" />,
    bolt: <path d="m13 2-9 12h7l-1 8 10-13h-7Z" />,
    search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></>,
    plus: <path d="M12 5v14M5 12h14" />,
    chevron: <path d="m8 10 4 4 4-4" />,
    chart: <><path d="M4 3v17h17M8 15v-4M13 15V6M18 15V9" /></>,
    spark: <><path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z" /><path d="m20 2 .6 1.4L22 4l-1.4.6L20 6l-.6-1.4L18 4l1.4-.6Z" /></>,
    check: <path d="m5 12 4 4L19 6" />,
    arrow: <><path d="M12 19V5m-6 6 6-6 6 6" /></>,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    settings: <><circle cx="12" cy="12" r="3" /><path d="m9 3 6 0 1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1Z" /></>,
    attach: <path d="m8 13 7-7a3 3 0 0 1 4 4L9 20a5 5 0 0 1-7-7L13 2M6 15l9-9" />,
    more: <><circle cx="5" cy="12" r="1" /><circle cx="12" cy="12" r="1" /><circle cx="19" cy="12" r="1" /></>,
    download: <><path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5" /></>,
    menu: <path d="M4 6h16M4 12h16M4 18h16" />,
    close: <path d="m6 6 12 12M18 6 6 18" />,
    book: <><path d="M12 5c-3-2-6-2-9-1v15c3-1 6-1 9 1 3-2 6-2 9-1V4c-3-1-6-1-9 1Z" /><path d="M12 5v15" /></>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] || paths.file}</svg>;
}

function Mark() { return <span className={s.mark}><svg viewBox="0 0 32 32" fill="none" aria-hidden="true"><path d="M7 23V11a4 4 0 0 1 8 0v12M15 18h4a6 6 0 1 0 0-12M19 18l6 8" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" /></svg></span>; }
const sampleTasks = [
  { title: "销售额全量分析报告", kind: "数据分析", icon: "chart", meta: "2 张工作表 · 62 行数据", time: "10:42", status: "已完成" },
  { title: "本周工作总结", kind: "写作", icon: "file", meta: "3 个关键进展 · 5 项下周计划", time: "09:28", status: "已完成" },
  { title: "产品方案调研", kind: "调研", icon: "search", meta: "正在整理参考资料", time: "09:12", status: "进行中" },
];

function SalesChart({ compact = false }: { compact?: boolean }) {
  return <div className={`${s.chart} ${compact ? s.chartCompact : ""}`}>
    <svg viewBox="0 0 560 186" role="img" aria-label="主表销售额：2025年1月2100，2026年1月4200，2026年2月6300">
      {[30, 80, 130].map((y, i) => <g key={y}><line x1="43" x2="545" y1={y} y2={y} stroke="currentColor" opacity=".1" strokeDasharray="3 4" /><text x="0" y={y + 4} fill="currentColor" opacity=".5" fontSize="11">{["6,000", "4,000", "2,000"][i]}</text></g>)}
      <path d="M55 127 C140 127 180 94 295 76 S425 31 530 21 L530 151 L55 151Z" fill="currentColor" opacity=".07" />
      <path d="M55 127 C140 127 180 94 295 76 S425 31 530 21" fill="none" stroke="currentColor" strokeWidth="3" />
      {[[55, 127], [295, 76], [530, 21]].map(([x, y]) => <circle key={x} cx={x} cy={y} r="4" fill="currentColor" />)}
      {[[55, "2025-01"], [295, "2026-01"], [530, "2026-02"]].map(([x, label]) => <text key={x} x={x} y="179" textAnchor="middle" fill="currentColor" opacity=".55" fontSize="11">{label}</text>)}
    </svg>
  </div>;
}

function Steps({ compact = false }: { compact?: boolean }) {
  return <div className={compact ? s.stepsCompact : s.steps}>
    {[ ["读取完整表格", "2 个工作表 · 62 行数据"], ["计算指标与图表", "汇总、分组与月度变化"], ["生成分析成品", "报告与 4 张数据图表"] ].map(([title, sub], i) => <div className={s.step} key={title}><span className={s.stepCheck}><Icon name="check" size={14} /></span><div><strong>{title}</strong><small>{sub}</small></div><span className={s.stepNumber}>0{i + 1}</span></div>)}
  </div>;
}

export default function DesignLab() {
  const [theme, setTheme] = useState<Theme>("studio");
  const [flavor, setFlavor] = useState<StudioFlavor>("editorial");
  const [showDirections, setShowDirections] = useState(false);
  const [screen, setScreen] = useState<Screen>("home");
  const [canvasOnly, setCanvasOnly] = useState(false);
  const [query, setQuery] = useState("");
  const [prompt, setPrompt] = useState("");
  const [toast, setToast] = useState("");
  const [sidebar, setSidebar] = useState(false);
  const [references, setReferences] = useState(false);
  const [versionOpen, setVersionOpen] = useState(false);
  const toastTimer = useRef<ReturnType<typeof setTimeout>>();
  const composer = useRef<HTMLTextAreaElement>(null);
  const searchInput = useRef<HTMLInputElement>(null);
  const selected = directions.find(d => d.id === theme)!;
  const personality = studioFlavors.find(f => f.id === flavor)!;
  const refinedStudio = theme === "studio" && flavor !== "original";
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const id = params.get("style");
    if (directions.some(d => d.id === id)) setTheme(id as Theme);
    const flavorId = params.get("flavor");
    if (studioFlavors.some(f => f.id === flavorId)) setFlavor(flavorId as StudioFlavor);
    if (params.get("screen") === "report") setScreen("report");
    setCanvasOnly(params.get("canvas") === "1");
    return () => { if (toastTimer.current) clearTimeout(toastTimer.current); };
  }, []);
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setScreen("home");
        searchInput.current?.focus();
      } else if (event.key.toLowerCase() === "n" && !event.metaKey && !event.ctrlKey && !event.altKey && !(event.target instanceof HTMLElement && (event.target.isContentEditable || ["INPUT", "TEXTAREA"].includes(event.target.tagName)))) {
        event.preventDefault();
        setScreen("home"); setPrompt(""); setSidebar(false);
        setTimeout(() => composer.current?.focus(), 20);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);
  function notify(message: string) {
    if (toastTimer.current) clearTimeout(toastTimer.current);
    setToast(message);
    toastTimer.current = setTimeout(() => setToast(""), 3500);
  }
  function changeTheme(id: Theme) {
    setTheme(id); setSidebar(false);
    const url = new URL(window.location.href); url.searchParams.set("style", id);
    window.history.replaceState(null, "", url);
  }
  function changeFlavor(id: StudioFlavor) {
    setFlavor(id); setTheme("studio"); setSidebar(false);
    const url = new URL(window.location.href);
    url.searchParams.set("style", "studio"); url.searchParams.set("flavor", id);
    window.history.replaceState(null, "", url);
  }
  function go(next: Screen) { setScreen(next); setSidebar(false); setVersionOpen(false); }
  function newTask(text = "") { go("home"); setPrompt(text); setTimeout(() => composer.current?.focus(), 20); }

  const composerBox = <form className={s.composer} onSubmit={e => { e.preventDefault(); go("report"); notify("已打开示例结果；预览不会创建真实任务。"); }}>
    <textarea ref={composer} aria-label="告诉办公搭子你的需求" placeholder={theme === "paper" ? "写下你的想法，或者放进一份材料…" : "交给我一份材料，或说说今天想完成什么…"} value={prompt} onChange={e => setPrompt(e.target.value)} rows={2} />
    <div className={s.composerBottom}><button type="button" className={s.attach} onClick={() => { setPrompt("分析这份合成销售数据，汇总各区域销售额，并生成图表。"); notify("已加入合成销售数据.xlsx 示例材料。"); }}><Icon name="attach" size={17} /><span>添加材料</span></button><span className={s.model}><Icon name="spark" size={14} /> DeepSeek</span><button className={s.send} type="submit" aria-label="预览任务结果"><span>开始处理</span><Icon name="arrow" size={17} /></button></div>
  </form>;

  const scenarios = <div className={s.scenarios}>{[["chart", "分析表格", "看清数字背后的变化"], ["file", "起草文稿", "让表达更进一步"], ["search", "调研资料", "把信息变成判断"], ["bolt", "安排自动化", "把重复工作交出去"]].map(([icon, title, sub], i) => <button className={s.scenario} key={title} onClick={() => newTask(["请分析上传表格的销售额、区域表现与月度趋势。", "请帮我起草一份结构清楚的周报。", "请调研这个产品，并整理结论和参考来源。", "帮我准备一份定期执行的工作总结任务。"][i])}><span className={s.scenarioIcon}><Icon name={icon} size={23} /></span><span><strong>{title}</strong><small>{sub}</small></span><span className={s.scenarioIndex}>0{i + 1}</span></button>)}</div>;

  const taskList = <section className={s.tasks}><div className={s.sectionHead}><h3>{theme === "studio" ? "最近的成果" : "最近任务"}<span>03</span></h3><button onClick={() => notify("这里展示 3 个任务示例，真实任务请返回现有工作台查看。")} className={s.textButton}>查看全部</button></div><div className={s.taskRows}>{sampleTasks.filter(t => t.title.includes(query) || t.kind.includes(query)).map(task => <button key={task.title} className={s.taskRow} onClick={() => { if (task.title === sampleTasks[0].title) go("report"); else notify("此卡片展示" + task.kind + "任务的视觉样式。销售分析卡片可展开查看。"); }}><span className={`${s.taskIcon} ${s["taskColor" + sampleTasks.indexOf(task)]}`}><Icon name={task.icon} size={20} /></span><span className={s.taskCopy}><strong>{task.title}</strong><small>{task.meta}</small></span><span className={s.taskKind}>{task.kind}</span><span className={task.status === "进行中" ? s.running : s.done}>{task.status === "已完成" ? <Icon name="check" size={13} /> : <span className={s.runningDot} />}{task.status}</span><time>{task.time}</time></button>)}{sampleTasks.every(t => !t.title.includes(query) && !t.kind.includes(query)) ? <p className={s.empty}>没有匹配的示例任务。</p> : null}</div></section>;

  const rightRail = <aside className={s.rightRail}><section className={s.focusCard}><div className={s.sectionHead}><h3>继续上次的工作</h3><Icon name="more" size={18} /></div><span className={s.fileThumb}><Icon name="chart" size={27} /></span><h4>销售额全量分析</h4><p>数据已算好，<br />接下来看看业务变化。</p><div className={s.focusNumbers}><strong>62<span>行数据</span></strong><strong>4<span>张图表</span></strong></div><button className={s.secondary} onClick={() => go("report")}>打开报告</button></section><section className={s.scheduleCard}><div className={s.sectionHead}><h3>自动化</h3><Icon name="bolt" size={16} /></div><strong>每周工作总结</strong><p>周五 17:30 · 定期执行</p><span className={s.scheduleFoot}><span /> 已启用<span>查看安排</span></span></section></aside>;

  const report = <div className={s.reportLayout}><article className={s.reportPaper}><div className={s.documentMeta}><span><Icon name="file" size={15} /> 数据分析报告</span><span>更新于今天 10:42</span></div><h1>销售额全量分析报告</h1><p className={s.reportLead}>从完整数据中，找到下一步行动的依据。</p><div className={s.reportActions}><span className={s.done}><Icon name="check" size={13} /> 已完成</span><span>当前 v5</span><button onClick={() => setVersionOpen(v => !v)}><Icon name="clock" size={15} /> 版本记录</button><button onClick={() => notify("已展示章节编辑入口。实际改写可在现有工作台完成。")}><Icon name="spark" size={15} /> 修改此节</button></div>{versionOpen ? <div className={s.versionPanel}><strong>版本记录</strong>{["v5 · 图表解读修订 · 当前版本", "v4 · 全文改写", "v3 · 恢复原稿", "v2 · 建议动作精简", "v1 · 首次生成"].map(v => <p key={v}>{v}</p>)}</div> : null}<section className={s.summaryBox}><span className={s.summaryLabel}><Icon name="spark" size={16} /> 关键结论</span><p>主表销售额合计 <strong>12,600</strong>，2026 年 2 月环比增长 <strong>50%</strong>。华南区域贡献略高；线下补充数据单独核算。</p></section><div className={s.metricGrid}><div><span>主表销售额</span><strong>12,600<small>元</small></strong><em>60 行完整数据</em></div><div><span>2 月环比</span><strong>+50<small>%</small></strong><em>对比 2026 年 1 月</em></div><div><span>转化率均值</span><strong>20.5<small>%</small></strong><em>未加权平均</em></div></div><section className={s.reportChart}><div className={s.sectionHead}><h3>销售额 · 月度变化</h3><span className={s.muted}>主表 · 元</span></div><SalesChart /></section><div className={s.reportEnd}><h3>建议动作</h3><p>补齐缺失的同比基期；核实订单量与转化率不变的原因；明确两张工作表的业务口径。</p><span>来源：合成销售数据.xlsx · 销售明细、线下补充</span></div></article><aside className={s.reportAside}><div className={s.sectionHead}><h3>执行依据</h3><span className={s.muted}>3 / 3</span></div><Steps /><div className={s.deliverables}><h3>交付文件</h3>{[["X", "Excel 数据与图表", "8 个工作表"], ["P", "PPT 分析演示", "18 页 · 可编辑图表"], ["W", "Word 完整报告", "含结论与来源"]].map(([letter, title, sub]) => <button key={letter} onClick={() => notify("这是下载入口的设计预览；真实文件可从原工作台下载。")}><span>{letter}</span><span><strong>{title}</strong><small>{sub}</small></span><Icon name="download" size={16} /></button>)}</div><div className={s.noteCard}><Icon name="book" size={19} /><p>数字由完整数据计算。<br />每一版修改，都有所保留。</p></div></aside></div>;

  return <div className={`${s.lab} ${canvasOnly ? s.canvasOnly : ""}`}>
    {!canvasOnly ? <header className={s.labHeader}><div className={s.labIntro}><div><span className={s.eyebrow}>AI OFFICE BUDDY / DESIGN STUDY 02</span><h1>{theme === "studio" ? "活力创作，再长出一点个性。" : "同一个办公搭子，四种设计方向。"}</h1></div><div className={s.labLinks}><a href="/design-lab/fusion" className={s.latestDesign}>查看最新融合版 →</a><a href="/" className={s.backToApp}>返回现有工作台</a></div></div><button className={s.otherDirections} onClick={() => setShowDirections(v => !v)} aria-expanded={showDirections}>{showDirections ? "收起基础方向" : "查看上一轮四种方向"} <Icon name="chevron" size={14} /></button>{showDirections || theme !== "studio" ? <div className={s.directionTabs} role="tablist" aria-label="设计方向">{directions.map(d => <button key={d.id} role="tab" aria-selected={theme === d.id} onClick={() => changeTheme(d.id)} className={`${s.directionTab} ${theme === d.id ? s.directionActive : ""}`}><span className={`${s.swatch} ${s[d.id]}`}>{d.letter}</span><span><strong>{d.name}</strong><small>{d.subtitle}</small></span>{d.id === "studio" ? <em>当前方向</em> : null}</button>)}</div> : null}{theme === "studio" ? <div className={s.flavorPicker} role="tablist" aria-label="活力创作细分风格">{studioFlavors.map(f => <button key={f.id} role="tab" aria-selected={flavor === f.id} onClick={() => changeFlavor(f.id)} className={s["flavor" + f.id]}><span className={s.flavorDot} /><span><strong>{f.name}</strong><small>{f.note}</small></span>{f.id === "editorial" ? <em>推荐</em> : null}</button>)}</div> : null}<div className={s.labUtility}><p>{theme === "studio" ? personality.note + "。工作台与报告页一起切换，原版可随时对照。" : selected.detail}</p><div><div className={s.screenTabs} aria-label="预览页面"><button aria-pressed={screen === "home"} onClick={() => go("home")}>工作台</button><button aria-pressed={screen === "report"} onClick={() => go("report")}>报告详情</button></div><button className={s.referenceToggle} onClick={() => setReferences(v => !v)} aria-expanded={references}>参考来源 <Icon name="chevron" size={14} /></button></div></div>{references ? <div className={s.references}><strong>公开页面的视觉研究</strong><p>参考字体层级、空间组织、色彩与组件关系；以下是为 AI办公搭子重新设计的界面。</p>{directions.map(d => <div key={d.id}><span>{d.letter} · {d.name}</span>{d.sources.map(source => <a key={source.url} href={source.url} target="_blank" rel="noreferrer">{source.name} <span>↗</span></a>)}</div>)}</div> : null}</header> : null}
    <div className={`${s.app} ${s[theme]} ${theme === "studio" ? s[flavor] || "" : ""}`} data-theme={theme} data-flavor={theme === "studio" ? flavor : undefined} data-screen={screen}>
      {sidebar ? <button className={s.sidebarBackdrop} aria-label="关闭导航" onClick={() => setSidebar(false)} /> : null}
      <aside className={`${s.sidebar} ${sidebar ? s.sidebarOpen : ""}`}><div className={s.brand}><Mark /><span>办公搭子<small>{theme === "orbit" ? "PERSONAL WORKSPACE" : "AI OFFICE BUDDY"}</small></span><button onClick={() => setSidebar(false)} className={s.mobileClose} aria-label="关闭侧栏"><Icon name="close" size={18} /></button></div><button className={s.newTask} onClick={() => newTask()}><Icon name="plus" size={19} /> 新建任务 <kbd>N</kbd></button><nav>{[["home", "工作台"], ["file", "我的任务"], ["folder", "资料库"], ["bolt", "自动化"]].map(([icon, label], i) => <button className={((screen === "home" && i === 0) || (screen === "report" && i === 1)) ? s.navActive : ""} key={label} onClick={() => i === 0 ? go("home") : i === 1 ? go("report") : notify(label + "入口将保留；当前预览聚焦工作台与报告详情。")}><Icon name={icon} size={19} /><span>{label}</span>{i === 1 ? <span className={s.navCount}>3</span> : null}{i === 3 ? <span className={s.navBadge}>1</span> : null}</button>)}</nav><div className={s.sidebarSection}><div className={s.sidebarLabel}>最近打开 <Icon name="more" size={16} /></div><button onClick={() => go("report")}><span className={s.recentDot} />销售额全量分析报告</button><button onClick={() => notify("这是周报任务的导航示例。")}><span className={s.recentDot} />本周工作总结</button><button onClick={() => notify("这是调研任务的导航示例。")}><span className={s.recentDot} />产品方案调研</button></div><div className={s.sidebarBottom}><button onClick={() => notify("设置与模型配置将沿用现有功能。")}><Icon name="settings" size={18} /> 设置与偏好</button><div className={s.profile}><span className={s.avatar}>Z</span><span><strong>Zoe 的工作空间</strong><small>个人空间</small></span><Icon name="chevron" size={15} /></div></div></aside>
      <div className={s.main}><header className={s.appHeader}><div className={s.breadcrumb}><button className={s.menuButton} aria-label="打开导航" onClick={() => setSidebar(true)}><Icon name="menu" /></button><span>个人空间</span><b>/</b><strong>{screen === "home" ? "工作台" : "销售分析"}</strong></div><div className={s.headerActions}><label className={s.search}><Icon name="search" size={16} /><input ref={searchInput} aria-label="搜索示例任务" placeholder="搜索任务" value={query} onChange={e => { setQuery(e.target.value); setScreen("home"); }} /><kbd>⌘ K</kbd></label><span className={s.previewBadge}>设计预览 · 示例数据</span><span className={s.avatar}>Z</span></div></header>
        {screen === "report" ? report : <div className={s.homeContent}>
          <div className={s.welcome}><div><div className={s.welcomeEyebrow}>{theme === "studio" ? personality.eyebrow : theme === "orbit" ? "YOUR WORKSPACE, IN FOCUS." : theme === "paper" ? "你的个人工作空间" : "10 月 4 日，星期日"}</div><h1>{theme === "studio" ? <>{personality.first}<br /><span>{personality.second}</span></> : theme === "paper" ? "让想法，落在纸上。" : theme === "orbit" ? "把注意力留给重要的事。" : "上午好，Zoe"}{theme === "clear" ? <span className={s.welcomeSpark}>✦</span> : null}</h1><p>{theme === "orbit" ? "从一个清晰的目标，到一份可以交付的成果。" : theme === "paper" ? "写作、研究、分析。每一份认真，都值得一个好结果。" : theme === "studio" ? personality.description : "从一份材料、一句需求，开始今天的工作。"}</p>{refinedStudio ? <div className={s.studioSignature}><span className={s.onlineDot} /><span>{flavor === "editorial" ? "YOUR IDEAS, YOUR WAY." : flavor === "pixel" ? "SYSTEM READY / 灵感已连接" : "TODAY IS A GOOD DAY TO MAKE."}</span></div> : null}</div>{theme === "studio" ? <StudioArtwork flavor={flavor} className={s.studioArt} /> : null}{theme === "orbit" ? <div className={s.orbitSummary}><span>当前工作</span><strong>03<small>个任务</small></strong><span>2 已完成 · 1 进行中</span></div> : <span className={s.welcomeEdition}>{theme === "studio" ? "VOL. 01 / YOUR PERSONAL STUDIO" : ""}</span>}</div>
          <div className={s.homeGrid}><div className={s.homePrimary}><section className={s.createSection}>{theme === "clear" ? <div className={s.createTitle}><span className={s.aiOrb}><Icon name="spark" size={22} /></span><div><strong>今天，想一起完成什么？</strong><small>读资料、写报告、分析数据，都可以交给我。</small></div></div> : null}{theme === "studio" ? <div className={s.studioCreateTop}><span>{flavor === "editorial" ? "01 / DROP YOUR NEXT IDEA" : flavor === "pixel" ? "NEW QUEST_ / 开始新的任务" : flavor === "collage" ? "✎ 一张白纸，无限可能" : "START SOMETHING"}</span><Icon name="spark" size={27} /></div> : null}{composerBox}{theme === "paper" ? <p className={s.paperHint}>从空白开始，也可以从已有材料继续。</p> : null}</section>{scenarios}{theme === "orbit" ? <section className={s.orbitResult}><div><span className={s.resultEyebrow}><Icon name="chart" size={16} /> 最近完成 · 销售分析</span><h2>数据已就绪，<br />下一步是判断。</h2><div className={s.orbitMetrics}><strong>12,600<small>主表销售额</small></strong><strong>+50%<small>2 月环比</small></strong></div><button className={s.textButton} onClick={() => go("report")}>查看完整报告 <Icon name="file" size={14} /></button></div><div className={s.orbitResultChart}><span className={s.muted}>销售额 · 月度变化</span><SalesChart compact /></div></section> : null}{taskList}</div>{rightRail}</div>
        </div>}
        <footer className={s.appFooter}><span><Icon name="spark" size={13} /> AI办公搭子</span><span>想法有去处，工作有结果。</span><span>{theme === "studio" ? "STUDIO / " + flavor.toUpperCase() : selected.english + " / 0" + (directions.findIndex(d => d.id === theme) + 1)}</span></footer>
      </div>
      {toast ? <div className={s.toast} role="status"><Icon name="check" size={18} />{toast}<button onClick={() => setToast("")} aria-label="关闭提示"><Icon name="close" size={16} /></button></div> : null}
    </div>
    {!canvasOnly ? <footer className={s.labFooter}><span>{theme === "studio" ? personality.name + " · 活力创作的原创延展" : selected.letter + " / " + selected.name + " · 视觉灵感来自 " + selected.subtitle}</span><span>可以切换方向、打开报告、输入需求；正式数据与功能保持在原工作台。</span></footer> : null}
  </div>;
}
