# API 接口与兼容说明

更新：2026-10-05。后端基址为 `http://127.0.0.1:8040`；完整机器可读定义为 `/openapi.json`，交互文档为 `/docs`。普通请求省略模型、技能/专家、预算和材料策略等技术字段，由服务端采用管理员默认配置；旧 API 显式字段继续兼容。实现和本轮验证边界见[用户界面精简](阶段文档/用户界面精简.md)、[本轮验收](evidence/2026-10-05-用户界面精简/验收说明.md)。

2026-10-04 修复后，旧 `/plan` 与 `/replan` 使用相同状态保护；任务与自动化有中断恢复和执行归属校验。具体证据与限制见[修复验收](审查报告/2026-10-04-12项缺口修复验收.md)。

## 模型与新建任务

`GET /api/models` 返回 `{ "items": [...] }`。每项包括 `id`、`label`、`provider`、`model`、`available`、`status`、`hint`，不返回密钥或端点。目录用于独立本机 `/admin` 管理页和兼容调用，普通工作台不要求选择模型；未配置项保留用于维护与诊断。

`POST /api/tasks` 的 `prompt` 必填，普通请求示例：

```json
{
  "prompt": "根据提供的事实整理一份工作周报。",
  "urls": []
}
```

`prompt` 为 1–8,000 字符，`urls` 最多 3 个。省略 `model_id` 时采用维护者 `LLM_*` 默认配置；服务端复用 `detect_scene` 判断任务场景。`model_id`、`skill_id`、`expert_id` 保留显式调用兼容，普通工作台不发送这些字段。任务保存具体 `model_id`、`model_name`、`model_label`，规划、执行、重试与改写沿用固定型号。默认配置缺失返回 `DEFAULT_MODEL_NOT_CONFIGURED`，不挑选模型目录首项、不回退到模拟或换厂商；显式配置仍按原规则校验。老任务缺型号时不伪造历史配置。

`GET /health` 提供 `default_model_id` 和 `default_schedule_token_budget`，用于本机管理页诊断；不返回模型密钥。

新建接口负责生成计划；前端随后上传材料、必要时重新规划，再调用确认执行接口。单独调用创建接口不代表报告已经生成。

## 任务生命周期

| 方法与路径 | 用途 |
| --- | --- |
| `GET /api/tasks` | 任务列表；支持 `q`、`include_merged`、`include_archived` |
| `GET /api/tasks/{task_id}` | 任务详情、步骤、材料、错误、模型与报告状态 |
| `POST /api/tasks/{task_id}/uploads` | multipart `file`；每任务最多 3 份、每份 20 MB |
| `POST /api/tasks/{task_id}/workspace-refs` | JSON `paths` 数组，显式加入资料库材料 |
| `POST /api/tasks/{task_id}/replan` | 可选 `prompt`、`urls`；重新生成计划 |
| `POST /api/tasks/{task_id}/confirm` | `{ "confirm_cost": false }` 发起执行；仅在用户确认费用后传 `true` |
| `POST /api/tasks/{task_id}/pause`、`/resume` | 暂停、继续 |
| `POST /api/tasks/merge` | `task_ids` 数组，2–20 个任务 |
| `POST /api/tasks/{task_id}/unarchive` | 恢复归档任务 |
| `DELETE /api/tasks/{task_id}` | 删除所选任务 |
| `GET /api/tasks/{task_id}/events` | SSE 事件；当前前端也使用状态轮询 |

普通任务状态：`planning` → `plan_ready` → `running` → `succeeded`；执行可进入 `paused` / `failed`，重试或重新规划后继续。另有 `archived`、`merged`。后端重启将未完成的 `running` 任务转为 `paused`，不无条件自动继续。

重启时 `planning` 转为 `failed/PLANNING_INTERRUPTED`，可重新规划；没有有效步骤时确认执行返回 `PLAN_REQUIRED`。`/plan` 与 `/replan` 均拒绝 `running`、`planning` 和 `succeeded` 状态，晚到的旧执行结果不能覆盖新计划。

普通文档正文最多 60,000 字符，任务文档合计最多 90,000 字符；超限返回 `DOCUMENT_TOO_LARGE` / `MATERIALS_TOO_LARGE`，不静默截断。DOCX 读取正文与嵌套表格；无可提取文字的 PDF 返回 `DOCUMENT_EMPTY`，混合 PDF 的无文字页会标注未 OCR。表格继续采用完整数据计算，预览不替代原始数据。

任务响应的 `usage` 包含 `calls`、`prompt_tokens`、`completion_tokens`、`total_tokens`、`unknown_calls`、`simulated_calls` 和 `estimated_cost_cny`。token 合计只统计供应商返回值；未知与模拟单独计数，旧任务不补造用量。金额仅按配置单价估算，不是供应商账单。

## 报告、分析与版本

| 方法与路径 | 请求/响应要点 |
| --- | --- |
| `GET /api/tasks/{task_id}/report` | `{ markdown, version, sections: [{id,title}] }`；不是直接返回 Markdown 文件 |
| `GET /api/tasks/{task_id}/analysis` | `{ analysis: ... \| null }`；含完整行数、指标、分组、月度值、异常及图表 |
| `POST /api/tasks/{task_id}/rewrite` | `instruction`（1–2,000 字符）、`scope`（`full`/`section`）、可选 `section_id`、`expected_version` |
| `GET /api/tasks/{task_id}/report/versions` | 当前版本号与版本列表 |
| `GET /api/tasks/{task_id}/report/versions/{version}` | 旧版正文、差异、`diff_truncated` |
| `POST /api/tasks/{task_id}/report/restore` | 必填 `version`、`expected_version`；恢复另存一个新版本 |
| `GET /api/tasks/{task_id}/report.docx`、`.xlsx`、`.pptx` | 下载实际文件；Markdown 由前端基于正文生成下载 |
| `POST /api/tasks/{task_id}/export/feishu` | 用户主动导出；普通界面走个人 OAuth 连接流程 |

