import { test, expect } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';

test('real local ASR draft reaches streamed response and real TTS playback', async ({ page }) => {
  test.skip(!process.env.AVATAR_E2E_REAL_ASR_MODEL || process.env.AVATAR_E2E_REAL_TTS !== '1', 'requires explicit local ASR model and online TTS');
  await page.goto('/chat#mission-control-disposable-e2e-token');
  await expect(page.getByLabel('上传 WAV 语音')).toBeEnabled();
  const begin = Date.now();
  await page.getByLabel('上传 WAV 语音').setInputFiles('../data/g2-cycle-01/voice-corpus/voice0-text2.wav');
  await expect(page.getByLabel('消息', { exact: true })).toHaveValue(/天空.*蓝色/);
  const asrDraftMs = Date.now() - begin;
  await expect(page.locator('.chat-message')).toHaveCount(0);
  await page.getByLabel('自动分段朗读新回复').check();
  const sent = Date.now();
  await page.getByRole('button', { name: '发送消息' }).click();
  const audio = page.getByLabel('小海语音播放器');
  await expect(audio).toBeVisible({ timeout: 20000 });
  await expect.poll(() => audio.evaluate((element: HTMLAudioElement) => element.currentTime)).toBeGreaterThan(0.05);
  const sendToPlayingMs = Date.now() - sent;
  await expect.poll(async () => Number(await page.locator('.avatar-stage').getAttribute('data-mouth-open'))).toBeGreaterThan(0);
  await page.evaluate(() => window.scrollTo(0,0));
  await page.screenshot({ path: '../data/g2-cycle-01/real-voice-browser.png', fullPage: true });
  mkdirSync('../data/g2-cycle-01', { recursive: true });
  writeFileSync('../data/g2-cycle-01/real-voice-browser.json', JSON.stringify({
    scope: 'real synthetic audio -> GPU/CPU local ASR -> reviewed draft -> controlled HTTP model -> real Edge-TTS -> Chromium/SVG',
    asrDraftMs, sendToPlayingMs, asrDevice: process.env.AVATAR_E2E_ASR_DEVICE ?? 'cpu',
    physicalMicrophoneVerified: false, realLLMQualityVerified: false,
  }, null, 2) + '\n');
  await page.getByRole('button', { name: '停止播放', exact: true }).click();
  await expect(audio).not.toHaveAttribute('src');
});
