import { expect, test } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
const queryProtocol = JSON.parse(readFileSync(new URL('../../evals/interaction/cycle-39/explicit-reminder-query-protocol.json', import.meta.url), 'utf8')) as {
  maintained_browser_control: { inputs: string[] };
};

const token = 'mission-control-disposable-e2e-token';
test('explicit reminder reads deliver recorded state and conditions without changing the record', async ({ page }, info) => {
  test.skip(Boolean(process.env.AVATAR_E2E_LLM_PROVIDER || process.env.AVATAR_E2E_REMINDER_DELIVERY_CASE),
    'This maintained control is scoped to the disposable default fixture.');
  const report: any = { scope: 'C39 maintained explicit reminder query browser control',
    head: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(),
    completed: false, failure: null, calls: [], turns: [], errors: [], nativeOrGpuClaim: false };
  const api = async (path: string, data?: unknown) => {
    const response = await page.request.fetch('/api/v1' + path, { method: data === undefined ? 'GET' : 'POST',
      headers: { 'X-Avatar-Token': token }, data });
    const body = await response.json();
    const logged = structuredClone(body);
    if (logged.data?.confirmation_token) logged.data.confirmation_token = '[fixture confirmation capability omitted]';
    report.calls.push({ path, status: response.status(), response: logged });
    expect(response.ok()).toBe(true);
    return body.data;
  };
  page.on('pageerror', error => report.errors.push(error.message));
  try {
    report.sourceControl = await api('/chat', { text: '回到现实。' });
    expect(report.sourceControl.generation_mode).toBe('rules_speaker_control');
    const draft = await api('/reminders', { text: '提醒我2099年1月1日上午十点，C39浏览器只读查询控制。' });
    await api('/operations/' + draft.draft_id + '/confirm', { confirmation_token: draft.confirmation_token });
    const row = (await api('/reminders')).find((value: any) => value.title === 'C39浏览器只读查询控制');
    expect(row).toBeTruthy();
    report.before = row;
    await page.goto('/chat#' + token);
    await expect(page.locator('.chat-history')).toHaveAttribute('data-history-ready', 'true');
    for (const template of queryProtocol.maintained_browser_control.inputs) {
      const text = template.replace('{id}', String(row.id));
      const before = await page.locator('.chat-message.assistant').count();
      const accepted = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/v1/turns');
      await page.getByLabel('消息', { exact: true }).fill(text);
      await page.getByRole('button', { name: '发送消息' }).click();
      const jobId = (await (await accepted).json()).data.job_id;
      await expect(page.locator('.chat-message.assistant')).toHaveCount(before + 1);
      await expect(page.locator('.chat-message.assistant').last().getByRole('button', { name: '朗读回复', exact: true })).toBeVisible();
      const visible = await page.locator('.chat-message.assistant > div').last().textContent();
      const job = await api('/turns/' + jobId);
      expect(job.status).toBe('completed');
      expect(job.result.generation_mode).toBe('rules_reminder_query');
      expect(job.result.analysis_mode).toBe('rules_reminder_query');
      expect(visible).toBe(job.result.reply);
      expect(job.result.tool_calls).toEqual([]);
      expect(job.result.action_receipts.items).toEqual([]);
      expect(job.result.due_reminders).toEqual([]);
      if (text.startsWith('查询提醒编号')) {
        expect(visible).toContain(row.title);
        expect(visible).toContain('记录状态为有效');
        expect(job.result.reminder_query.state.id).toBe(row.id);
      } else {
        expect(visible).toContain('服务退出期间无法自动投递');
        expect(job.result.reminder_query.external_delivery_channels).toEqual([]);
      }
      const conversation = await api('/conversation');
      expect(conversation.items.find((value: any) => value.id === job.result.conversation.assistant_message_id).text).toBe(visible);
      report.turns.push({ text, visible, result: job.result });
    }
    report.after = (await api('/reminders')).find((value: any) => value.id === row.id);
    expect(report.after).toEqual(report.before);
    expect(report.errors).toEqual([]);
    await page.screenshot({ path: info.outputPath('reminder-query-final.png') });
    report.completed = true;
  } catch (error) { report.failure = String(error); throw error; }
  finally { writeFileSync(info.outputPath('reminder-query-evidence.json'), JSON.stringify(report, null, 2) + '\n'); }
});
