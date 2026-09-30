const { app, BrowserWindow, shell } = require("electron");
const { spawn } = require("child_process");
const http = require("http");
const path = require("path");
const fs = require("fs");

const PROJECT_ROOT = path.resolve(__dirname, "..");
const BACKEND_DIR = path.join(PROJECT_ROOT, "backend");
const FRONTEND_DIR = path.join(PROJECT_ROOT, "frontend");
const BACKEND_URL = "http://127.0.0.1:8040";
const FRONTEND_URL = "http://127.0.0.1:3040";
const HEALTH_URL = `${BACKEND_URL}/health`;

/** @type {import('child_process').ChildProcess[]} */
const children = [];
let backendStartedByUs = false;
let frontendStartedByUs = false;

function httpOk(url, timeoutMs = 1500) {
  return new Promise((resolve) => {
    const req = http.get(url, (res) => {
      res.resume();
      resolve(res.statusCode >= 200 && res.statusCode < 500);
    });
    req.on("error", () => resolve(false));
    req.setTimeout(timeoutMs, () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function waitFor(url, attempts = 60, gapMs = 500) {
  for (let i = 0; i < attempts; i++) {
    if (await httpOk(url)) return true;
    await new Promise((r) => setTimeout(r, gapMs));
  }
  return false;
}

function resolvePython() {
  const candidates =
    process.platform === "win32"
      ? [
          path.join(BACKEND_DIR, ".venv", "Scripts", "python.exe"),
          "python",
        ]
      : [
          path.join(BACKEND_DIR, ".venv", "bin", "python"),
          path.join(BACKEND_DIR, ".venv", "bin", "python3"),
          "python3.12",
          "python3",
        ];
  for (const c of candidates) {
    if (c.includes(path.sep) && !fs.existsSync(c)) continue;
    return c;
  }
  return process.platform === "win32" ? "python" : "python3";
}

function spawnLogged(command, args, cwd, label) {
  const child = spawn(command, args, {
    cwd,
    env: { ...process.env },
    stdio: ["ignore", "pipe", "pipe"],
  });
  child.stdout.on("data", (buf) => {
    process.stdout.write(`[${label}] ${buf}`);
  });
  child.stderr.on("data", (buf) => {
    process.stderr.write(`[${label}] ${buf}`);
  });
  child.on("exit", (code, signal) => {
    console.log(`[${label}] exited code=${code} signal=${signal}`);
  });
  children.push(child);
  return child;
}

async function ensureBackend() {
  if (await httpOk(HEALTH_URL)) {
    console.log("[desktop] backend already up");
    return;
  }
  const py = resolvePython();
  console.log("[desktop] starting backend with", py);
  spawnLogged(
    py,
    ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8040"],
    BACKEND_DIR,
    "backend"
  );
  backendStartedByUs = true;
  const ok = await waitFor(HEALTH_URL);
  if (!ok) {
    throw new Error("后端未能在超时内就绪（8040）。请检查 backend/.venv 与 .env。");
  }
}

async function ensureFrontend() {
  if (await httpOk(FRONTEND_URL)) {
    console.log("[desktop] frontend already up");
    return;
  }
  const npmCmd = process.platform === "win32" ? "npm.cmd" : "npm";
  const mode = (process.env.DESKTOP_FRONTEND_MODE || "dev").toLowerCase();
  const script = mode === "start" ? "start" : "dev";
  console.log("[desktop] starting frontend npm run", script);
  spawnLogged(npmCmd, ["run", script], FRONTEND_DIR, "frontend");
  frontendStartedByUs = true;
  const ok = await waitFor(FRONTEND_URL, 90, 700);
  if (!ok) {
    throw new Error("前端未能在超时内就绪（3040）。请先在 frontend 执行 npm install。");
  }
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 840,
    minWidth: 960,
    minHeight: 640,
    title: "AI办公搭子",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  win.loadURL(FRONTEND_URL);
  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });
}

function stopChildrenWeStarted() {
  for (const child of children) {
    if (!child.killed) {
      try {
        if (process.platform === "win32") {
          spawn("taskkill", ["/pid", String(child.pid), "/f", "/t"]);
        } else {
          child.kill("SIGTERM");
        }
      } catch (_) {
        /* ignore */
      }
    }
  }
  if (!backendStartedByUs && !frontendStartedByUs) {
    console.log("[desktop] reused external servers; not stopping them");
  }
}

app.whenReady().then(async () => {
  try {
    await ensureBackend();
    await ensureFrontend();
    createWindow();
  } catch (err) {
    console.error(err);
    const { dialog } = require("electron");
    dialog.showErrorBox("AI办公搭子启动失败", String(err.message || err));
    app.quit();
  }
});

app.on("window-all-closed", () => {
  stopChildrenWeStarted();
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  stopChildrenWeStarted();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});
