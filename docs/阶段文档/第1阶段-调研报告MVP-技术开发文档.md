# 第 1 阶段技术开发文档｜调研报告 MVP（纵向切片）

> 文档同步说明（2026-10-04）：本文为对应阶段的历史设计/验收记录；当前界面、功能范围和操作方式以[当前 PRD](../PRD/PRD-当前版本.md)、[真实工作流实现](融合界面与真实工作流.md)为准。新建任务和自动化均必填 `model_id`，旧无模型参数示例请按[当前 API](../API接口.md)更新后使用。

> 配套文档：`docs/PRD/PRD.md`、`docs/阶段文档/技术适配声明.md`、`docs/阶段文档/架构方案.md`、仓库根目录《AI产品Vibe Coding通用技术栈手册》。  
> 生命周期对应 AGENTS：**阶段 2 后端 MVP 第一刀**；对产品经理口语称「开发第 1 阶段」。  
> **本文档只覆盖本阶段。开发时不得提前实现 Word 导出、本地文件夹、技能/专家、定时任务、腾讯生态、桌面/App、正式登录、上云。**

---

## 一、阶段目标

### 交付范围
打通个人本地主链路：

1. 用户用自然语言（可选链接 / 上传 ≤3 个参考文件）创建调研任务  
2. 系统生成**任务计划**，用户确认后才执行  
3. 执行中：**联网检索** + 阅读上传材料 + 起草报告；进度可见；可暂停  
4. 产出**页面可读**的 Markdown 报告，并支持**下载**  
5. 任务 / 计划 / 步骤 / 产物**本机持久化**，进程重启可恢复  
6. 执行前费用量级提示；预估超过约 **¥5** 时二次确认  

### 阶段产物
- 可运行后端（8040）+ 最小验收前端（3040）  
- SQLite 库与 `data/uploads`、`data/artifacts`  
- mock 自动化测试通过记录  
- 本阶段 README 启动说明 + 证据包目录准备  

### 验收标准（对齐 PRD，本阶段细化）
- 能完成一次「下任务 → 确认计划 → 出报告 → 下载 `.md`」  
- 未确认计划时，不得进入检索/成稿执行  
- 检索不足处不得装成已核实事实（应出现「未找到公开来源」或「待核实」类表述）  
- 界面明示：任务内容会发给当前配置的模型厂商做推理  
- 重启后端后，未完成或已完成任务仍可从列表打开，产物不丢  
- 数字效果标准 **D2 待样例打分**（真实冒烟时再定），不阻塞本阶段 mock 验收  

### 明确不做
Word；本地授权文件夹；技能/专家；定时任务；更多连接器；邮件/分享；多人账号；云部署；PPT/表格。

### 本阶段打通的主链路片段
`创建任务 → 生成计划 → 确认（含费用闸门）→ 执行（检索/读材料/写报告）→ 阅读/下载 → 可选暂停/失败重试/改计划`

---

## 二、技术适配摘要

- 引用《技术适配声明》：纵向切片；Python/FastAPI；Web；SQLite；检索 + SSE；费用软闸门。  
- **本阶段采用**：Python 3.12、FastAPI、Pydantic、pytest、SQLite、Next.js 最小页、项目 `.env`。  
- **本阶段启用**：联网检索、上传解析、长任务+SSE、费用软闸门、本地产物目录。  
- **本阶段暂缓**：Word、本地文件夹、技能/专家、定时、RAG、登录、上云。  
- **开发路径**：纵向切片。

---

## 三、技术栈与模型

| 层 | 选用 | 不引入 |
| --- | --- | --- |
| 后端 | FastAPI + Uvicorn | Django 等 |
| 校验 | Pydantic v2 | — |
| DB | SQLAlchemy 2.x + SQLite | Postgres（本阶段） |
| 测试 | pytest + httpx | — |
| 前端 | Next.js（App Router）+ TS + Tailwind | Electron/Tauri |
| 文档解析 | pypdf；python-docx | OCR |
| 检索 | 可插拔：有 `TAVILY_API_KEY` 用 Tavily；否则用内置「简易检索适配器」（开发/mock 可用固定夹具；真实验收需配置检索 Key 或接受受限检索） | 腾讯文档等 |

**模型（本阶段选型）**  
PRD 不限厂商。本阶段统一走 **OpenAI 兼容 Chat Completions**：

| 配置项 | 含义 |
| --- | --- |
| `LLM_API_KEY` | 用户自备 |
| `LLM_BASE_URL` | 如官方 OpenAI、DeepSeek、兼容网关 |
| `LLM_MODEL` | 聊天模型名 |
| `LLM_MOCK=1` | 强制 mock，不打真实模型（测试默认） |

费用估算：按「计划步数 × 粗算 token 单价」给出**量级**（非精确账单）；单价可用环境变量 `LLM_PRICE_PER_1K_CNY`（默认按保守值估算）。

