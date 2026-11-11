import { test, expect } from '@playwright/test';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { join } from 'node:path';
const token = 'mission-control-disposable-e2e-token';
type ScopeRow = { input: string; reply: string | null; scope: string; blocked: boolean;
  generationMode: string; memories: string[]; reminders: number; seconds: number };

test('real character speech stays separate from user memory and reminder authority', async ({ page }, info) => {
  test.skip(!process.env.AVATAR_E2E_LLM_PROVIDER || process.env.AVATAR_E2E_SPEAKER_SCOPE !== '1', 'explicit real provider and speaker experiment required');
  test.setTimeout(0);
  const folder = process.env.AVATAR_E2E_EVIDENCE_DIR ?? info.outputDir;
  const output = join(folder, 'real-speaker-browser.json');
  const screenshot = join(folder, 'real-speaker-browser.png');
  if (existsSync(output) || existsSync(screenshot)) throw Error('Use fresh speaker evidence paths');
  mkdirSync(folder, { recursive: true });
  const provenance = {
    sourceHead: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(),
    createdUtc: new Date().toISOString(),
    provider: JSON.parse(readFileSync(process.env.AVATAR_E2E_LLM_PROVIDER ?? '', 'utf8')),
    sourceSha256: Object.fromEntries(['../src/avatar/main.py', '../src/avatar/brain/speaker_scope.py',
      '../src/avatar/web.py', 'e2e/real-speaker.spec.ts'].map(path => [path,
      createHash('sha256').update(readFileSync(path)).digest('hex')])),
  };
  const rows: ScopeRow[] = [];
  const save = (complete: boolean) => writeFileSync(output, JSON.stringify({
    scope: 'Actual pinned local model and application HTTP/SSE/browser; synthetic source ownership and action authority only',
    ...provenance,
    rows, executionComplete: complete, semanticApproved: false,
  }, null, 2) + '\n');
  save(false);
  await page.goto('/chat#' + token);
  await expect(page.locator('.chat-history')).toHaveAttribute('data-history-ready', 'true');
  async function say(text: string) {
    const before = await page.locator('.chat-message.assistant').count();
    const started = Date.now();
    const accepted = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/v1/turns');
    await page.getByLabel('消息', { exact: true }).fill(text);
    await page.getByRole('button', { name: '发送消息' }).click();
    const id = (await (await accepted).json()).data.job_id;
    await expect(page.locator('.chat-message.assistant')).toHaveCount(before + 1, { timeout: 30000 });
    await expect(page.locator('.chat-message.assistant').last().getByRole('button', { name: '朗读回复', exact: true })).toBeVisible({ timeout: 30000 });
    const visible = await page.locator('.chat-message.assistant > div').last().textContent();
    const snapshot = await page.evaluate(async ({ jobId, auth }) => {
      const get = async (path: string) => {
        const response = await fetch('/api/v1/' + path, { headers: { 'X-Avatar-Token': auth } });
        if (!response.ok) throw Error('HTTP ' + response.status);
        return (await response.json()).data;
      };
      return { job: await get('turns/' + encodeURIComponent(jobId)),
        memories: await get('memory'), reminders: await get('reminders') };
    }, { jobId: id, auth: token });
    expect(snapshot.job.status).toBe('completed');
    const result = snapshot.job.result;
    expect(visible).toBe(result.reply);
    expect(result.trace.verifier.available).toBe(false);
    const row: ScopeRow = { input: text, reply: visible, scope: result.speaker_attribution.scope,
      blocked: result.speaker_tool_blocked, generationMode: result.generation_mode,
      memories: snapshot.memories.map((memory: { content: string }) => memory.content),
      reminders: snapshot.reminders.length, seconds: (Date.now() - started) / 1000 };
    rows.push(row); save(false);
    return row;
  }
  const real = await say('我叫陈宁。');
  expect(real.memories).toEqual(['名字: 陈宁']);
  expect((await say('我来扮演小说角色。')).scope).toBe('fictional_character');
  expect((await say('我叫林悦。')).memories).toEqual(['名字: 陈宁']);
  expect((await say('我喜欢游泳。')).memories).toEqual(['名字: 陈宁']);
  const blocked = await say('提醒我明天9点带伞。');
  expect(blocked.blocked).toBe(true); expect(blocked.reminders).toBe(0);
  expect(blocked.reply).toContain('退出角色');
  const character = await say('故事里我叫什么名字？');
  expect(character.reply).toContain('林悦'); expect(character.reply).not.toContain('陈宁');
  expect((await say('回到现实。')).scope).toBe('current_user');
  const authorized = await say('提醒我明天9点带伞。');
  expect(authorized.blocked).toBe(false); expect(authorized.reminders).toBe(1);
  const recalled = await say('我叫什么名字？');
  expect(recalled.reply).toContain('陈宁'); expect(recalled.reply).not.toContain('林悦');
  expect(recalled.memories).toEqual(['名字: 陈宁']);
  await page.screenshot({ path: screenshot }); save(true);
});
