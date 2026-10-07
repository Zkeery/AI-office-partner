import { expect, test } from "@playwright/test";

test("user workflow hides internal configuration while admin retains it", async ({ page, request }) => {
  const browserErrors: string[] = [];
  page.on("pageerror", error => browserErrors.push(error.message));
  await page.goto("/");
  await expect(page.getByRole("button", { name: "选择模型", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "能力货架", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Open Next.js Dev Tools", exact: true })).toHaveCount(0);
  await page.goto("/?panel=schedules");
  await page.getByRole("button", { name: "+ 添加自动化", exact: true }).click();
  await expect(page.getByPlaceholder("例如 50000")).toHaveCount(0);
  await expect(page.getByText("运行模型（必选）", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("combobox", { name: "技能（可选）", exact: true })).toHaveCount(0);
  await expect(page.getByRole("combobox", { name: "专家（可选）", exact: true })).toHaveCount(0);
  await expect(page.getByRole("combobox", { name: "资料读取方式", exact: true })).toHaveCount(0);

  const api = "http://127.0.0.1:8141";
  const response = await request.post(`${api}/api/schedules`, {
    data: { name: "管理配置隔离回归", prompt: "整理工作周报", interval_minutes: 10080 },
  });
  expect(response.ok()).toBeTruthy();
  const schedule = await response.json();
  try {
    await page.goto("/admin");
    await expect(page.getByRole("heading", { name: "管理工作台", exact: true })).toBeVisible();
    await expect(page.getByText("50,000 tokens", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "自动化配置", exact: true }).click();
    await page.getByText("管理配置隔离回归", { exact: true }).locator("..").locator("..").getByRole("button", { name: "管理配置", exact: true }).click();
    await expect(page.getByText("运行模型（必选）", { exact: true })).toBeVisible();
    await expect(page.getByPlaceholder("例如 50000")).toHaveValue("50000");
    await expect(page.getByRole("combobox", { name: "技能（可选）", exact: true })).toBeVisible();
    await expect(page.getByRole("combobox", { name: "专家（可选）", exact: true })).toBeVisible();
    await expect(page.getByRole("combobox", { name: "资料读取方式", exact: true })).toBeVisible();
    expect(browserErrors).toEqual([]);
  } finally {
    await request.delete(`${api}/api/schedules/${schedule.id}`);
  }
});
