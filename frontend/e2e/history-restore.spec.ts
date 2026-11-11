import { test, expect } from '@playwright/test';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const token = 'mission-control-disposable-e2e-token';
const hash = (p: string) => createHash('sha256').update(readFileSync(p)).digest('hex');
test('restores paginated source history and blocks cancelled and erased content across tabs', async ({ page, context }, info) => {
  test.skip(process.env.AVATAR_E2E_RESTORE_AUDIT !== '1', 'explicit durable-history research opt-in');
  test.setTimeout(0);
  const folder = process.env.AVATAR_E2E_EVIDENCE_DIR ?? info.outputDir; mkdirSync(folder, { recursive: true });
  const file = join(folder, 'restore.json'); if (existsSync(file)) throw Error('Use fresh restore evidence directory');
  const sources = ['src/features/chat/ChatPage.tsx', 'e2e/history-restore.spec.ts', '../src/avatar/main.py',
    '../src/avatar/brain/memory.py', '../src/avatar/web_api.py', '../evals/interaction/cycle-11/history-contract.json'];
  for (const p of ['src/features/chat/useChatHistory.ts', 'src/lib/conversation.ts']) if (existsSync(p)) sources.push(p);
  const report = { head: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(),
    sourceSha256: Object.fromEntries(sources.map(p => [p, hash(p)])),
    servedBundleSha256: Object.fromEntries(['dist/index.html', ...readdirSync('dist/assets').filter(p => p.endsWith('.js')).map(p => 'dist/assets/' + p)].map(p => [p, hash(p)])),
    scope: 'Actual browser/local HTTP/SSE, controlled provider and disposable database; no real model, physical or multi-day approval',
    elapsedSeconds: 0, turns: [] as any[], steps: [] as any[], errors: [] as string[],
    completed: false, failure: null as string | null };
  const started = Date.now(); const save = () => { report.elapsedSeconds = (Date.now() - started) / 1000; writeFileSync(file, JSON.stringify(report, null, 2) + '\n'); };
  page.on('pageerror', error => report.errors.push(error.message));
  const submitted: string[] = [];
  page.on('request', request => { if (new URL(request.url()).pathname === '/api/v1/turns' && request.method() === 'POST') submitted.push(request.postDataJSON().request_id); });
  const get = async (path: string) => {
    const response = await page.request.get('/api/v1' + path, { headers: { 'X-Avatar-Token': token } });
    expect(response.ok()).toBe(true); return (await response.json()).data;
  };
  const send = async (i: number) => {
    const text = `项目代号恢复审计第${String(i).padStart(3, '0')}号，继续规划。`;
    await page.getByLabel('消息', { exact: true }).fill(text);
    await page.getByRole('button', { name: '发送消息', exact: true }).click();
    await expect(page.locator('.chat-message.assistant').last().getByRole('button', { name: '朗读回复', exact: true })).toBeVisible();
    const job = await get('/turns/' + submitted.at(-1)); expect(job.status).toBe('completed');
    report.turns.push({ text, ...job }); save(); return text;
  };
  save();
  try {
    await page.goto('/chat#' + token);
    await expect(page.getByRole('heading', { name: '对话观测', exact: true })).toBeVisible();
    const first = await send(1); await send(2);
    const before = await page.locator('.chat-message > div').allTextContents();
    await page.getByRole('link', { name: '工具', exact: true }).click();
    await page.getByRole('link', { name: '对话观测', exact: true }).click();
    report.steps.push({ name: 'SPA restore', before, observed: await page.locator('.chat-message > div').allTextContents() }); save();
    await expect(page.getByText(first, { exact: true })).toBeVisible();
    await expect(page.locator('.chat-message')).toHaveCount(4);
    await page.reload(); await expect(page.getByText(first, { exact: true })).toBeVisible();
    const latestTrace = page.locator('.chat-message.assistant details').last();
    await latestTrace.locator('summary').click();
    await expect(latestTrace.locator('pre')).toHaveCount(5);
    expect(JSON.parse((await latestTrace.locator('pre').first().textContent())!)).toEqual(report.turns.at(-1).result.trace.decision);
    await latestTrace.locator('summary').click();
    report.steps.push({ name: 'refresh and original trace', passed: true }); save();
    for (let i = 3; i <= 54; i++) await send(i);
    await page.getByRole('link', { name: '工具', exact: true }).click();
    await page.getByRole('link', { name: '对话观测', exact: true }).click();
    await expect(page.locator('.chat-message')).toHaveCount(100);
    await page.getByRole('button', { name: '加载更早的对话', exact: true }).click();
    await expect(page.locator('.chat-message')).toHaveCount(108);
    const ids = await page.locator('.chat-message').evaluateAll(nodes => nodes.map(node => node.getAttribute('data-message-id')));
    expect(ids.every(Boolean) && new Set(ids).size === 108).toBe(true);
    const snapshot = await get('/conversation?limit=200');
    expect(snapshot.items.map((m: any) => m.text)).toEqual(report.turns.flatMap(row => [row.text, row.result.reply]));
    report.steps.push({ name: '54 turns and source pagination', ids, snapshot }); save();
    await page.getByLabel('消息', { exact: true }).fill('请解释云为什么会移动，fixture-long');
    await page.getByRole('button', { name: '发送消息', exact: true }).click();
    await expect(page.getByText('正在生成；最终回复会完成检查后替换此草稿。', { exact: true })).toBeVisible();
    const draft = await page.locator('.chat-message.assistant').last().locator('div').first().textContent();
    await page.getByRole('button', { name: '停止生成', exact: true }).click();
    await expect.poll(async () => (await get('/turns/' + submitted.at(-1))).status).toBe('cancelled');
    await page.reload(); await expect(page.locator('.chat-message.user').last()).toContainText('fixture-long');
    const cancelledSnapshot = await get('/conversation?limit=200');
    expect(cancelledSnapshot.items.filter((m: any) => m.role === 'assistant')).toHaveLength(54);
    if (draft) expect(cancelledSnapshot.items.some((m: any) => m.role === 'assistant' && m.text === draft)).toBe(false);
    report.steps.push({ name: 'cancelled draft not restored', draft, snapshot: cancelledSnapshot }); save();
    // Hold one genuine old snapshot; the privacy event must invalidate this read.
    let release!: () => void; const held = new Promise<void>(resolve => { release = resolve; });
    let captured!: () => void; const capture = new Promise<void>(resolve => { captured = resolve; });
    let intercepted = false, fulfillmentError: string | null = null;
    await page.route('**/api/v1/conversation*', async route => {
      if (intercepted) { await route.continue(); return; }
      intercepted = true; const response = await route.fetch(); const body = await response.body(); captured(); await held;
      try { await route.fulfill({ response, body }); } catch (error) { fulfillmentError = String(error); }
    });
    await page.getByRole('button', { name: '刷新对话记录', exact: true }).click(); await capture;
    const other = await context.newPage(); await other.goto('/memory#' + token);
    const summary = await get('/summary'); expect(summary.items.length).toBeGreaterThan(0);
    const selected = summary.items[0];
    const source = other.locator('.source-detail').filter({ hasText: `原话 #${selected.message_id} ·` });
    await source.getByRole('button', { name: '预览删除此原话', exact: true }).click();
    await other.getByRole('checkbox', { name: '我理解此操作不可撤销', exact: true }).check();
    await other.getByRole('button', { name: '确认执行', exact: true }).click();
    await expect(other.getByRole('dialog')).toHaveCount(0);
    await expect(page.getByText(selected.text, { exact: true })).toHaveCount(0);
    release();
    await page.bringToFront();
    await expect(page.locator('.chat-history')).toHaveAttribute('data-history-ready', 'true');
    await expect(page.getByText(selected.text, { exact: true })).toHaveCount(0);
    const current = await get('/conversation?limit=200');
    expect(current.revision).toBeGreaterThan(snapshot.revision);
    expect(current.items.find((m: any) => m.id === selected.message_id).redacted).toBe(true);
    expect(JSON.stringify(current)).not.toContain(selected.text);
    expect(current.items.every((m: any) => !m.result)).toBe(true);
    expect(submitted).toHaveLength(55);
    report.steps.push({ name: 'cross-tab erase invalidates held old snapshot and traces', erasedSource: selected.message_id,
      erasedText: selected.text, fulfillmentError, current, submitted: submitted.length });
    await other.close(); expect(report.errors).toEqual([]); report.completed = true;
  } catch (error) { report.failure = String(error); throw error; }
  finally { save(); await page.screenshot({ path: join(folder, 'restore-final.png') }).catch(() => {}); }
});
