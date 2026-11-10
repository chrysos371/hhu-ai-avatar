import { test, expect } from '@playwright/test';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
const token = 'mission-control-disposable-e2e-token';
type DeliveryRow = { input: string; reply: string | null; task: unknown;
  deliveryCheck: { repair_mode?: string | null }; generationMode: string; seconds: number };

test('real task delivery keeps verbatim text across web turns', async ({ page }, info) => {
  test.skip(!process.env.AVATAR_E2E_LLM_PROVIDER || process.env.AVATAR_E2E_TASK_DELIVERY !== '1' || process.env.AVATAR_E2E_LITERAL_COMPOSITION !== '1', 'explicit real provider and task/slot opt-ins required');
  test.setTimeout(0);
  const folder = process.env.AVATAR_E2E_EVIDENCE_DIR ?? info.outputDir;
  const output = join(folder, 'real-delivery-browser.json');
  const screenshot = join(folder, 'real-delivery-browser.png');
  if (existsSync(output) || existsSync(screenshot)) throw Error('Use fresh delivery evidence paths');
  mkdirSync(folder, { recursive: true });
  await page.goto('/chat#' + token);
  const rows: DeliveryRow[] = [];
  async function say(text: string) {
    const started = Date.now();
    const accepted = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/v1/turns');
    await page.getByLabel('消息', { exact: true }).fill(text);
    await page.getByRole('button', { name: '发送消息' }).click();
    const jobId = (await (await accepted).json()).data.job_id;
    await expect(page.locator('.chat-message.assistant details')).toHaveCount(rows.length + 1, { timeout: 30000 });
    const visible = await page.locator('.chat-message.assistant > div').last().textContent();
    const job = await page.evaluate(async ({ id, auth }) => {
      const response = await fetch('/api/v1/turns/' + encodeURIComponent(id), { headers: { 'X-Avatar-Token': auth } });
      return (await response.json()).data;
    }, { id: jobId, auth: token });
    expect(job.status).toBe('completed');
    expect(visible).toBe(job.result.reply);
    expect(job.result.trace.verifier.available).toBe(false);
    rows.push({ input: text, reply: visible, task: job.result.task, deliveryCheck: job.result.delivery_check, generationMode: job.result.generation_mode, seconds: (Date.now() - started) / 1000 });
    return job.result;
  }
  const first = await say('请写一句角色台词，包含“我喜欢喝花茶”。');
  expect(first.reply).toContain('我喜欢喝花茶');
  expect(first.task.required_literals).toEqual(['我喜欢喝花茶']);
  const revision = await say('再短一点。');
  expect(revision.reply).toContain('我喜欢喝花茶');
  expect(revision.task.required_literals).toEqual(['我喜欢喝花茶']);
  const replacement = await say('改写这句台词，删掉“我喜欢喝花茶”，包含“我喜欢听雨”。');
  expect(replacement.reply).toContain('我喜欢听雨');
  expect(replacement.reply).not.toContain('我喜欢喝花茶');
  expect(replacement.task.forbidden_literals).toContain('我喜欢喝花茶');
  const comma = await say('请写一条简短消息，原样保留“时间，地点”。');
  expect(comma.reply).toContain('时间，地点');
  const reset = await say('再问个问题，什么是二进制？');
  expect(reset.task).toBeNull();
  expect(reset.reply).toContain('0'); expect(reset.reply).toContain('1');
  expect(reset.reply).not.toContain('时间，地点');
  await page.screenshot({ path: screenshot });
  writeFileSync(output, JSON.stringify({ scope: 'actual local model, HTTP/SSE/browser, five web turns and bounded history reconstruction; lexical checks only', rows, literalRepairsObserved: rows.filter(row => row.deliveryCheck.repair_mode?.startsWith('literal_')).length, semanticApproved: false }, null, 2) + '\n', { flag: 'wx' });
});