---

## 四、环境与配置

### `.env.example`（无秘密）
```bash
# 服务
APP_HOST=127.0.0.1
APP_PORT=8040
FRONTEND_ORIGIN=http://127.0.0.1:3040
DATA_DIR=./data

# 模型（验收前由产品经理填写真实值；勿提交 .env）
LLM_API_KEY=
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
LLM_MOCK=0
LLM_PRICE_PER_1K_CNY=0.02

# 检索
TAVILY_API_KEY=
SEARCH_MOCK=0

# 闸门
COST_SOFT_LIMIT_CNY=5
AGENT_MAX_STEPS=12
```

### 需要用户提供
- 真实验收前：`LLM_API_KEY`（及如需的 `TAVILY_API_KEY`）  
- 开发/CI：可全程 `LLM_MOCK=1`、`SEARCH_MOCK=1`

### 端口与启动
- 后端：`8040`  
- 前端：`3040`  
- 启动前检查端口占用；只改本项目配置。

---

## 五、项目结构（本阶段新增）

```text
projects/AI办公搭子/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/           # health, tasks, uploads, events(SSE)
│   │   ├── core/          # config, errors, logging, security
│   │   ├── db/            # engine, models, session
│   │   ├── schemas/
│   │   ├── services/      # planner, agent_runtime, search, files, costing
│   │   └── prompts/
│   ├── tests/
│   ├── requirements.txt
│   └── scripts/           # 可选启动辅助
├── frontend/              # Next.js 最小验收页
├── data/                  # gitignore：office.db, uploads/, artifacts/
├── .env.example
└── README.md              # 更新启动与验收
```

---

## 六、数据、资产与状态

### 持久化
- SQLite：`data/office.db`（schema_version=1）  
- 上传：`data/uploads/{task_id}/`  
- 产物：`data/artifacts/{task_id}/report.md` 等  
- 写入：DB 事务；文件先写临时再 rename  

### 表（逻辑字段）

**tasks**  
`id, title, user_prompt, status, cost_estimate_cny, cost_confirmed, plan_json, report_path, error_code, error_message, created_at, updated_at`

**task_steps**  
`id, task_id, seq, name, status, detail_json, created_at, updated_at`

**task_events**  
`id, task_id, event_type, payload_json, created_at`（供 SSE 补播与审计）

**uploads**  
`id, task_id, filename, stored_path, mime, size_bytes, text_excerpt, created_at`

### 状态机（task.status）

```text
draft → planning → plan_ready → (confirm) → awaiting_cost_confirm? → running
running ⇄ paused → succeeded | failed
failed / plan_ready → (revise) → planning → plan_ready
```

- `awaiting_cost_confirm`：仅当预估 > `COST_SOFT_LIMIT_CNY` 且尚未 `cost_confirmed`  
- 重启：`running` 任务标为 `paused` 或由 worker 续跑（本阶段采用：**重启后标 paused，用户点继续**，避免半步脏写；事件与已完成步骤保留）

---

## 七、API / 工具设计

