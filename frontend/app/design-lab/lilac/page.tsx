"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import s from "./lilac.module.css";
import { ModelPicker } from "@/components/ModelPicker";

type Screen = "home" | "report";
function Icon({ name, size = 19 }: { name: string; size?: number }) {
  const shapes: Record<string, ReactNode> = {
    home: <><path d="m3 10 9-7 9 7v10H3Z" /><path d="M9 20v-7h6v7" /></>,
    files: <><rect x="7" y="3" width="13" height="16" rx="2" /><path d="M4 7v13a2 2 0 0 0 2 2h11M11 8h5M11 12h5" /></>,
    folder: <path d="M3 6h7l2 2h9v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1Z" />,
    bolt: <path d="m13 3-9 11h7l-1 7L20 9h-7Z" />,
    search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></>,
    plus: <path d="M12 5v14M5 12h14" />,
    chevron: <path d="m8 10 4 4 4-4" />,
    arrow: <path d="M5 12h14m-5-5 5 5-5 5" />,
    up: <path d="M12 20V4m-6 6 6-6 6 6" />,
    chart: <><path d="M4 3v17h17M8 15v-4M13 15V6M18 15V9" /></>,
    pen: <><path d="m4 16-1 5 5-1L20 8l-4-4Zm10-10 4 4" /><path d="m17 3 1-1a2 2 0 0 1 3 3l-1 1" /></>,
    spark: <><path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z" /><path d="m21 2 .5 1.5L23 4l-1.5.5L21 6l-.5-1.5L19 4l1.5-.5Z" /></>,
    check: <path d="m5 12 4 4L19 6" />,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    attach: <path d="m8 13 7-7a3 3 0 0 1 4 4L9 20a5 5 0 0 1-7-7L13 2M6 15l9-9" />,
    dots: <><circle cx="5" cy="12" r="1" /><circle cx="12" cy="12" r="1" /><circle cx="19" cy="12" r="1" /></>,
    download: <><path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5" /></>,
    menu: <path d="M4 6h16M4 12h16M4 18h16" />,
    close: <path d="m6 6 12 12M18 6 6 18" />,
    help: <><circle cx="12" cy="12" r="9" /><path d="M9 8a3 3 0 0 1 6 1c0 2-3 2-3 4m0 3v.5" /></>,
    settings: <><path d="M4 7h16M4 17h16" /><circle cx="9" cy="7" r="3" fill="currentColor" stroke="none" /><circle cx="15" cy="17" r="3" fill="currentColor" stroke="none" /></>,
    mic: <><rect x="8" y="2" width="8" height="13" rx="4" /><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3m-4 0h8" /></>,
    sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5" /></>,
    layout: <><rect x="3" y="3" width="18" height="18" rx="2" /><path d="M3 9h18M9 9v12" /></>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{shapes[name] || shapes.files}</svg>;
}

function BrandMark({ large = false }: { large?: boolean }) {
  return <span className={`${s.brandMark} ${large ? s.brandMarkLarge : ""}`} aria-hidden="true"><svg viewBox="0 0 36 36" fill="none"><path d="M7 10.5 18 5v13L7 24Z" fill="currentColor" opacity=".44" /><path d="m18 5 11 5.5V24l-11-6Z" fill="currentColor" opacity=".72" /><path d="m7 24 11-6 11 6-11 6Z" fill="currentColor" /></svg></span>;
}

function BuddyFace() {
  return <span className={s.buddyFace} aria-hidden="true"><svg viewBox="0 0 88 88" fill="none"><ellipse cx="44" cy="77" rx="23" ry="4" fill="#9b74cc" opacity=".15" /><path d="M24 55 18 63m45-14 9-8" stroke="#7651a7" strokeWidth="6" strokeLinecap="round" /><g className={s.buddyWave}><path d="m71 41 1-8m0 8 6-5" stroke="#7651a7" strokeWidth="4" strokeLinecap="round" /></g><path d="m34 68-3 6m21-6 4 5" stroke="#7651a7" strokeWidth="6" strokeLinecap="round" /><rect x="19" y="14" width="50" height="56" rx="23" transform="rotate(-7 44 42)" fill="#ffe28b" /><path d="M30 20c6-4 13-5 18-3" stroke="#fff3c5" strokeWidth="4" strokeLinecap="round" /><path d="M34 36v5m16-6v5" stroke="#4d356d" strokeWidth="3.5" strokeLinecap="round" /><path d="M36 49c4 5 10 5 14-1" stroke="#4d356d" strokeWidth="2.7" strokeLinecap="round" /><ellipse cx="28" cy="46" rx="4" ry="2.5" fill="#e9ab83" opacity=".7" /><ellipse cx="57" cy="43" rx="4" ry="2.5" fill="#e9ab83" opacity=".7" /></svg></span>;
}

const tasks = [
  { id: "sales", title: "销售额全量分析", subtitle: "销售趋势、区域表现与关键结论", type: "数据分析", icon: "chart", date: "今天 10:42", state: "已完成" },
  { id: "weekly", title: "本周工作总结", subtitle: "本周进展、交付成果与下周计划", type: "写作", icon: "pen", date: "今天 09:28", state: "已完成" },
  { id: "research", title: "产品方案调研", subtitle: "产品定位、用户体验与资料来源", type: "调研", icon: "search", date: "今天 09:12", state: "进行中" },
];

function MiniChart({ large = false }: { large?: boolean }) {
  return <svg className={large ? s.largeChart : s.miniChart} viewBox="0 0 470 160" role="img" aria-label="示例销售额：2025年1月2100元，2026年1月4200元，2026年2月6300元">
    <defs><linearGradient id={large ? "lilac-fill-large" : "lilac-fill-small"} x1="0" y1="0" x2="0" y2="1"><stop stopColor="var(--chart-fill)" stopOpacity=".29" /><stop offset="1" stopColor="var(--chart-fill)" stopOpacity=".02" /></linearGradient></defs>
    {[28, 67, 106].map(y => <line key={y} x1="20" x2="450" y1={y} y2={y} stroke="#eeeaf5" strokeDasharray="3 5" />)}
    <path d="M28 106 235 65 442 24v112H28Z" fill={`url(#${large ? "lilac-fill-large" : "lilac-fill-small"})`} />
    <path d="M28 106 235 65 442 24" stroke="var(--chart-purple)" strokeWidth="2.7" strokeLinecap="round" strokeLinejoin="round" />
    {[[28,106],[235,65],[442,24]].map(([x,y]) => <circle key={x} cx={x} cy={y} r={large ? 4 : 3} fill="var(--chart-purple)" stroke="#fff" strokeWidth="2" />)}
    {[[28,"2025-01"],[235,"2026-01"],[442,"2026-02"]].map(([x,t]) => <text key={x} x={x} y="154" textAnchor="middle" fill="var(--chart-label)" fontSize="9" fontFamily="sans-serif">{t}</text>)}
  </svg>;
}

function Cover({ id }: { id: string }) {
  if (id === "sales") return <div className={`${s.cover} ${s.salesCover}`}><div className={s.coverSheet}><span className={s.coverEyebrow}>MONTHLY SALES</span><div className={s.coverNumbers}><strong>12,600<span>元</span></strong><small>↗ 50%</small></div><MiniChart /></div><span className={s.coverFile}>XLSX</span></div>;
  if (id === "weekly") return <div className={`${s.cover} ${s.weeklyCover}`}><div className={s.documentSheet}><div className={s.docIcon}><Icon name="pen" size={13} /></div><strong>本周工作总结</strong><span>WEEKLY REVIEW / OCT 04</span><i /><i /><i /><div><b>3</b><small>关键进展</small><b>5</b><small>下周计划</small></div></div><span className={s.coverFile}>DOCX</span></div>;
  return <div className={`${s.cover} ${s.researchCover}`}><div className={s.researchSheet}><div><span>01</span><strong>从信息，到洞察</strong></div><div className={s.researchTags}><i>产品定位</i><i>体验路径</i><i>关键发现</i></div><p /><p /><div className={s.researchProgress}><span /></div></div><span className={s.coverFile}>RESEARCH</span></div>;
}

export default function LilacDesign() {
  const [screen,setScreen] = useState<Screen>("home");
  const [prompt,setPrompt] = useState("");
  const [modelId,setModelId] = useState("");
  const [attachment,setAttachment] = useState(false);
  const [filter,setFilter] = useState("全部");
  const [drawer,setDrawer] = useState(false);
  const [searchOpen,setSearchOpen] = useState(false);
  const [query,setQuery] = useState("");
  const [versions,setVersions] = useState(false);
  const [toast,setToast] = useState("");
  const timer = useRef<ReturnType<typeof setTimeout>>();
  const composer = useRef<HTMLTextAreaElement>(null);
  const searchInput = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("screen") === "report") setScreen("report");
    function onKey(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); setSearchOpen(v => !v); }
      if (event.key === "Escape") { setSearchOpen(false); setDrawer(false); }
    }
    window.addEventListener("keydown",onKey);
    return () => { window.removeEventListener("keydown",onKey); if(timer.current) clearTimeout(timer.current); };
  },[]);
  useEffect(() => { if(searchOpen) searchInput.current?.focus(); },[searchOpen]);
  function notify(message:string) { if(timer.current) clearTimeout(timer.current); setToast(message); timer.current=setTimeout(()=>setToast(""),4000); }
  function go(next:Screen) { setScreen(next); setDrawer(false); setSearchOpen(false); setVersions(false); const url=new URL(window.location.href); if(next === "report") url.searchParams.set("screen","report"); else url.searchParams.delete("screen"); window.history.replaceState(null,"",url); }
  function compose(value="") { go("home"); setPrompt(value); setTimeout(()=>composer.current?.focus(),0); }
  function openTask(id:string) { if(id === "sales") go("report"); else notify("这张卡片展示"+(id === "weekly" ? "周报" : "调研")+"成果样式，销售分析可打开完整报告预览。"); }
  const filteredTasks=tasks.filter(t=>(filter === "全部" || t.type===filter));

  return <div className={s.shell}>
    {drawer ? <button className={s.navBackdrop} aria-label="关闭导航遮罩" onClick={()=>setDrawer(false)} /> : null}
    <aside className={`${s.sidebar} ${drawer ? s.sidebarOpen : ""}`}>
      <a className={s.brand} href="/design-lab/fusion"><BrandMark /><span>办公搭子<small>任务 · 分析 · 交付</small></span></a>
      <button className={s.workspace} onClick={()=>notify("当前展示 Zoe 的个人工作空间示例。")}><span className={s.workspaceAvatar}>Z</span><span>Zoe 的工作空间<small>个人空间</small></span><Icon name="chevron" size={15} /></button>
      <button className={s.createButton} onClick={()=>compose()}><Icon name="plus" size={17} />新建任务</button>
      <nav className={s.navigation} aria-label="主导航">
        {[['home','工作台'],['files','我的任务'],['folder','资料库'],['bolt','自动化']].map(([icon,title],i)=><button key={title} className={(screen === "home" && i===0)||(screen === "report" && i===1) ? s.navSelected : ""} onClick={()=>i===0 ? go("home") : i===1 ? go("report") : notify(title+"将在正式页面接入；当前预览工作台与报告详情。")}><Icon name={icon} /><span>{title}</span>{i===1 ? <small>3</small> : null}{i===3 ? <span className={s.navDot} /> : null}</button>)}
      </nav>
      <div className={s.recentNav}><div><span>最近打开</span><Icon name="dots" size={15} /></div>{tasks.map(t=><button key={t.id} onClick={()=>openTask(t.id)}><span className={s.recentDot} />{t.title}</button>)}</div>
      <div className={s.sidebarNote}><span className={s.noteSpark}><Icon name="spark" size={18} /></span><strong>按计划完成重复工作</strong><p>设置周期与执行内容，<br />自动整理报告和文稿。</p><button onClick={()=>notify("自动化入口沿用已有功能；此处为新视觉预览。")}>查看自动化<Icon name="arrow" size={14} /></button><div className={s.noteOrbit} aria-hidden="true" /></div>
      <div className={s.user}><span className={s.userAvatar}>Z</span><span><strong>Zoe</strong><small>今天也从容一点。</small></span><span className={s.online} /></div>
    </aside>

    <div className={s.main}>
      <header className={s.topbar}><div><button className={s.mobileMenu} aria-label="打开导航" onClick={()=>setDrawer(true)}><Icon name="menu" /></button><span>我的空间</span><span className={s.slash}>/</span><strong>{screen === "home" ? "工作台" : "销售分析"}</strong></div><div><button className={s.searchButton} onClick={()=>setSearchOpen(true)}><Icon name="search" size={17} /><span>搜索任务或材料</span><kbd>⌘ K</kbd></button><span className={s.previewBadge}><span />界面预览 · 示例数据</span><span className={s.headerAvatar}>Z</span></div></header>

      {screen === "home" ? <main className={s.content}>
        <section className={s.welcome}><div className={s.greeting}><span>你好，Zoe</span><span>10 月 4 日 · 星期日</span></div><h1>今天，专注<span>重要的工作。</span></h1><p>分析数据、整理文稿、生成报告，在这里开始。</p></section>
        <div className={s.startGrid}>
          <div className={s.startMain}>
            <form className={s.composer} aria-label="新建任务" onSubmit={e=>{e.preventDefault();if(!modelId){notify("请先选择本次任务使用的模型。");return;}go("report");notify("已打开示例报告；当前是设计预览，未创建真实任务。");}}>
              <textarea ref={composer} aria-label="告诉搭子你想做什么" placeholder="描述任务，或添加文件开始…" value={prompt} onChange={e=>setPrompt(e.target.value)} rows={3} onKeyDown={e=>{if(e.key==="Enter"&&!e.shiftKey&&!e.nativeEvent.isComposing&&e.keyCode!==229){e.preventDefault();e.currentTarget.form?.requestSubmit();}}} />
              {attachment ? <div className={s.attachment}><span>X</span>合成销售数据.xlsx<button type="button" aria-label="移除示例材料" onClick={()=>setAttachment(false)}><Icon name="close" size={12} /></button></div> : null}
              <div className={s.composerBottom}>
                <div className={s.composerTools}>
                  <button className={s.attachButton} type="button" aria-label="添加示例材料" title="添加材料" onClick={()=>{setAttachment(true);setPrompt("分析这份销售数据，整理关键变化与下一步建议。");}}><Icon name="plus" size={21} /></button>
                  <ModelPicker value={modelId} onChange={setModelId} variant="composer" />
                </div>
                <div className={s.composerActions}>
                  <button type="button" className={s.micButton} aria-label="语音输入（待接入）" title="语音输入 · 待接入" onClick={()=>notify("语音输入暂未接入，可先输入文字或添加材料。")}><Icon name="mic" size={22} /></button>
                  <button className={s.send} type="submit" aria-label="开始处理示例任务" title="发送任务"><Icon name="up" size={22} /></button>
                </div>
              </div>
            </form>
            <div className={s.shortcuts}>{[["chart","分析表格","请分析销售数据，整理趋势、区域表现和关键结论。"],["pen","起草文稿","请帮我写一份清晰、简洁的工作周报。"],["search","调研资料","请整理产品调研资料，并标注结论来源。"],["layout","生成演示","请把这份报告整理为演示文稿大纲。"]].map(([icon,label,text])=><button key={label} onClick={()=>compose(text)}><span><Icon name={icon} size={16} /></span>{label}<Icon name="arrow" size={13} /></button>)}</div>
          </div>
          <aside className={s.progressCard}><div className={s.progressHeading}><span>今日任务</span><Icon name="dots" size={16} /></div><div className={s.progressOverview}><div className={s.progressRing}><svg viewBox="0 0 70 70" aria-hidden="true"><circle cx="35" cy="35" r="28" fill="none" stroke="#ebe5f6" strokeWidth="5" /><circle cx="35" cy="35" r="28" fill="none" stroke="var(--progress-purple)" strokeWidth="5" strokeLinecap="round" strokeDasharray="117.3 176" transform="rotate(-90 35 35)" /></svg><span>2<small>/ 3</small></span></div><div><strong>已完成 2 项</strong><p>1 项调研任务处理中</p></div></div><div className={s.progressFoot}><span><i />产品方案调研</span><span>整理中</span></div></aside>
        </div>
        <section className={s.results}><div className={s.sectionHeading}><h2>最近的成果<span>最近生成的报告与文档</span></h2><button onClick={()=>{setFilter("全部");document.getElementById("lilac-results")?.scrollIntoView({behavior:window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",block:"center"});}}>查看全部<Icon name="arrow" size={14} /></button></div><div className={s.filters} aria-label="按成果类型筛选">{["全部","数据分析","写作","调研"].map(f=><button key={f} aria-pressed={filter===f} onClick={()=>setFilter(f)}>{f}</button>)}<span className={s.resultCount}>{filteredTasks.length} 份成果</span></div><div id="lilac-results" className={s.resultGrid}>{filteredTasks.map(t=><button key={t.id} className={s.resultCard} onClick={()=>openTask(t.id)}><Cover id={t.id} /><div className={s.cardBody}><div className={s.cardTitle}><span><Icon name={t.icon} size={15} /></span><h3>{t.title}</h3><Icon name="dots" size={16} /></div><p>{t.subtitle}</p><div className={s.cardMeta}><span>{t.date}</span><span className={t.state==="已完成" ? s.completed : s.processing}>{t.state==="已完成" ? <Icon name="check" size={11} /> : <i />}{t.state}</span></div></div></button>)}</div></section>
        <section className={s.bottomGrid}><div className={s.activity}><div className={s.sectionHeading}><h2>工作足迹</h2><span>今天</span></div><div className={s.activityRow}><span className={s.activityIcon}><Icon name="check" size={14} /></span><p><strong>销售额全量分析</strong>已生成报告与图表</p><time>10:42</time><button onClick={()=>go("report")} aria-label="查看销售分析成果"><Icon name="arrow" size={15} /></button></div><div className={s.activityRow}><span className={s.activityIcon}><Icon name="pen" size={14} /></span><p><strong>本周工作总结</strong>已整理完成</p><time>09:28</time><button onClick={()=>openTask("weekly")} aria-label="查看周报成果"><Icon name="arrow" size={15} /></button></div></div><div className={s.automation}><span className={s.automationIcon}><Icon name="bolt" size={21} /></span><div><h3>已启用每周工作总结</h3><p>工作总结将在周五 17:30 自动整理。</p><button onClick={()=>notify("这里展示每周总结的自动化入口；真实配置请返回现有工作台查看。")}>查看自动化<Icon name="arrow" size={13} /></button></div></div></section>
      </main> : <main className={s.reportContent}>
        <div className={s.reportToolbar}><button onClick={()=>go("home")}><span>←</span>返回工作台</button><div><span className={s.completed}><Icon name="check" size={13} />已完成</span><button onClick={()=>setVersions(v=>!v)} aria-expanded={versions}><Icon name="clock" size={15} />版本记录</button><button className={s.exportButton} onClick={()=>notify("这是导出入口预览。真实报告和文件可在现有工作台下载。")}>导出报告<Icon name="download" size={15} /></button></div></div>
        <div className={s.reportGrid}><article className={s.reportPaper}><div className={s.reportMeta}><span><Icon name="chart" size={14} />数据分析</span><span>更新于今天 10:42 · v5</span></div><h1>销售额全量分析报告</h1><p className={s.reportIntro}>从完整的数据里，找到下一步行动的方向。</p>{versions ? <div className={s.versionPanel}><strong>版本记录</strong>{["v5 · 图表解读修订 · 当前版本","v4 · 全文改写","v3 · 恢复原稿","v2 · 建议动作精简","v1 · 首次生成"].map(v=><p key={v}>{v}</p>)}</div> : null}<div id="lilac-summary" className={s.summary}><span><Icon name="spark" size={16} />关键结论</span><p>主表销售额合计 <strong>12,600 元</strong>，2026 年 2 月环比增长 <strong>50%</strong>。华南区域贡献略高；线下补充数据单独核算。</p></div><div className={s.reportMetrics}>{[["主表销售额","12,600","元","60 行完整数据"],["2 月环比","+50","%","对比 2026 年 1 月"],["转化率均值","20.5","%","未加权平均"]].map(([label,value,unit,note])=><div key={label}><span>{label}</span><strong>{value}<small>{unit}</small></strong><p>{note}</p></div>)}</div><section className={s.chartSection}><div className={s.sectionHeading}><h2>销售额 · 月度变化</h2><span>主表 / 元</span></div><MiniChart large /><div className={s.chartLegend}><span />主表销售额<span>2,100 → 4,200 → 6,300</span></div></section><section className={s.reportConclusion}><div className={s.sectionHeading}><h2>接下来，可以这样做</h2><button onClick={()=>notify("章节改写沿用已有功能；这里展示新的编辑入口样式。")}><Icon name="pen" size={14} />修改此节</button></div><p>补齐缺失的同比基期；核实订单量与转化率不变的原因；明确两张工作表的业务口径。</p><small>来源：合成销售数据.xlsx · 销售明细、线下补充</small></section></article><aside className={s.reportAside}><div className={s.sectionHeading}><h2>这份成果的来处</h2><span>3 / 3</span></div><div className={s.evidenceSteps}>{[["读取完整数据","2 张工作表 · 62 行记录"],["计算指标与图表","汇总、分组与月度变化"],["生成分析成果","完整报告 · 4 张数据图表"]].map(([title,note])=><div key={title}><span><Icon name="check" size={12} /></span><div><strong>{title}</strong><small>{note}</small></div></div>)}</div><div className={s.deliverables}><h2>交付文件</h2>{[["X","Excel 数据与图表","8 个工作表"],["P","PPT 分析演示","18 页 · 可编辑图表"],["W","Word 完整报告","结论、图表与来源"]].map(([letter,title,note])=><button key={letter} onClick={()=>notify("此按钮展示下载样式，真实文件请从现有工作台下载。") }><span>{letter}</span><div><strong>{title}</strong><small>{note}</small></div><Icon name="download" size={15} /></button>)}</div><div className={s.reportAsideNote}><BuddyFace /><strong>继续完善这份报告</strong><p>精简行动建议，或整理成团队汇报大纲。</p><div className={s.buddyActions}><button onClick={()=>compose("请把这份销售报告的建议部分精简成三条可执行的行动。")}>精简建议<Icon name="arrow" size={12} /></button><button onClick={()=>compose("请将这份销售报告整理成适合向团队汇报的演示大纲。")}>准备汇报<Icon name="arrow" size={12} /></button></div></div></aside></div>
      </main>}
      <footer className={s.footer}><span><span className={s.footerSpark}>✧</span>有条理地完成工作，也给自己留点余地。</span></footer>
    </div>

    {searchOpen ? <div className={s.modalBackdrop} onClick={()=>setSearchOpen(false)}><section className={s.searchModal} role="dialog" aria-modal="true" aria-label="搜索示例任务" onClick={e=>e.stopPropagation()}><div><Icon name="search" /><input ref={searchInput} aria-label="搜索任务" placeholder="搜索任务、文稿或报告…" value={query} onChange={e=>setQuery(e.target.value)} /><button onClick={()=>setSearchOpen(false)} aria-label="关闭搜索"><Icon name="close" size={17} /></button></div><p>最近的成果</p>{tasks.filter(t=>t.title.includes(query)||t.type.includes(query)).map(t=><button key={t.id} onClick={()=>openTask(t.id)}><Icon name={t.icon} size={18} /><span>{t.title}<small>{t.type} · {t.state}</small></span><Icon name="arrow" size={16} /></button>)}{tasks.every(t=>!t.title.includes(query)&&!t.type.includes(query)) ? <p>没有找到匹配的示例任务。</p> : null}</section></div> : null}
    {toast ? <div className={s.toast} role="status"><Icon name="check" size={16} />{toast}<button aria-label="关闭提示" onClick={()=>setToast("")}><Icon name="close" size={14} /></button></div> : null}
  </div>;
}
