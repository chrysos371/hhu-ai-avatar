import { test, expect } from '@playwright/test';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
const token = 'mission-control-disposable-e2e-token';
test('real verified identity does not bind a friend name to the user', async ({ page }, info) => {
  test.skip(!process.env.AVATAR_E2E_LLM_PROVIDER || process.env.AVATAR_E2E_IDENTITY_GROUNDING !== '1' || process.env.AVATAR_E2E_EMPTY_PROFILE !== '1', 'explicit real provider and empty disposable profile required');
  const folder = process.env.AVATAR_E2E_EVIDENCE_DIR ?? info.outputDir;
  mkdirSync(folder, { recursive: true });
  const output = join(folder, 'real-identity-browser.json');
  if (existsSync(output)) throw Error('Use a new identity evidence path');
  await page.goto('/chat#' + token);
  const replies: string[] = [];
  await expect(page.locator('.chat-history')).toHaveAttribute('data-history-ready', 'true');
  async function say(text: string) {
    const before = await page.locator('.chat-message.assistant').count();
    await page.getByLabel('消息', { exact: true }).fill(text);
    await page.getByRole('button', { name: '发送消息' }).click();
    await expect(page.locator('.chat-message.assistant')).toHaveCount(before + 1, { timeout: 20000 });
    await expect(page.locator('.chat-message.assistant').last().getByRole('button', { name: '朗读回复', exact: true })).toBeVisible({ timeout: 20000 });
    const reply = await page.locator('.chat-message.assistant > div').last().textContent();
    replies.push(reply ?? ''); return reply ?? '';
  }
  const first = await say('我的朋友叫柳林，我们第一次聊天。');
  expect(first).not.toMatch(/你好[，, ]*柳林|你叫柳林|你的名字是柳林/);
  const unknown = await say('你知道我叫什么名字吗？');
  expect(unknown).toMatch(/不知道|不记得|不清楚|无法确认|没有|还没|告诉/);
  expect(unknown).not.toMatch(/你叫柳林|你的名字是柳林/);
  await say('我叫温禾。');
  const known = await say('我的名字是什么？');
  expect(known).toContain('温禾'); expect(known).not.toContain('我叫温禾');
  const decisions = await page.locator('.trace pre').allTextContents();
  expect(decisions.some(text => text.includes('"identity_grounding": true'))).toBe(true);
  let profileGroundingObserved = false;
  if (process.env.AVATAR_E2E_PROFILE_GROUNDING === '1') {
    expect(decisions.some(text => text.includes('"generation_mode": "profile_lookup"'))).toBe(true);
    expect(decisions.some(text => text.includes('"action": "name_lookup"'))).toBe(true);
    await say('我喜欢网球。');
    const preference = await say('我的爱好是什么？');
    expect(preference).toContain('网球'); expect(preference).not.toContain('我喜欢网球');
    profileGroundingObserved = true;
  }
  writeFileSync(output, JSON.stringify({ scope: 'actual local model through HTTP/SSE/browser, disposable profile', replies, identityGroundingObserved: true, profileGroundingObserved }, null, 2)+'\n', { flag: 'wx' });
});
