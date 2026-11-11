import { test, expect } from '@playwright/test';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { join } from 'node:path';

const token = 'mission-control-disposable-e2e-token';
test('external API erasure invalidates an already visible old trace without a UI notification', async ({ page }, info) => {
  test.skip(process.env.AVATAR_E2E_EXTERNAL_ERASE !== '1', 'explicit external-writer audit probe'); test.setTimeout(0);
  const folder = process.env.AVATAR_E2E_EVIDENCE_DIR ?? info.outputDir; mkdirSync(folder, { recursive: true });
  const path = join(folder, 'external-erase.json'); if (existsSync(path)) throw Error('Use fresh external-erasure output');
  const sourcePaths = ['src/features/chat/ChatPage.tsx', 'src/features/chat/useChatHistory.ts', 'src/lib/conversation.ts',
    '../src/avatar/brain/conversations.py', '../src/avatar/brain/memory.py', 'e2e/external-erase.spec.ts',
    '../evals/interaction/cycle-11/external-erase-probe.json'];
  const report: any = { scope: 'Direct API deletion with no frontend event; disposable synthetic fact, no real user data',
    head: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(),
    sourceSha256: Object.fromEntries(sourcePaths.map(p => [p, createHash('sha256').update(readFileSync(p)).digest('hex')])),
    before: null, backendAfter: null, rows: [], refreshControl: null, completed: false, failure: null };
  const save = () => writeFileSync(path, JSON.stringify(report, null, 2) + '\n'); save();
  const api = async (path: string, data?: unknown) => {
    const response = await page.request[data === undefined ? 'get' : 'post']('/api/v1' + path,
      { headers: { 'X-Avatar-Token': token }, ...(data === undefined ? {} : { data }) });
    expect(response.ok()).toBe(true); return (await response.json()).data;
  };
  try {
    const facts = await api('/memory'); const fact = facts.find((row: any) => row.content.includes('浏览器测试原名')); expect(fact).toBeTruthy();
    await page.goto('/chat#' + token); await expect(page.locator('.chat-history')).toHaveAttribute('data-history-ready', 'true');
    await page.getByLabel('消息', { exact: true }).fill(fact.content);
    await page.getByRole('button', { name: '发送消息', exact: true }).click();
    const trace = page.locator('.chat-message.assistant details').last(); await expect(trace).toBeAttached();
    await trace.locator('summary').click(); await expect(trace.locator('pre').nth(1)).toContainText(fact.content);
    report.before = { factId: fact.id, factContent: fact.content, trace: await trace.locator('pre').allTextContents(), snapshot: await api('/conversation') }; save();
    const draft = await api('/memory/batch-draft', { actions: [{ action: 'forget', id: fact.id }] });
    const applied = await api('/operations/' + draft.draft_id + '/confirm', { confirmation_token: draft.confirmation_token });
    report.backendAfter = { auditId: applied.audit_id, snapshot: await api('/conversation') };
    expect(report.backendAfter.snapshot.revision).toBeGreaterThan(report.before.snapshot.revision);
    expect(report.backendAfter.snapshot.items.filter((row: any) => row.role === 'assistant').every((row: any) => !row.result)).toBe(true);
    report.rows = await page.evaluate(async content => {
      const rows: { wall: number; oldTraceVisible: boolean }[] = [];
      await new Promise<void>(resolve => {
        const tick = () => {
          rows.push({ wall: performance.now(), oldTraceVisible: [...document.querySelectorAll('.trace pre')].some(node => node.textContent?.includes(content)) });
          if (rows.length < 12) requestAnimationFrame(tick); else resolve();
        }; requestAnimationFrame(tick);
      }); return rows;
    }, fact.content); save();
    await page.getByRole('button', { name: '刷新对话记录', exact: true }).click();
    await expect(page.locator('.chat-history')).toHaveAttribute('data-history-ready', 'true');
    report.refreshControl = { traces: await page.locator('.trace pre').allTextContents(), oldTraceRemoved: await page.locator('.trace').count() === 0 }; save();
    expect(report.refreshControl.oldTraceRemoved).toBe(true);
    expect(report.rows.every((row: any) => !row.oldTraceVisible)).toBe(true); report.completed = true;
  } catch (error) { report.failure = String(error); throw error; }
  finally { save(); await page.screenshot({ path: join(folder, 'external-erase-final.png') }).catch(() => {}); }
});
