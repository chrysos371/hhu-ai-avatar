import { expect, test, type Page } from '@playwright/test';
import { writeFileSync, mkdirSync } from 'node:fs';
const token = 'mission-control-disposable-e2e-token';
async function microphone(page: Page, tone: boolean) {
  await page.goto('/chat#' + token);
  await expect(page.getByLabel('上传 WAV 语音')).toBeEnabled();
  await page.evaluate(async playTone => {
    const context = new AudioContext({ sampleRate: 48000 });
    const destination = context.createMediaStreamDestination();
    const gain = context.createGain(); gain.gain.value = playTone ? .04 : 0;
    const oscillator = context.createOscillator(); oscillator.frequency.value = 220;
    oscillator.connect(gain).connect(destination);
    oscillator.start(); oscillator.stop(context.currentTime + 1);
    const state = { stops: 0 };
    Object.assign(window, { endpointTest: state });
    for (const track of destination.stream.getTracks()) {
      const stop = track.stop.bind(track);
      track.stop = () => { state.stops++; stop(); void context.close(); };
    }
    Object.defineProperty(navigator.mediaDevices, 'getUserMedia', { configurable: true,
      value: async () => { await context.resume(); return destination.stream; } });
  }, tone);
}
test('automatic pause fills only a draft and releases the real audio graph', async ({ page }) => {
  await microphone(page, true);
  const start = Date.now();
  await page.getByRole('button', { name: '麦克风输入' }).click();
  await expect(page.getByLabel('消息', { exact: true })).toHaveValue('浏览器识别草稿', { timeout: 7000 });
  await expect(page.getByText('检测到停顿，已结束录音；请检查识别草稿。')).toBeVisible();
  await expect(page.locator('.chat-message')).toHaveCount(0);
  expect(await page.evaluate(() => (window as unknown as { endpointTest: { stops: number } }).endpointTest.stops)).toBe(1);
  mkdirSync('../data/g2-cycle-02', { recursive: true });
  writeFileSync('../data/g2-cycle-02/endpoint-browser-pause.json', JSON.stringify({
    scope: 'Chromium generated WebAudio tone and silence through actual AudioWorklet; controlled ASR, no physical mic',
    draftMs: Date.now() - start, tracksStopped: 1, messagesSent: 0,
  }, null, 2));
});
test('eight seconds of silence releases microphone without transcription or chat', async ({ page }) => {
  await microphone(page, false);
  const calls: string[] = [];
  page.on('request', request => {
    if (request.url().includes('/speech/transcribe') || request.url().endsWith('/turns')) calls.push(request.url());
  });
  await page.getByRole('button', { name: '麦克风输入' }).click();
  await expect(page.getByText('未检测到足够音量的语音，录音已结束；可关闭自动结束后重试。')).toBeVisible({ timeout: 12000 });
  expect(calls).toEqual([]);
  expect(await page.evaluate(() => (window as unknown as { endpointTest: { stops: number } }).endpointTest.stops)).toBe(1);
  await expect(page.getByLabel('消息', { exact: true })).toHaveValue('');
});
