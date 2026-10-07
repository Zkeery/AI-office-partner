import { expect, test, type Page } from "@playwright/test";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";

async function expectSimpleComposer(page: Page) {
  await expect(page.getByRole("button", { name: /选择模型/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /能力货架/ })).toHaveCount(0);
  await expect(page.getByLabel("语音输入尚未接入")).toHaveCount(0);
}

test("remove CSV, generate a normal report, rewrite, restore and download", async ({ page }) => {
  const browserErrors: string[] = [];
  page.on("pageerror", error => browserErrors.push(error.message));
  await page.goto("/");
  await page.getByLabel("上传任务材料").setInputFiles({ name: "sales.csv", mimeType: "text/csv", buffer: Buffer.from("产品,销量\nA,11\n") });
  await page.getByRole("button", { name: "移除 sales.csv", exact: true }).click();
  await page.getByLabel("告诉搭子你想做什么").fill("根据这些事实整理工作周报：已完成两份方案，下周评审。");
  await expectSimpleComposer(page);
  const createRequest = page.waitForRequest(request => request.method() === "POST" && /\/api\/tasks$/.test(request.url()));
  await page.getByRole("button", { name: "发送任务", exact: true }).click();
  expect(Object.keys((await createRequest).postDataJSON()).sort()).toEqual(["prompt", "urls"]);
  await expect(page.getByText("当前 v1", { exact: true })).toBeVisible();
  await expect(page.getByText(/本次模型：|供应商返回.*tokens|用量未知/)).toHaveCount(0);
  await expect(page.getByText(/表格分析请先上传/)).toHaveCount(0);
  await page.getByRole("button", { name: "修改内容", exact: true }).click();
  await page.getByPlaceholder("例如：把这节压缩成三条建议，保留数字和来源").fill("精简表达，保留事实。");
  await page.getByRole("button", { name: "保存为新版本", exact: true }).click();
  await expect(page.getByText("当前 v2", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "版本记录", exact: true }).click();
  await page.getByRole("combobox", { name: "选择版本", exact: true }).selectOption("1");
  await page.getByRole("button", { name: "恢复此版（保留现有版本）", exact: true }).click();
  await expect(page.getByText("当前 v3", { exact: true })).toBeVisible();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "下载·Markdown", exact: true }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/\.md$/);
  expect(await download.failure()).toBeNull();
  expect(browserErrors).toEqual([]);
});

test("table analysis still reads real rows and exports a workbook", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("上传任务材料").setInputFiles({ name: "sales.csv", mimeType: "text/csv", buffer: Buffer.from("产品,销量\nA,11\nB,22\nC,33\n") });
  await page.getByLabel("告诉搭子你想做什么").fill("分析销量表，核对三行数据总数和总销量。");
  await expectSimpleComposer(page);
  await page.getByRole("button", { name: "发送任务", exact: true }).click();
  await expect(page.getByRole("region", { name: "完整数据分析" })).toBeVisible();
  await expect(page.getByRole("region", { name: "完整数据分析" })).toContainText("66");
  await page.getByRole("button", { name: "Excel", exact: true }).click();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "下载·Excel", exact: true }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/\.xlsx$/);
  expect(await download.failure()).toBeNull();
});

test("explicit table scene still prevents running without a table", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "分析表格", exact: true }).click();
  await expectSimpleComposer(page);
  await page.getByRole("button", { name: "发送任务", exact: true }).click();
  await expect(page.getByText("表格分析请先上传 CSV/Excel，或从资料库选一张表。", { exact: true })).toBeVisible();
});

