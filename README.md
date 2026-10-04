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

模型由用户在任务或自动化表单中明确选择，首批 DeepSeek、GPT、通义千问、豆包；待配置项不能提交。配置方法与 API 必填字段见 [模型接入与选择](docs/模型接入与选择.md)。

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
- 任务：按实际工具执行并记录结果依据；失败步骤、跳过原因与续跑状态可见
- 表格分析：完整读取 CSV/XLSX 的全部工作表，程序计算汇总、分组、月度同比环比和异常，展示真实图表
- 成品：导出 Word/Excel/PPT/Markdown；Excel 包含明细、复算公式和原生图表，PPT 包含可编辑图表与分页正文
- 报告修改：按章节或全文改写，查看版本差异、恢复旧版，冲突时阻止覆盖；合并、搜索、自动归档继续可用
- 自动化：按小时/天/周或自定义间隔执行，可查看跑次与失败
- 飞书：任务成功后导出到「我的」云文档（需用户 OAuth）

### 表格分析与报告版本

在「数据 → 表格分析」上传材料并确认执行，完成后可切换工作表、查看图表数值和月度变化。报告下方「修改内容」可选章节或全文；「版本记录」可查看差异并恢复，恢复会另存新版本。

每次分析上限为 100,000 行、1,000,000 个数据单元格、50 张工作表、每表 512 列。每表第一条非空行作为表头，全空行忽略；超限明确报错。XLSX 的公式需先在 Excel 等软件中计算并保存，缺少缓存结果时不会按零值处理。只支持 CSV/XLSX，不执行上传表格里的公式或宏。

数值计算排除空值和非法数字，离群值保留。比例和单价类字段使用未加权均值，不能替代基于原始分子、分母的整体指标。每表自动选择一个主要指标；页面柱图展示前 12 个分组，折线展示最近 24 个有数据月份；完整计算结果与明细在 Excel 中。异常示例每表最多 100 条，并单独显示异常总数。

Excel 中的公式可复算原始明细，图表与报告是分析时的快照；修改明细后需重新上传分析。首次读取旧报告会自动建立版本记录；版本存入本机数据库，重启后保留。

前端检查：在 `frontend/` 运行 `npm run typecheck`、`npm run lint`、`npm run build`。

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
