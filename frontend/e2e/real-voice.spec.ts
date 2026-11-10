import { test, expect } from '@playwright/test';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

test('real local ASR draft reaches streamed response and real TTS playback', async ({ page }, info) => {
  test.skip(!process.env.AVATAR_E2E_REAL_ASR_MODEL || process.env.AVATAR_E2E_REAL_TTS !== '1', 'requires explicit local ASR model and online TTS');
  const folder = process.env.AVATAR_E2E_EVIDENCE_DIR ?? info.outputDir;
  mkdirSync(folder, { recursive: true });
  const screenshot = join(folder, 'real-voice-browser.png');
  const timing = join(folder, 'real-voice-browser.json');
  if (existsSync(screenshot) || existsSync(timing)) throw Error('Use a fresh real-service evidence directory');
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
  const audio = page.getByLabel(/语音播放器$/);
  await expect(audio).toBeVisible({ timeout: 20000 });
  await expect.poll(() => audio.evaluate((element: HTMLAudioElement) => element.currentTime)).toBeGreaterThan(0.05);
  const sendToPlayingMs = Date.now() - sent;
  await expect.poll(async () => Number(await page.locator('.avatar-stage').getAttribute('data-mouth-open'))).toBeGreaterThan(0);
  await page.evaluate(() => window.scrollTo(0,0));
  await page.screenshot({ path: screenshot, fullPage: true });
  writeFileSync(timing, JSON.stringify({
    scope: process.env.AVATAR_E2E_LLM_PROVIDER ? 'synthetic audio -> real local ASR -> reviewed draft -> real local Qwen -> real Edge-TTS -> Chromium/SVG' : 'synthetic audio -> real local ASR -> reviewed draft -> controlled HTTP model -> real Edge-TTS -> Chromium/SVG',
    realModelInference: Boolean(process.env.AVATAR_E2E_LLM_PROVIDER),
    asrDraftMs, sendToPlayingMs, asrDevice: process.env.AVATAR_E2E_ASR_DEVICE ?? 'cpu',
    physicalMicrophoneVerified: false, realLLMQualityVerified: false,
  }, null, 2) + '\n', { flag: 'wx' });
  await page.getByRole('button', { name: '停止播放', exact: true }).click();
  await expect(audio).not.toHaveAttribute('src');
});
