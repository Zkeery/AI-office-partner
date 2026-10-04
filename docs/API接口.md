# API 接口与兼容说明

更新：2026-10-04。后端基址为 `http://127.0.0.1:8040`；完整机器可读定义为 `/openapi.json`，交互文档为 `/docs`。本文描述当前代码，旧阶段文档中的无模型参数示例属于历史记录。

## 模型与新建任务

`GET /api/models` 返回 `{ "items": [...] }`。每项包括 `id`、`label`、`provider`、`model`、`available`、`status`、`hint`，不返回密钥或端点。前端只显示 `available=true` 的项；服务端保留未配置项以便管理与诊断。

`POST /api/tasks` 的 `prompt` 和 `model_id` 必填，示例：

```json
{
  "prompt": "根据提供的事实整理一份工作周报。",
  "model_id": "deepseek",
  "urls": [],
  "skill_id": "weekly_report"
}
```

`prompt` 为 1–8,000 字符，`urls` 最多 3 个；`skill_id`、`expert_id` 可选。缺少/空白/未知/未配置的模型会被拒绝，不能依赖原来的全局默认模型。任务响应保存 `model_id`、`model_name`、`model_label`；老任务可能没有这些字段，前端显示历史配置。

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

`GET /api/schedules` 返回自动化列表。`POST /api/schedules` 的 `prompt`、`model_id` 必填，另可传 `name`、`interval_minutes`（默认 60）、`enabled`（默认 true）、`skill_id`、`expert_id`、`trigger_mode`（`interval` / `on_task_succeeded`）、`listen_schedule_id`。新建时固定具体型号，跑次继承；`PATCH /api/schedules/{schedule_id}` 可以明确更换模型，不能清空。

`POST /api/schedules/{schedule_id}/run-now` 立即执行；`GET .../runs` 查看历史；`GET /api/schedules/notices` 查看站内结果；`DELETE /api/schedules/{schedule_id}` 删除。

资料库使用 `GET /api/workspace`、`GET /api/workspace/entries`、`GET /api/workspace/file` 和 `POST /api/workspace/upload`。目录配置接口 `PUT /api/workspace` 属于维护能力，没有普通用户配置入口。

## 管理能力与错误

Webhook、密钥轮换、飞书群通知偏好和应用身份导出仍有服务端实现，但已从普通用户界面移除。这是展示边界，当前本机应用没有新增登录或服务端角色授权；不可把隐藏按钮理解为接口已被权限隔离。

业务错误通常采用 `{ "error": { "code", "message" } }`。参数校验也可能使用 FastAPI 的 `detail` 响应；客户端需同时处理。密钥只来自本项目服务端配置。完整配置和旧 `LLM_*` 兼容条件见[模型接入与选择](模型接入与选择.md)。
