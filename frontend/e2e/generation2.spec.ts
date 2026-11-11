import { expect, test, type Page } from "@playwright/test";
const token = "mission-control-disposable-e2e-token";
test.beforeEach(async ({ page }) => {
  await page.goto("/chat#" + token);
  await expect(page.getByRole("heading", { name: "对话观测", exact: true })).toBeVisible();
  await expect(page.locator('.chat-history')).toHaveAttribute('data-history-ready', 'true');
});
async function begin(page: Page) {
  await page.getByLabel("消息", { exact: true }).fill("请解释云为什么会移动，fixture-long");
  const submission = page.waitForRequest(request => request.url().endsWith('/api/v1/turns') && request.method() === 'POST');
  await page.getByRole('button', { name: '发送消息' }).click();
  return (await submission).postDataJSON().request_id as string;
}
test('checked draft appears before completion and interruption stops the job', async ({ page }) => {
  const before = await page.locator('.chat-message.assistant details').count();
  const id = await begin(page);
  await expect(page.locator('.chat-message.assistant > div').last()).toContainText('云并不是');
  await expect(page.getByText('正在生成；最终回复会完成检查后替换此草稿。')).toBeVisible();
  await page.getByRole('button', { name: '停止生成' }).click();
  await expect(page.getByText('已停止，未完成的助手内容不存入记忆。')).toBeVisible();
  await expect.poll(async () => {
    const response = await page.request.get('/api/v1/turns/' + id, { headers: { 'X-Avatar-Token': token } });
    return (await response.json()).data.status;
  }).toBe('cancelled');
  await expect(page.locator('.chat-message.assistant details')).toHaveCount(before);
});
test('automatic speech is segmented and stopping it does not start the next part', async ({ page }) => {
  await page.getByLabel('自动分段朗读新回复').check();
  await begin(page);
  await expect(page.getByText(/语音片段 1 \/ [2-9]/)).toBeVisible({ timeout: 15000 });
  const audio = page.getByLabel(/语音播放器$/);
  await expect.poll(() => audio.evaluate((element: HTMLAudioElement) => element.currentTime)).toBeGreaterThan(0.05);
  await page.getByRole('button', { name: '停止播放', exact: true }).click();
  await expect(audio).not.toHaveAttribute('src');
  await expect(page.locator('.avatar-stage')).toHaveAttribute('data-mouth-open', '0.000');
  await expect(page.getByText(/语音片段/)).toHaveCount(0);
});
test('microphone input interrupts generation before recording', async ({ page, context }) => {
  await context.grantPermissions(['microphone']);
  const id = await begin(page);
  await page.getByRole('button', { name: '麦克风输入' }).click();
  await expect(page.getByText('正在录音，最长 60 秒…')).toBeVisible();
  await expect.poll(async () => {
    const response = await page.request.get('/api/v1/turns/' + id, { headers: { 'X-Avatar-Token': token } });
    return (await response.json()).data.status;
  }).toBe('cancelled');
  await page.getByRole('button', { name: '取消语音输入' }).click();
  await expect(page.getByLabel('消息', { exact: true })).toHaveValue('');
});
