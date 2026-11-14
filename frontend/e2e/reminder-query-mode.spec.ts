import { expect, test } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';

const protocol = JSON.parse(readFileSync(new URL('../../evals/interaction/cycle-45/product-query-protocol.json', import.meta.url), 'utf8'));
const token = 'mission-control-disposable-e2e-token';

test('dedicated reminder queries reach the real DOM with preserved typed history and no reminder changes', async ({ page }, info) => {
  test.skip(Boolean(process.env.AVATAR_E2E_LLM_PROVIDER || process.env.AVATAR_E2E_REMINDER_DELIVERY_CASE),
    'Maintained disposable default fixture; not a native quality experiment.');
  const report: any = { scope: 'C45 actual product query mode DOM/HTTP, controlled fixture, previously seen queries',
    head: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(),
    completed: false, turns: [], calls: [], errors: [], failure: null, nativeOrGPUClaim: false };
  const api = async (path: string, data?: unknown) => {
    const response = await page.request.fetch('/api/v1' + path, { method: data === undefined ? 'GET' : 'POST',
      headers: { 'X-Avatar-Token': token }, data });
    const body = await response.json(), logged = structuredClone(body);
    if (logged.data?.confirmation_token) logged.data.confirmation_token = '[fixture confirmation capability omitted]';
    report.calls.push({ path, status: response.status(), response: logged });
    expect(response.ok()).toBe(true); return body.data;
  };
  page.on('pageerror', error => report.errors.push(error.message));
  try {
    await api('/chat', { text: '回到现实。' });
    const draft = await api('/reminders', { text: '提醒我2099年1月1日上午十点，' + protocol.browser_seed + '。' });
    await api('/operations/' + draft.draft_id + '/confirm', { confirmation_token: draft.confirmation_token });
    const row = (await api('/reminders')).find((r: any) => r.title === protocol.browser_seed);
    expect(row).toBeTruthy(); report.before = row;
    await page.goto('/chat#' + token);
    await expect(page.locator('.chat-history')).toHaveAttribute('data-history-ready', 'true');
    for (const entry of protocol.browser_cases) {
      const text = entry.text.replace('{id}', String(row.id));
      await expect(page.getByLabel('本轮仅查询提醒')).toBeEnabled();
      await page.getByLabel('本轮仅查询提醒').check();
      await expect(page.getByLabel('本轮允许联网工具')).toBeDisabled();
      const accepted = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/v1/turns');
      await page.getByLabel('消息', { exact: true }).fill(text);
      await page.getByRole('button', { name: '发送消息' }).click();
      const response = await accepted, submitted = response.request().postDataJSON();
      expect(submitted).toMatchObject({ text, mode: 'reminder_query', use_web: false });
      const jobId = (await response.json()).data.job_id;
      await expect(page.locator('.chat-message.assistant').last().locator('[data-reminder-query]')).toHaveAttribute('data-reminder-query', entry.route);
      await expect(page.getByLabel('本轮仅查询提醒')).not.toBeChecked();
      const job = await api('/turns/' + jobId);
      expect(job.status).toBe('completed');
      const visible = await page.locator('.chat-message.assistant > div').last().textContent();
      expect(visible).toBe(job.result.reply);
      expect(job.result.reminder_query.route).toBe(entry.route);
      expect(job.result.reminder_query.source_message_id).toBe(job.result.conversation.user_message_id);
      expect(job.result.due_reminders).toEqual([]); expect(job.result.tool_calls).toEqual([]);
      expect(job.result.action_receipts.items).toEqual([]);
      if (entry.route === 'read_state') expect(visible).toContain(row.title);
      if (entry.route === 'read_policy') expect(visible).toContain('当前没有短信、邮件或电话提醒通道');
      report.turns.push({ text, submitted, visible, result: job.result });
    }
    report.after = (await api('/reminders')).find((r: any) => r.id === row.id);
    expect(report.after).toEqual(report.before);
    await page.reload();
    await expect(page.locator('.chat-history')).toHaveAttribute('data-history-ready', 'true');
    for (const entry of protocol.browser_cases) {
      await expect(page.locator('[data-reminder-query=' + entry.route + ']')).toHaveCount(1);
    }
    report.views = [];
    for (const width of protocol.browser_viewports) {
      await page.setViewportSize({ width, height: 1000 });
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
      expect(overflow).toBe(false);
      await page.screenshot({ path: info.outputPath('query-mode-' + width + '.png'), fullPage: true });
      report.views.push({ width, overflow });
    }
    expect(report.errors).toEqual([]); report.completed = true;
  } catch (error) { report.failure = String(error); throw error; }
  finally { writeFileSync(info.outputPath('query-mode-evidence.json'), JSON.stringify(report, null, 2) + '\n'); }
});
