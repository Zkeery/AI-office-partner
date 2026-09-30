# AI办公搭子 · 桌面端（Electron 壳）

用系统窗口打开本产品；后台仍是本机 8040 / 3040，数据与网页版相同。

## 使用前准备（只需做一次）

1. 项目根目录已有 `.env`（模型 / 检索 Key 按需填写）。
2. 后端虚拟环境：

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. 前端依赖：

```bash
cd frontend
npm install
```

4. 桌面壳依赖：

```bash
cd desktop
npm install
```

## 打开桌面端

```bash
cd desktop
npm start
```

看到「AI办公搭子」窗口即成功。若 8040/3040 已经在跑，会直接复用，不重复启动。

## 说明

- 默认用 `next dev` 起前端；若要生产模式：先 `cd frontend && npm run build`，再  
  `DESKTOP_FRONTEND_MODE=start npm start`
- 关掉窗口会结束**由本壳拉起**的后端/前端；若启动前服务已在跑，则不会强行关掉。
- 本阶段不做安装包 / 公证；macOS 若拦截，在系统设置里允许即可。
