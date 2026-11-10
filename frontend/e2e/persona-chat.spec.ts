import { test, expect } from '@playwright/test';
import { writeFileSync } from 'node:fs';
const headers = { 'X-Avatar-Token': 'mission-control-disposable-e2e-token' };
test('confirmed persona name reaches chat and audio accessibility labels', async ({ page }, info) => {
  await page.goto('/chat#mission-control-disposable-e2e-token');
  const original = (await (await page.request.get('/api/v1/persona', { headers })).json()).data.data.name;
  async function rename(name: string) {
    const response = await page.request.post('/api/v1/persona/draft', { headers, data: { changes: { name } } });
    const draft = (await response.json()).data;
    expect(response.status()).toBe(201);
    const confirmed = await page.request.post(`/api/v1/operations/${draft.draft_id}/confirm`, {
      headers, data: { confirmation_token: draft.confirmation_token },
    });
    expect(confirmed.ok()).toBe(true);
  }
  try {
    await rename('星澜'); await page.reload();
    const current = (await (await page.request.get('/api/v1/persona', { headers })).json()).data.data.name;
    const heading = await page.locator('.speech-panel h2').textContent();
    const player = await page.locator('audio').getAttribute('aria-label');
    writeFileSync(info.outputPath('persona-name.json'), JSON.stringify({ currentName: current, heading, player }, null, 2));
    await expect(page.getByRole('heading', { name: '星澜在这里' })).toBeVisible();
    await expect(page.locator('.avatar-stage')).toHaveAttribute('aria-label', '星澜，正在聆听');
    await expect(page.getByLabel('星澜语音播放器')).toHaveCount(1);
  } finally { await rename(original); }
});