改写时建议总是传 `expected_version`；章节 ID 从当前报告响应读取，不自行构造。恢复与改写遇到版本冲突返回 HTTP 409、`REPORT_CONFLICT`，刷新后重新决定，不自动覆盖最新内容。没有分析快照时 `analysis` 为 `null`，不能展示假图表。

## 自动化与资料库

`GET /api/schedules` 返回自动化列表。`POST /api/schedules` 的 `prompt` 必填，普通工作台只提交任务要求、材料/链接、名称、执行时间和开关；省略 `model_id` 时采用管理员 `LLM_*` 默认模型，省略 `token_budget` 时采用内部默认 50,000。旧显式 `model_id`、`token_budget`（1,024–1,000,000 的整数）、`skill_id`、`expert_id`、`trigger_mode`（`interval` / `on_task_succeeded`）和 `listen_schedule_id` 继续兼容，集中于本机管理能力。`interval_minutes` 默认 60、`enabled` 默认 true。新建固定具体型号，跑次继承；普通编辑保留已有型号及有效额度，显式管理更新可调整。旧缺模型规则仅在用户主动重新保存时采用管理员默认，不批量启用，原开关保持不变。

材料字段：`urls`（最多 3 个 HTTP(S) 链接）、`workspace_paths`（明确选择的相对路径）。普通工作台不提交材料策略。内部及旧 API 保留 `material_mode`（`snapshot` 保存时冻结，或 `latest` 每次读取所选文件最新版）和 `include_upstream_result`（仅事件触发），由管理配置及既有规则决定。文件最多 3 份，上游成果占 1 份；每次执行复制材料并记录 SHA-256，上游结果使用触发跑次的固定报告版本。切换资料库根目录后，`latest` 规则必须重新选材。

`PATCH /api/schedules/{schedule_id}` 省略 `token_budget` 时保留既有有效额度，显式 `null` 恢复内部默认 50,000；旧缺模型规则在用户主动 PATCH 且省略 `model_id` 时采用管理员默认，显式 `model_id: null` 仍返回 422。保存时保留原开关，不批量启用历史规则。

列表保留 `setup_required`、`active_run_id` 与内部配置字段，普通页面不展示技术字段。旧规则缺模型时保持待设置状态，不自动运行；用户主动保存时采用管理员默认模型。仅缺预算但已有模型的规则可使用内部默认 50,000，已有有效额度保留。同一规则只允许一个活动跑次；重复领取、执行期间修改/删除返回 `SCHEDULE_BUSY`。跑次在首次模型调用前写入 `running`，终态为 `success`、`failed`、`paused` 或 `interrupted`；只有任务 `succeeded` 才算成功。运行中 `finished_at=null`。

跑次响应新增 `input_manifest`、`upstream_run_id`、`token_budget`、`budget_used_tokens` 和 `usage`。每次模型调用（含规划与重试）先保守预留 tokens，额度不足返回 `BUDGET_EXCEEDED`，不发送该次请求；有供应商实际值后核销，未知用量保留预留值。跑次结束后的手工继续或改写由用户发起，用量计入任务，不再计入已结束跑次。

`POST /api/schedules/{schedule_id}/run-now` 立即执行；`GET .../runs` 查看历史；`GET /api/schedules/notices` 查看站内结果；`DELETE /api/schedules/{schedule_id}` 删除。

资料库使用 `GET /api/workspace`、`GET /api/workspace/entries`、`GET /api/workspace/file` 和 `POST /api/workspace/upload`；普通界面只浏览、上传和选择资料，不展示本机技术目录路径。目录配置接口 `PUT /api/workspace` 的授权根目录设置移至 `/admin`。

## 管理能力与错误

独立本机管理页 `/admin` 承载模型、技能/专家、预算、材料策略、资料库授权根目录设置与技术统计，普通导航无入口；密钥仍由 `.env` 维护，管理页不编辑或返回凭据。Webhook、密钥轮换、飞书群通知偏好和应用身份导出仍有服务端实现，没有普通用户入口。本轮仅调整展示和默认配置行为，没有新增登录或服务端角色授权；管理路由不能视为接口权限隔离。

当前注册的业务错误、HTTP 错误、参数校验和未处理异常均采用 `{ "error": { "code", "message" } }`；请求校验为 `VALIDATION_ERROR`，未分类内部异常为 `INTERNAL_ERROR`。模型错误分为 `LLM_AUTH_FAILED`、`LLM_QUOTA_EXCEEDED`、`LLM_RATE_LIMITED`、`LLM_TIMEOUT`、`LLM_NETWORK_ERROR`、`LLM_UNAVAILABLE`、`LLM_REQUEST_REJECTED`、`LLM_INVALID_RESPONSE`、`LLM_OUTPUT_TRUNCATED`；只有临时网络/超时/限流/5xx/408 最多尝试 3 次。密钥不进入错误正文或用量记录。完整配置见[模型接入与选择](模型接入与选择.md)。
