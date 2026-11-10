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
test("all eleven routes survive reload and ordinary chat exposes collapsed trace", async ({
  page,
}) => {
  for (const [path, title] of [
    ["/", "数字人大脑总览"],
    ["/chat", "对话观测"],
    ["/persona", "人设管理"],
    ["/emotion", "情绪干预"],
    ["/memory", "记忆中枢"],
    ["/qq", "QQ 会话管理"],
    ["/characters", "角色馆"],
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
test("QQ memory correction is confirmed, audited and isolated from another account", async ({ page }) => {
  await page.getByRole('link', { name: 'QQ 会话' }).click();
  await expect(page.getByRole('heading', { name: 'QQ 会话管理' })).toBeVisible();
  const select = page.getByLabel('选择 QQ 会话');
  await select.selectOption({ label: '私聊 23456' });
  await page.getByRole('button', { name: /\[active\] 名字: 浏览器QQ原名/ }).click();
  await page.getByLabel('纠正后的事实').fill('浏览器QQ新名');
  await page.getByRole('button', { name: '预览纠错' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button', { name: '取消', exact: true }).click();
  await expect(page.getByRole('button', { name: /\[active\] 名字: 浏览器QQ原名/ })).toBeVisible();
  await page.getByRole('button', { name: '预览纠错' }).click();
  await page.getByRole('button', { name: '确认执行' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByRole('button', { name: /\[active\] 名字: 浏览器QQ新名/ })).toBeVisible();
  await expect(page.getByText(/memory.batch · success/)).toBeVisible();
  await select.selectOption({ label: '私聊 34567' });
  await expect(page.getByRole('button', { name: /\[active\] 名字: 其他QQ原名/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /\[active\] 名字: 浏览器QQ新名/ })).toHaveCount(0);
});
test("character switching keeps separate conversations and persona changes require confirmation", async ({ page }) => {
  await page.getByRole('link', {name:'角色馆'}).click();
  await expect(page.getByRole('heading',{name:'角色馆',exact:true})).toBeVisible();
  await page.getByLabel('发给当前角色').fill('我叫浏览器角色用户');
  await page.getByRole('button',{name:'发送',exact:true}).click();
  await expect(page.getByText('这是当前角色的离线测试回复。')).toBeVisible();
  await page.getByRole('button',{name:/GPT · 白龙娘/}).click();
  await expect(page.getByText('我叫浏览器角色用户')).toHaveCount(0);
  await page.getByRole('button',{name:/DeepSeek · 鲸鱼娘/}).click();
  await expect(page.getByText('我叫浏览器角色用户')).toBeVisible();
  await page.getByText(/编辑这个角色的人设/).click();
  await page.getByLabel('角色称呼').fill('浏览器鲸鱼');
  await page.getByRole('button',{name:'预览人设修改'}).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button',{name:'取消',exact:true}).click();
  await expect(page.getByRole('heading',{name:'鲸鱼娘',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'预览人设修改'}).click();
  await page.getByRole('button',{name:'确认执行'}).click();
  await expect(page.getByRole('heading',{name:'浏览器鲸鱼',exact:true})).toBeVisible();
  await page.getByRole('button',{name:/GPT · 白龙娘/}).click();
  await expect(page.getByRole('heading',{name:'白龙娘',exact:true})).toBeVisible();
});
test('shared facts are opt-in, revocable and undoable from the character gallery', async ({page})=>{
  await page.getByRole('link',{name:'角色馆'}).click();
  await page.getByText('管理跨角色共享事实',{exact:true}).click();
  await page.getByLabel('事实类型').selectOption('diet');
  await page.getByLabel('共享内容',{exact:true}).fill('浏览器测试：不吃花生');
  await page.getByRole('checkbox',{name:'GPT · 白龙娘',exact:true}).check();
  await page.getByRole('button',{name:'保存共享事实',exact:true}).click();
  await expect(page.getByText('浏览器测试：不吃花生 · GPT · 白龙娘',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'撤销共享',exact:true}).click();
  await expect(page.getByText('浏览器测试：不吃花生 · GPT · 白龙娘',{exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'撤回最近一次事实操作',exact:true}).click();
  await expect(page.getByText('浏览器测试：不吃花生 · GPT · 白龙娘',{exact:true})).toBeVisible();
  await page.getByText('模型配置',{exact:true}).click();
  await expect(page.getByLabel('当前角色使用的模型')).toHaveValue('default');
  await page.getByLabel('当前角色使用的模型').selectOption('default');
  await page.getByRole('button',{name:'应用模型',exact:true}).click();
  await expect(page.getByRole('button',{name:'应用模型',exact:true})).toBeDisabled();
});
