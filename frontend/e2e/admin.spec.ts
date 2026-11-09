import { expect, test } from "@playwright/test";
const token = "mission-control-disposable-e2e-token";
test.beforeEach(async ({ page }) => {
  const failures: string[] = [];
  page.on("pageerror", (error) => failures.push(error.message));
  await page.goto("/#" + token);
  await expect(
    page.getByRole("heading", { name: "数字人大脑总览" }),
  ).toBeVisible();
  await expect(page.getByText("后端已连接")).toBeVisible();
  page.on("close", () => expect(failures).toEqual([]));
});
test("persona cancel, confirm, reload and reverse draft stay auditable", async ({
  page,
}) => {
  await page.getByRole("link", { name: "人设管理" }).click();
  await page.getByLabel("角色名称").fill("浏览器确认新名");
  await page.getByRole("button", { name: "生成人设草案" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "取消", exact: true }).click();
  await page.reload();
  await expect(page.getByLabel("角色名称")).not.toHaveValue("浏览器确认新名");
  await page.getByLabel("角色名称").fill("浏览器确认新名");
  await page.getByRole("button", { name: "生成人设草案" }).click();
  await page.getByRole("button", { name: "确认执行" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.reload();
  await expect(page.getByLabel("角色名称")).toHaveValue("浏览器确认新名");
  await page.getByRole("link", { name: "操作审计" }).click();
  await expect(
    page.getByRole("cell", { name: /persona.update/ }).first(),
  ).toBeVisible();
  await page.getByRole("button", { name: /详情/ }).first().click();
  await page.getByRole("button", { name: /生成反向草案 #/ }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "取消", exact: true }).click();
});
test("emotion override confirms independently of automatic state", async ({
  page,
}) => {
  await page.getByRole("link", { name: "情绪干预" }).click();
  await page.getByLabel("干预原因").fill("浏览器表达覆盖测试");
  await page.getByRole("button", { name: "生成情绪草案" }).click();
  await page.getByRole("button", { name: "确认执行" }).click();
  await expect(page.getByText(/覆盖 #/)).toBeVisible();
  await page.reload();
  await expect(page.getByText(/浏览器表达覆盖测试/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "自动状态" })).toBeVisible();
});
test("memory correction retains history and exposes source", async ({
  page,
}) => {
  await page.getByRole("link", { name: "记忆中枢" }).click();
  await page.getByRole("button", { name: "来源 #1", exact: true }).click();
  await page.getByLabel("记忆纠正内容").fill("名字：浏览器测试纠正名");
  await page.getByRole("button", { name: "生成纠错草案" }).click();
  await page.getByRole("button", { name: "确认执行" }).click();
  await expect(
    page.getByRole("cell", { name: "名字: 浏览器测试纠正名", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByLabel("包含历史版本").check();
  await expect(page.getByText(/浏览器测试原名/).first()).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("cell", { name: "名字: 浏览器测试纠正名", exact: true }),
  ).toBeVisible();
});
test("knowledge upload previews, cancel preserves sources, confirm imports; narrow layout", async ({
  page,
}) => {
  await page.getByRole("link", { name: "知识与学习" }).click();
  await page.getByRole("button", { name: "上传文件", exact: true }).click();
  await page.getByLabel("知识文件").setInputFiles({
    name: "browser.md",
    mimeType: "text/markdown",
    buffer: Buffer.from("浏览器实验室开放时间为上午九点。"),
  });
  await page.getByRole("button", { name: "解析并生成预览" }).click();
  await expect(
    page.getByRole("region", { name: "知识切片预览" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "检查导入差异" }).click();
  await page.getByRole("button", { name: "取消", exact: true }).click();
  await expect(page.getByText("尚无已确认导入的知识。")).toBeVisible();
  await page.getByRole("button", { name: "检查导入差异" }).click();
  await page.getByRole("button", { name: "确认执行" }).click();
  await expect(page.getByText("#1 browser.md", { exact: true })).toBeVisible();
  await page.getByLabel("查询内容").fill("实验室");
  await page.getByRole("button", { name: "检索", exact: true }).click();
  await expect(
    page.getByText("浏览器实验室开放时间为上午九点。", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "../data/mission-control/desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "../data/mission-control/mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});
test("all nine routes survive reload and ordinary chat exposes collapsed trace", async ({
  page,
}) => {
  for (const [path, title] of [
    ["/", "数字人大脑总览"],
    ["/chat", "对话观测"],
    ["/persona", "人设管理"],
    ["/emotion", "情绪干预"],
    ["/memory", "记忆中枢"],
    ["/knowledge", "知识与学习"],
    ["/reminders", "提醒"],
    ["/tools", "工具"],
    ["/audit", "操作审计"],
  ]) {
    await page.goto(path);
    await page.reload();
    await expect(
      page.getByRole("heading", { name: title, exact: true }),
    ).toBeVisible();
    await expect(page.getByRole("alert")).toHaveCount(0);
  }
  await page.getByRole("link", { name: "对话观测" }).click();
  await page.getByLabel("消息", { exact: true }).fill("你好");
  await page.getByRole("button", { name: "发送消息" }).click();
  await expect(page.getByText("本轮决策与来源")).toBeVisible();
  await expect(page.locator("details")).not.toHaveAttribute("open");
  await page.getByRole("link", { name: "总览", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "最近管理操作" }),
  ).toBeVisible();
  await page.screenshot({
    path: "../data/mission-control/dashboard.png",
    fullPage: true,
  });
});
