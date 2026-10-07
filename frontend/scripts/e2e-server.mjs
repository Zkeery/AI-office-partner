import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const project = path.dirname(frontend);
const runtime = path.join(project, ".runtime");
mkdirSync(runtime, { recursive: true });
const data = mkdtempSync(path.join(runtime, "e2e-"));
const nextEnvPath = path.join(frontend, "next-env.d.ts");
const originalNextEnv = readFileSync(nextEnvPath, "utf8");
const children = [];
const env = { ...process.env, DATA_DIR: data, LLM_MOCK: "1", SEARCH_MOCK: "1", FEISHU_MOCK: "1",
  LLM_API_KEY: "", DEEPSEEK_API_KEY: "", OPENAI_API_KEY: "", QWEN_API_KEY: "", DOUBAO_API_KEY: "", TAVILY_API_KEY: "",
  FEISHU_APP_ID: "", FEISHU_APP_SECRET: "", FEISHU_NOTIFY_ON: "off", LOCAL_WORKSPACE_ROOT: "",
  FRONTEND_ORIGIN: "http://127.0.0.1:3141", APP_PORT: "8141", NEXT_PUBLIC_API_BASE: "http://127.0.0.1:8141", NEXT_DIST_DIR: ".next-e2e",
};
function start(command, args, cwd) {
  const child = spawn(command, args, { cwd, env, stdio: "inherit" });
  children.push(child);
  child.on("error", error => { console.error(error.message); stop(1); });
  return child;
}
let stopping = false;
async function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  await Promise.all(children.filter(child => child.exitCode === null && child.signalCode === null).map(child => new Promise(resolve => {
    child.once("exit", resolve);
    child.kill("SIGTERM");
    const timer = setTimeout(() => { child.kill("SIGKILL"); resolve(); }, 5000);
    timer.unref();
  })));
  rmSync(data, { recursive: true, force: true });
  writeFileSync(nextEnvPath, originalNextEnv);
  process.exit(code);
}
process.on("SIGTERM", () => stop());
process.on("SIGINT", () => stop());
const python = process.env.E2E_PYTHON || path.join(project, "backend/.venv/bin/python");
const backend = start(python, ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8141", "--no-access-log"], path.join(project, "backend"));
backend.on("exit", code => { if (!stopping) void stop(code || 1); });
const build = start(process.execPath, ["node_modules/next/dist/bin/next", "build"], frontend);
build.on("exit", code => {
  if (stopping) return;
  if (code !== 0) { void stop(code || 1); return; }
  const server = start(process.execPath, ["node_modules/next/dist/bin/next", "start", "-H", "127.0.0.1", "-p", "3141"], frontend);
  server.on("exit", result => { if (!stopping) void stop(result || 1); });
});