统一错误：`{"error":{"code":"STRING","message":"人话"}}`，HTTP 4xx/5xx；不返回堆栈。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health` | 健康检查 |
| POST | `/api/tasks` | 创建任务（prompt，可选 urls[]）→ 返回 task，异步或同步进入 planning |
| GET | `/api/tasks` | 列表 |
| GET | `/api/tasks/{id}` | 详情（含 plan、steps、report 摘要） |
| POST | `/api/tasks/{id}/plan` | 触发/重做计划生成 |
| POST | `/api/tasks/{id}/confirm` | 确认执行；若超费用软上限且未带 `confirm_cost:true` → 错误 `COST_CONFIRM_REQUIRED` |
| POST | `/api/tasks/{id}/pause` | 暂停 |
| POST | `/api/tasks/{id}/resume` | 继续 |
| DELETE | `/api/tasks/{id}` | 删除任务及上传/产物 |
| POST | `/api/tasks/{id}/uploads` | multipart 上传，校验扩展名与 ≤20MB、总数≤3 |
| GET | `/api/tasks/{id}/report` | 返回 Markdown 文本或下载 |
| GET | `/api/tasks/{id}/events` | **SSE**：进度事件流 |

### SSE 事件
`event: progress | step | artifact | done | error`  
- `progress`：`{message, percent?}`  
- `step`：`{seq, name, status}`  
- `artifact`：`{kind:"report", path}`  
- `done`：`{task_id, status}`（必须收尾）  
- `error`：`{code, message}`（必须收尾）

### Agent 工具白名单（MVP）
| 工具 | 权限 | 说明 |
| --- | --- | --- |
| `web_search` | 自动 | 查询字符串；返回标题/URL/摘要 |
| `fetch_url` | 自动 | 抓取用户或检索得到的 http(s) 页文本（限长） |
| `read_uploads` | 自动 | 读本任务已解析文本 |
| `write_report` | 自动 | 写入/更新 `report.md` |

- 最大步数：`AGENT_MAX_STEPS`（默认 12）  
- 人工确认：计划确认；费用软上限确认  
- **禁止**：发邮件、删用户磁盘任意路径、访问上传目录外路径  

---

## 八、Prompt 设计

### 1) 计划生成 `prompts/plan.md`
- 角色：调研任务规划助手  
- 输入：用户需求、可选 URL 列表、上传材料摘要  
- 输出：**严格 JSON**：`{title, steps:[{name, goal, tool_hint}], cost_factors}`  
- 约束：步骤 3～8 步；必须含检索与成稿；不执行工具  

### 2) 执行/成稿 `prompts/report.md`
- 角色：调研报告撰写助手  
- 输入：用户需求、计划、检索摘录、上传摘录  
- 输出：Markdown 报告（背景/要点/结论；引用链接列表）  
- 约束：**无来源不得写成事实**；不足处写「未找到公开来源」或「待核实」；不编造链接  

解析：计划 JSON 用 Pydantic 校验，失败有限重试（≤2）；报告做非空与标题结构弱校验。

---

## 九、验收界面（纵向切片）

- **性质**：最小可操作产品切片（非最终视觉）  
- **终端**：桌面浏览器宽度优先；不强制手机完美  
- **页面**：任务列表 | 新建任务（提示已告知模型外发）| 计划确认（含费用提示）| 执行进度 | 报告预览与下载 | 暂停/继续/删除  
- **上限**：不做技能商店、定时、多主题换肤、协作  

---

## 十、测试要求

### 第一层 mock（必须全绿）
1. 健康检查  
2. 创建任务 → mock 计划 → 状态 `plan_ready`  
3. 未 confirm 时执行接口拒绝  
4. confirm 后 mock 执行 → `succeeded` + report 文件存在  
5. 预估费用 > 软上限且未 `confirm_cost` → `COST_CONFIRM_REQUIRED`  
6. 带 `confirm_cost` 可通过  
7. 上传非法扩展名 / 超大小失败  
8. 上传合法 txt 成功并进入材料摘要  
9. 暂停 / 继续状态转换  
10. 删除任务清理 DB 与文件  
11. SSE 以 `done` 或 `error` 收尾  
12. 模拟重启：DB 中任务与 report 仍可读；`running` 恢复为 `paused`  

### 第二层真实冒烟（有 Key 后）
- 输入示例：「调研 2026 年国内 AI 办公助手产品特点，输出一页报告」  
- 记录：是否出计划、是否有检索引用、报告是否可下载、有无明显编造链接  
- D2：产品经理对 5～10 条样例打分（本阶段可先 1 条冒烟）  

---

## 十一、验收清单（产品经理照着点）

- [ ] 按 README 启动后，浏览器打开前端地址能看到页面  
- [ ] 看到「内容将发送给当前配置的模型」类提示  
- [ ] 输入一句调研需求，点创建，能看到计划步骤  
- [ ] **不点确认**时，不能直接变成「已完成报告」  
- [ ] 点确认后能看到进度，最终能打开/下载 Markdown  
- [ ] 报告里若信息不足，能看到「未找到」或「待核实」类字样（mock 或真实均应遵守）  
- [ ] 关掉后端再开，仍能在列表里找到该任务和报告  
- [ ] （可选真实 Key）再跑一条真实调研，把感受告诉 AI 以便打分  

---

## 十二、风险与待确认项

| 风险 | 缓解 |
| --- | --- |
| 无检索 Key 时真实调研质量差 | mock 夹具保证工程验收；README 写明配置 Tavily 后效果更好 |
| 费用仅为估算 | UI 标明「量级估计」；软上限防失控 |
| 网页抓取不稳定 | 限长、超时、失败写入步骤详情，不整单崩溃 |
| 模型编造链接 | Prompt 约束 + 验收人工看；后续可加链接可达性检查（非本阶段必须） |

**必须由产品经理决定的问题：无**（D2 待冒烟打分，不阻塞本阶段开发）。

---

## 十三、交接给下一阶段

本阶段结束后应就绪：
- 任务状态机、SSE、SQLite、上传与报告落盘契约  
- Agent 工具接口形状（可挂新连接器）  
- 最小前端调用方式  

下一阶段（紧随）可直接复用任务模型，增量做：Word 导出、本地文件夹、技能/专家包。

---

## 开发执行顺序（给 AI 的施工顺序）

1. 后端骨架 + 配置 + 错误模型 + health  
2. DB 模型与任务 CRUD + 状态机  
3. mock LLM / mock Search + 计划与执行服务  
4. 上传与报告文件  
5. SSE  
6. API 测试全绿  
7. Next.js 最小页对接  
8. README + 更新项目状态；准备证据包目录  
9. （有 Key 时）真实冒烟，不配 Key 则真实项记「待验」