test("automation creates and edits without technical settings and shows a completed run", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "自动化", exact: true }).click();
  await page.getByRole("button", { name: "+ 添加自动化", exact: true }).click();
  await page.getByLabel("名称", { exact: true }).fill("浏览器回归自动化");
  await page.getByLabel("自动执行内容", { exact: true }).fill("整理本周完成事项与下周计划。");
  await expect(page.getByLabel("参考链接（每行一条，最多 3 条）", { exact: true })).not.toBeVisible();
  await expect(page.getByText("资料库 / 根目录", { exact: true })).not.toBeVisible();
  await expect(page.getByRole("button", { name: /选择模型/ })).toHaveCount(0);
  await expect(page.getByRole("spinbutton", { name: /token/ })).toHaveCount(0);
  await expect(page.getByLabel("技能（可选）")).toHaveCount(0);
  await expect(page.getByLabel("专家（可选）")).toHaveCount(0);
  await expect(page.getByLabel("资料读取方式")).toHaveCount(0);
  await expect(page.getByRole("spinbutton")).toHaveCount(0);
  await page.getByRole("button", { name: "每天", exact: true }).click();
  await expect(page.getByRole("spinbutton")).toHaveCount(0);
  await page.getByRole("button", { name: "自定义", exact: true }).click();
  await page.getByLabel("执行间隔（分钟）", { exact: true }).fill("90");
  const createRequest = page.waitForRequest(request => request.method() === "POST" && /\/api\/schedules$/.test(request.url()));
  await page.getByRole("button", { name: "创建自动化", exact: true }).click();
  const createdRequest = await createRequest;
  expect(Object.keys(createdRequest.postDataJSON()).sort()).toEqual(["interval_minutes", "name", "prompt", "urls", "workspace_paths"]);
  const row = page.getByRole("row").filter({ hasText: "浏览器回归自动化" });
  await expect(row).toBeVisible();
  const createdResponse = await createdRequest.response();
  const original = await createdResponse!.json();
  expect(original.interval_minutes).toBe(90);
  await row.getByRole("button", { name: "编辑", exact: true }).click();
  await expect(page.getByRole("spinbutton", { name: /token/ })).toHaveCount(0);
  await expect(page.getByLabel("执行间隔（分钟）", { exact: true })).toHaveValue("90");
  await page.getByLabel("自动执行内容", { exact: true }).fill("整理本周完成事项与下周重点计划。");
  const patchRequest = page.waitForRequest(request => request.method() === "PATCH" && request.url().endsWith(`/api/schedules/${original.id}`));
  await page.getByRole("button", { name: "保存自动化", exact: true }).click();
  const patchedRequest = await patchRequest;
  expect(Object.keys(patchedRequest.postDataJSON()).sort()).toEqual(["interval_minutes", "name", "prompt", "urls", "workspace_paths"]);
  await expect(row).toBeVisible();
  const updated = await (await patchedRequest.response())!.json();
  for (const field of ["enabled", "model_id", "token_budget", "skill_id", "expert_id", "trigger_mode", "listen_schedule_id", "material_mode", "include_upstream_result"]) {
    expect(updated[field]).toEqual(original[field]);
  }
  await row.getByRole("button", { name: "立即跑", exact: true }).click();
  await expect(page.getByText("当前 v1", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "自动化", exact: true }).click();
  await row.getByRole("button", { name: "跑次历史", exact: true }).click();
  await expect(page.getByText("成功", { exact: true })).toBeVisible();
  await expect(page.getByText(/已用\/预留|tokens|用量未知/)).toHaveCount(0);
});

test("cost confirmation still offers a readable message and an explicit continue action", async ({ page }) => {
  let firstConfirm = true;
  await page.route("**/api/tasks/*/confirm", async route => {
    if (firstConfirm) {
      firstConfirm = false;
      await route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ error: { code: "COST_CONFIRM_REQUIRED", message: "本次费用需要确认后才能继续。" } }) });
    } else await route.continue();
  });
  await page.goto("/");
  await page.getByLabel("告诉搭子你想做什么").fill("根据以下事实整理周报：完成两份方案。");
  await page.getByRole("button", { name: "发送任务", exact: true }).click();
  await expect(page.getByText("本次费用需要确认后才能继续。", { exact: false })).toBeVisible();
  await expect(page.getByText(/COST_CONFIRM_REQUIRED/)).toHaveCount(0);
  await page.getByRole("button", { name: "确认费用并继续", exact: true }).click();
  await expect(page.getByText("当前 v1", { exact: true })).toBeVisible();
});

test("ordinary editing preserves an existing dependency and its material strategy", async ({ page, request }) => {
  const api = "http://127.0.0.1:8141/api/schedules";
  const upstreamResponse = await request.post(api, { data: { name: "依赖回归上游", prompt: "整理周报", interval_minutes: 60, enabled: false } });
  expect(upstreamResponse.ok()).toBeTruthy();
  const upstream = await upstreamResponse.json();
  let downstreamId = "";
  try {
    const response = await request.post(api, { data: { name: "依赖回归自动化", prompt: "汇总上游成果", interval_minutes: 60, enabled: false, trigger_mode: "on_task_succeeded", listen_schedule_id: upstream.id, material_mode: "latest", include_upstream_result: true, token_budget: 80000 } });
    expect(response.ok()).toBeTruthy();
    const original = await response.json();
    downstreamId = original.id;
    await page.goto("/?panel=schedules");
    const row = page.getByRole("row").filter({ hasText: "依赖回归自动化" });
    await row.getByRole("button", { name: "编辑", exact: true }).click();
    await expect(page.getByText("执行时间：在“依赖回归上游”完成后运行。", { exact: true })).toBeVisible();
    await expect(page.getByLabel("资料读取方式")).toHaveCount(0);
    await expect(page.getByRole("checkbox")).toHaveCount(0);
    await page.getByLabel("自动执行内容", { exact: true }).fill("重新汇总上游成果，保留来源。");
    const savedResponse = page.waitForResponse(response => response.request().method() === "PATCH" && response.url().endsWith(`/api/schedules/${downstreamId}`));
    await page.getByRole("button", { name: "保存自动化", exact: true }).click();
    const saved = await savedResponse;
    expect(saved.ok()).toBeTruthy();
    const updated = await saved.json();
    for (const field of ["enabled", "model_id", "token_budget", "trigger_mode", "listen_schedule_id", "material_mode", "include_upstream_result"]) {
      expect(updated[field]).toEqual(original[field]);
    }
  } finally {
    if (downstreamId) await request.delete(`${api}/${downstreamId}`);
    await request.delete(`${api}/${upstream.id}`);
  }
});

