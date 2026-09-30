# AI办公搭子

本机单用户 MVP：写作/任务、资料库、自动化调度，以及飞书导出到「我的」云文档。

> **定位**：当前面向本机开发与自用，**不是**完整的 Vercel 一键部署方案。前端可单独静态/SSR 托管，但后端（FastAPI + 本地数据目录）需另行托管后才能上云。

## 技术栈

| 层 | 技术 |
| --- | --- |
| 前端 | Next.js 14、React 18、Tailwind CSS（开发端口 **3040**） |
| 后端 | FastAPI、SQLAlchemy、Uvicorn（开发端口 **8040**） |
| 桌面壳（可选） | Electron（复用本机 8040/3040） |
| 集成 | 大模型 API、Tavily 检索（可选）、飞书开放平台（导出 / 可选群通知） |

## 本机启动

### 1. 依赖

- Python 3.12+
- Node.js 18+（含 npm）
- （可选）本机已安装桌面端依赖时可用 Electron 壳

### 2. 配置

```bash
cp .env.example .env
```

默认 `LLM_MOCK=1`、`SEARCH_MOCK=1`、`FEISHU_MOCK=1`，不配真实 Key 也能跑通工程路径。  
真实验收时将对应 `*_MOCK=0`，并在 `.env` 中填写自己的密钥（**不要提交 `.env`**）。

### 3. 后端（8040）

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8040 --reload
```

健康检查：打开 [http://127.0.0.1:8040/health](http://127.0.0.1:8040/health) 应看到 `{"status":"ok",...}`。

> 请在 `backend/` 目录启动，以便 `.env` 中 `DATA_DIR=./data` 落到 `backend/data/`（任务库、上传、飞书 token 等运行时文件，已由 `.gitignore` 忽略）。

### 4. 前端（3040）

另开终端：

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 [http://127.0.0.1:3040](http://127.0.0.1:3040)。

### 5. 桌面端（可选）

需已装好 backend 虚拟环境与 frontend 依赖：

```bash
cd desktop
npm install
npm start
```

说明见 [desktop/README.md](desktop/README.md)。

### 6. 测试

```bash
cd backend
source .venv/bin/activate
pytest -q
```

## 端口

| 服务 | 端口 |
| --- | --- |
| 后端 | 8040 |
| 前端 | 3040 |

## 飞书相关

1. 在[飞书开放平台](https://open.feishu.cn/)**自建应用**，取得 App ID / App Secret，写入本机 `.env`（勿提交仓库）。
2. 用户授权导出（导出到「我的」云文档）需配置重定向 URL，且与配置完全一致：
   - `http://127.0.0.1:8040/api/feishu/oauth/callback`
3. 建议为用户身份开通的 scopes：
   - `offline_access`
   - `drive:drive`
   - `docx:document`
4. **群通知默认关闭**（`FEISHU_NOTIFY_ON=off`）；需要时再在本机配置或 UI 中打开，chat_id 仅保存在本机。

Mock 模式下可不配飞书凭证，用本地模拟导出链路。

## 功能速览

- 场景卡：竞品调研、会议纪要、周报、邮件稿、方案模板、表格分析等
- 能力货架：技能 / 专家浏览与选用
- 任务：生成成品、导出 Word/Excel/Markdown、合并、搜索、自动归档
- 自动化：按小时/天/周或自定义间隔执行，可查看跑次与失败
- 飞书：任务成功后导出到「我的」云文档（需用户 OAuth）

## 文档

- 需求：[docs/PRD/](docs/PRD/)
- 进度：[docs/项目状态.md](docs/项目状态.md)
- 阶段与架构说明：[docs/阶段文档/](docs/阶段文档/)
- 上线暂缓说明：[docs/阶段文档/上线方案摘要-暂缓.md](docs/阶段文档/上线方案摘要-暂缓.md)

## 安全提示

- 密钥只放本机 `.env`，仓库仅保留 `.env.example` 占位符。
- `backend/data/`、OAuth token、通知偏好、数据库等运行时文件不应进入版本库。
- 页面会提示：任务内容会发给当前配置的模型厂商做推理。
- 若密钥曾泄露到聊天或不信任环境，请到对应控制台轮换。
