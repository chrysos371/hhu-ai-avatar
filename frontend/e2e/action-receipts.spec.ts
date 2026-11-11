import { test, expect } from '@playwright/test';
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';

const token = 'mission-control-disposable-e2e-token';
test('real local receipts survive reply reload and clear on independent privacy change', async ({ page }, info) => {
  test.skip(process.env.AVATAR_E2E_ACTION_RECEIPTS !== '1', 'explicit isolated receipt/privacy fixture');
  test.setTimeout(0);
  const folder = process.env.AVATAR_E2E_EVIDENCE_DIR ?? info.outputDir;
  mkdirSync(folder, { recursive: true });
  const output = join(folder, 'receipt-browser.json');
  if (existsSync(output)) throw Error('Use fresh receipt browser evidence');
  function files(path: string): string[] {
    return readdirSync(path, { withFileTypes: true }).flatMap(entry => entry.isDirectory()
      ? files(join(path, entry.name)) : [join(path, entry.name)]);
  }
  const inputs = [...files('src'), ...files('../src/avatar').filter(path => path.endsWith('.py')),
    ...files('dist'), 'e2e/action-receipts.spec.ts', '../tests/helpers/serve_admin_e2e.py'];
  const report: Record<string, unknown> = {
    scope: 'Actual Chromium UI, authenticated app HTTP/SSE, real local SQL; fixture model, no native model quality or notification/device claim.',
    head: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(), completed: false,
    sourceSha256: Object.fromEntries(inputs.map(path => [path, createHash('sha256').update(readFileSync(path)).digest('hex')])),
  };
  const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
  const save = () => writeFileSync(output, JSON.stringify(report, null, 2) + '\n'); save();
  const api = async (path: string, data?: unknown) => {
    const response = await page.request[data === undefined ? 'get' : 'post']('/api/v1' + path,
      { headers: { 'X-Avatar-Token': token }, ...(data === undefined ? {} : { data }) });
    expect(response.ok()).toBe(true); return (await response.json()).data;
  };
  const ready = async () => {
    await expect(page.locator('.chat-history')).toHaveAttribute('data-history-ready', 'true');
    await expect(page.getByRole('button', { name: '发送消息', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: '核验本地操作记录', exact: true })).toBeEnabled();
  };
  const send = async (text: string) => {
    await page.getByLabel('消息', { exact: true }).fill(text);
    await page.getByRole('button', { name: '发送消息', exact: true }).click();
    await expect(page.getByLabel('消息', { exact: true })).toHaveValue('');
    await ready();
  };
  const panel = page.getByRole('region', { name: '实际本地操作', exact: true });
  try {
    await page.goto('/chat#' + token); await ready();
    await send('提醒我明天下午3点浏览器回执正控');
    const created = await api('/conversation/actions'); report.created = created;
    expect(created.items).toHaveLength(1); expect(created.items[0].action).toBe('reminder.created');
    const reminder = created.items[0].reminder_id;
    await panel.getByRole('button', { name: '核验本地操作记录' }).click();
    await expect(panel.getByText(new RegExp('创建提醒 · 提醒 #' + reminder))).toBeVisible();
    await send('取消提醒' + reminder);
    await panel.getByRole('button', { name: '核验本地操作记录' }).click();
    await expect(panel.getByText(new RegExp('取消提醒 · 提醒 #' + reminder))).toBeVisible();
    report.cancelled = await api('/conversation/actions'); report.reminders = await api('/reminders');
    await page.reload(); await ready();
    expect(await panel.locator('li').count()).toBe(0); // No cached evidence automatically restored.
    await panel.getByRole('button', { name: '核验本地操作记录' }).click();
    await expect(panel.locator('li')).toHaveCount(2);
    report.reloaded = await panel.innerText();
    await page.screenshot({ path: join(folder, 'receipt-ui-desktop.png'), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: join(folder, 'receipt-ui-mobile.png'), fullPage: true });
    const fact = (await api('/memory')).find((row: { content: string }) => row.content.includes('浏览器测试原名'));
    expect(fact).toBeTruthy();
    const draft = await api('/memory/batch-draft', { actions: [{ action: 'forget', id: fact.id }] });
    await api('/operations/' + draft.draft_id + '/confirm', { confirmation_token: draft.confirmation_token });
    await expect(panel.locator('li')).toHaveCount(0);
    await ready(); await panel.getByRole('button', { name: '核验本地操作记录' }).click();
    await expect(panel.getByText(/当前没有可见的本地操作回执/)).toBeVisible();
    report.afterForget = await api('/conversation/actions'); report.errors = errors;
    expect(report.afterForget).toMatchObject({ items: [], notification_delivery_verified: false });
    expect(errors).toEqual([]); report.completed = true;
  } catch (error) { report.failure = String(error); throw error; }
  finally { save(); }
});