test("warm home and navigation fit a mobile viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByLabel("告诉搭子你想做什么")).toBeVisible();
  const width = await page.evaluate(() => ({ client: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
  expect(width.scroll).toBeLessThanOrEqual(width.client);
  await page.getByRole("button", { name: "打开导航", exact: true }).click();
  await page.getByRole("button", { name: "我的任务", exact: true }).click();
  await expect(page.getByLabel("搜索任务列表")).toBeVisible();
});

test("automation materials stay collapsed and survive creation and editing", async ({ page, request }) => {
  const api = "http://127.0.0.1:8141/api";
  const workspace = mkdtempSync(path.resolve(process.cwd(), "../.runtime/e2e-materials-"));
  writeFileSync(path.join(workspace, "facts.csv"), "事项,数量\n方案,2\n", "utf8");
  let scheduleId = "";
  try {
    const configured = await request.put(`${api}/workspace`, { data: { root: workspace } });
    expect(configured.ok()).toBeTruthy();
    await page.goto("/?panel=schedules");
    await page.getByRole("button", { name: "+ 添加自动化", exact: true }).click();
    await page.getByLabel("名称", { exact: true }).fill("材料折叠回归自动化");
    await page.getByLabel("自动执行内容", { exact: true }).fill("根据所选资料整理周报。");
    await page.getByRole("button", { name: "每周", exact: true }).click();
    const materials = page.getByRole("group", { name: "执行材料", exact: true });
    const links = materials.getByLabel("参考链接（每行一条，最多 3 条）", { exact: true });
    await expect(links).not.toBeVisible();
    await materials.locator("summary").click();
    await links.fill("https://example.com/first");
    await materials.getByRole("button", { name: "选择：facts.csv", exact: true }).click();
    await materials.locator("summary").click();
    await expect(materials.locator("summary")).toContainText("已选 1 份资料 · 1 个链接");
    await expect(links).not.toBeVisible();
    const creation = page.waitForResponse(response => response.request().method() === "POST" && response.url().endsWith("/api/schedules"));
    await page.getByRole("button", { name: "创建自动化", exact: true }).click();
    const created = await creation;
    expect(created.ok()).toBeTruthy();
    const original = await created.json();
    scheduleId = original.id;
    expect(original.workspace_paths).toEqual(["facts.csv"]);
    expect(original.urls).toEqual(["https://example.com/first"]);
    const row = page.getByRole("row").filter({ hasText: "材料折叠回归自动化" });
    await row.getByRole("button", { name: "编辑", exact: true }).click();
    await expect(materials.locator("summary")).toContainText("已选 1 份资料 · 1 个链接");
    await expect(links).not.toBeVisible();
    await materials.locator("summary").click();
    await expect(links).toHaveValue("https://example.com/first");
    await expect(materials.getByRole("button", { name: "移除 facts.csv", exact: true })).toBeVisible();
    await links.fill("https://example.com/updated");
    await materials.locator("summary").click();
    const saving = page.waitForResponse(response => response.request().method() === "PATCH" && response.url().endsWith(`/api/schedules/${scheduleId}`));
    await page.getByRole("button", { name: "保存自动化", exact: true }).click();
    const saved = await saving;
    expect(saved.ok()).toBeTruthy();
    const updated = await saved.json();
    expect(updated.workspace_paths).toEqual(original.workspace_paths);
    expect(updated.urls).toEqual(["https://example.com/updated"]);
    expect(updated.material_mode).toEqual(original.material_mode);
    expect(updated.enabled).toEqual(original.enabled);
  } finally {
    if (scheduleId) await request.delete(`${api}/schedules/${scheduleId}`);
    rmSync(workspace, { recursive: true });
  }
});
