import { test, expect, type Page, type TestInfo } from '@playwright/test';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
const token = 'mission-control-disposable-e2e-token';
type Sample = { wall: number; mediaTime: number; frameTime: number | null; frameSegment: number | null;
  lagMs: number | null; open: string; radiusY: number | null; paused: boolean; ended: boolean;
  seeking: boolean; readyState: number; rate: number; speaking: boolean; src: string };
type RequestRow = { slot: number; id: string; text: string; wall: number; headerToken: boolean; fulfillmentError?: string };
const hash = (path: string) => createHash('sha256').update(readFileSync(path)).digest('hex');
function artifact(name: string, info: TestInfo) {
  const folder = process.env.AVATAR_E2E_EVIDENCE_DIR ?? info.outputDir;
  mkdirSync(folder, { recursive: true }); const path = join(folder, name + '.json');
  if (existsSync(path)) throw Error('Use fresh playback evidence paths');
  const provenance = { sourceHead: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(),
    createdUtc: new Date().toISOString(), protocolSha256: hash('../evals/interaction/cycle-08/playback-protocol.json'),
    sourceSha256: Object.fromEntries(['src/features/chat/useSpeechPlayer.ts', 'src/features/chat/AvatarStage.tsx',
      'e2e/playback-audit.spec.ts', '../tests/helpers/serve_admin_e2e.py', '../src/avatar/lab/transport_fixture.py'].map(path => [path, hash(path)])),
    servedBundleSha256: Object.fromEntries(['dist/index.html', ...readdirSync('dist/assets').filter(p => p.endsWith('.js')).map(p => 'dist/assets/' + p)].map(path => [path, hash(path)])) };
  return { folder, provenance, save: (value: unknown) => writeFileSync(path, JSON.stringify(value, null, 2) + '\n') };
}
function wav(seconds: number) {
  const rate = 16000, count = seconds * rate, bytes = Buffer.alloc(44 + count * 2);
  bytes.write('RIFF', 0); bytes.writeUInt32LE(bytes.length - 8, 4); bytes.write('WAVEfmt ', 8);
  bytes.writeUInt32LE(16, 16); bytes.writeUInt16LE(1, 20); bytes.writeUInt16LE(1, 22);
  bytes.writeUInt32LE(rate, 24); bytes.writeUInt32LE(rate * 2, 28); bytes.writeUInt16LE(2, 32);
  bytes.writeUInt16LE(16, 34); bytes.write('data', 36); bytes.writeUInt32LE(count * 2, 40);
  for (let i = 0; i < count; i++) bytes.writeInt16LE(Math.round(.1 * 32767 * Math.sin(2 * Math.PI * 220 * i / rate)), 44 + i * 2);
  return bytes;
}
async function oracle(page: Page, segmented = false, holdSecond = false) {
  const requests: RequestRow[] = [], mapping: [string, { time: number; segment: number }][] = [];
  const assets = new Map<string, Buffer>(); const cancels: string[] = [];
  // Predeclare every oracle code: later prefetches must not change the sampler's
  // serialized lookup after sampling has already started in the page.
  for (let slot = 1; slot <= (segmented ? 3 : 1); slot++) {
    const total = segmented ? 100 : 800;
    for (let index = 0; index < total; index++) {
      const mouth = (index + 1 + (segmented ? (slot - 1) * 100 : 0)) / (segmented ? 301 : 801);
      mapping.push([mouth.toFixed(3), { time: index * .01, segment: slot }]);
    }
  }
  let releaseSecond!: () => void; const blocked = new Promise<void>(resolve => { releaseSecond = resolve; });
  page.on('request', request => { if (new URL(request.url()).pathname === '/api/v1/speech/cancel') cancels.push(request.postData() ?? ''); });
  await page.route('**/api/v1/speech', async route => {
    const slot = requests.length + 1, id = 'playback_audit_audio_' + String(slot).padStart(12, '0');
    const row: RequestRow = { slot, id, text: (route.request().postDataJSON() as { text: string }).text,
      wall: Date.now(), headerToken: route.request().headers()['x-avatar-token'] === token };
    requests.push(row);
    if (segmented && slot > 3) { await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: { code: 'unexpected_segment', message: 'extra segment request' }, data: null }) }); return; }
    const duration = segmented ? 1 : 8, total = duration * 100;
    const frames = Array.from({ length: total }, (_, index) => {
      const mouth = (index + 1 + (segmented ? (slot - 1) * 100 : 0)) / (segmented ? 301 : 801);
      return { time: index * .01, mouth_open: mouth, vowel: 'a', energy: 1 };
    });
    assets.set(id, wav(duration));
    if (holdSecond && slot === 2) await blocked;
    try { await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: {
      audio_id: id, duration, frames, warning: null, expires_at: Date.now() / 1000 + 900 }, error: null }) }); }
    catch (error) { row.fulfillmentError = String(error); }
  });
  await page.route('**/api/v1/speech/audio/*', async route => {
    const id = new URL(route.request().url()).pathname.split('/').at(-1)!;
    const bytes = assets.get(id); if (!bytes) throw Error('Unregistered oracle audio');
    await route.fulfill({ status: 200, contentType: 'audio/wav', body: bytes, headers: { 'Cache-Control': 'no-store' } });
  });
  return { requests, mapping, cancels, releaseSecond };
}
async function open(page: Page) {
  await page.goto('/chat#' + token);
  await expect(page.getByRole('heading', { name: '对话观测', exact: true })).toBeVisible();
  await page.evaluate(() => {
    const audio = document.querySelector('audio[aria-label$="语音播放器"]') as HTMLAudioElement;
    const scope = window as typeof window & { __auditMediaEvents: unknown[] }; scope.__auditMediaEvents = [];
    for (const type of ['play', 'playing', 'pause', 'ended', 'seeking', 'seeked', 'ratechange', 'error', 'emptied'])
      audio.addEventListener(type, () => scope.__auditMediaEvents.push({ type, wall: performance.now(),
        mediaTime: audio.currentTime, paused: audio.paused, ended: audio.ended, seeking: audio.seeking,
        src: audio.getAttribute('src'), error: audio.error?.code ?? null }));
  });
}
async function chat(page: Page, segmented = false) {
  if (segmented) await page.getByLabel('自动分段朗读新回复').check();
  await page.getByLabel('消息', { exact: true }).fill(segmented ? 'fixture-playback-audit，请给出三段最终回复。' : '你好，做一次播放时钟测试。');
  await page.getByRole('button', { name: '发送消息' }).click();
  await expect(page.locator('.chat-message.assistant details')).toHaveCount(1);
  if (!segmented) await page.getByRole('button', { name: '朗读回复' }).click();
  await expect.poll(() => page.getByLabel(/语音播放器$/).evaluate((a: HTMLAudioElement) => a.currentTime)).toBeGreaterThan(.03);
}
async function setPosition(page: Page, rate: number, position: number) {
  await page.getByLabel(/语音播放器$/).evaluate(async (audio: HTMLAudioElement, value) => {
    audio.pause(); audio.playbackRate = value.rate;
    const seeked = new Promise<void>(resolve => audio.addEventListener('seeked', () => resolve(), { once: true }));
    audio.currentTime = value.position; await seeked; await audio.play();
  }, { rate, position });
}
async function samples(page: Page, mapping: [string, { time: number; segment: number }][], count: number): Promise<Sample[]> {
  return page.evaluate(async ({ mapping, count }) => {
    const codes = Object.fromEntries(mapping), rows: Sample[] = [];
    const audio = document.querySelector('audio[aria-label$="语音播放器"]') as HTMLAudioElement;
    const stage = document.querySelector('.avatar-stage')!;
    await new Promise<void>(resolve => {
      const tick = () => {
        const open = stage.getAttribute('data-mouth-open') ?? '', code = codes[open];
        const radius = stage.querySelector('ellipse[cy="156"]')?.getAttribute('ry');
        rows.push({ wall: performance.now(), mediaTime: audio.currentTime, frameTime: code?.time ?? null,
          frameSegment: code?.segment ?? null, lagMs: code ? (audio.currentTime - code.time) * 1000 : null,
          open, radiusY: radius === undefined ? null : Number(radius), paused: audio.paused,
          ended: audio.ended, seeking: audio.seeking, readyState: audio.readyState,
          rate: audio.playbackRate, speaking: stage.classList.contains('speaking'), src: audio.getAttribute('src') ?? '' });
        if (rows.length < count) requestAnimationFrame(tick); else resolve();
      }; requestAnimationFrame(tick);
    }); return rows;
  }, { mapping, count });
}
function clockGate(rows: Sample[]) {
  const active = rows.slice(2).filter(row => !row.paused && !row.ended && !row.seeking);
  const lag = active.filter(row => row.lagMs !== null).map(row => Math.abs(row.lagMs!)).sort((a, b) => a - b);
  const p95 = lag[Math.max(0, Math.ceil(lag.length * .95) - 1)] ?? Infinity;
  const max = lag.at(-1) ?? Infinity;
  const geometry = active.every(row => Number(row.open) <= .04 ? row.radiusY === null
    : row.radiusY !== null && Math.abs(row.radiusY - (2 + Number(row.open) * 15)) <= .01);
  return { activeSamples: active.length, unmapped: active.length - lag.length, p95AbsoluteLagMs: p95,
    maxAbsoluteLagMs: max, svgGeometryMatches: geometry,
    passed: active.length >= 30 && lag.length === active.length && p95 <= 50 && max <= 100 && geometry
      && active.at(-1)!.mediaTime > active[0].mediaTime };
}
async function mediaEvents(page: Page) {
  return page.evaluate(() => (window as typeof window & { __auditMediaEvents: unknown[] }).__auditMediaEvents);
}
test.beforeEach(() => { test.skip(process.env.AVATAR_E2E_PLAYBACK_AUDIT !== '1', 'explicit playback research opt-in'); test.setTimeout(0); });

test('measures actual media clock across rates seeks pause end and stop', async ({ page }, info) => {
  const file = artifact('clock', info), control = await oracle(page);
  const report = { ...file.provenance, scope: 'Actual Chromium decoded PCM and rendered SVG, synthetic timeline oracle only',
    cases: [] as { name: string; rows: Sample[]; gate: ReturnType<typeof clockGate> }[], controls: [] as Record<string, unknown>[],
    requests: control.requests, mediaEvents: [] as unknown[], completed: false, failure: null as string | null, physicalApproved: false };
  file.save(report);
  try {
    await open(page); await chat(page);
    expect(new Set(control.mapping.map(([key]) => key)).size).toBe(800);
    for (const [name, rate, position] of [['rate1', 1, .5], ['rate0.5', .5, 1], ['rate2', 2, 2], ['seek_forward', 1, 5], ['seek_backward', 1, .5]] as const) {
      await setPosition(page, rate, position); const rows = await samples(page, control.mapping, 48);
      report.cases.push({ name, rows, gate: clockGate(rows) }); file.save(report);
    }
    const pauseWall = await page.getByLabel(/语音播放器$/).evaluate((a: HTMLAudioElement) => { const t = performance.now(); a.pause(); return t; });
    const paused = await samples(page, control.mapping, 6), closed = paused.findIndex(row => row.open === '0.000');
    const pausePass = closed >= 0 && closed < 2 && paused[closed].wall - pauseWall <= 100 && paused.every(row => row.paused);
    report.controls.push({ name: 'pause', rows: paused, firstClosedRaf: closed + 1, passed: pausePass }); file.save(report);
    await setPosition(page, 1, 7.85); const ending = await samples(page, control.mapping, 32);
    const endedAt = ending.findIndex(row => row.ended), afterEnd = ending.slice(Math.max(endedAt, 0));
    const endedPass = endedAt >= 0 && afterEnd.slice(2).every(row => row.open === '0.000' && !row.speaking);
    report.controls.push({ name: 'ended', rows: ending, passed: endedPass });
    await page.getByRole('button', { name: '停止播放', exact: true }).click();
    const stopped = await samples(page, control.mapping, 6), stopPass = stopped.every(row => row.src === '' && row.open === '0.000' && !row.speaking);
    report.controls.push({ name: 'stop', rows: stopped, passed: stopPass }); file.save(report);
    expect(report.cases.every(item => item.gate.passed)).toBe(true); expect(pausePass && endedPass && stopPass).toBe(true);
    report.completed = true;
    await page.screenshot({ path: join(file.folder, 'clock.png') });
  } catch (error) { report.failure = String(error); throw error; }
  finally { report.mediaEvents = await mediaEvents(page).catch(() => []); file.save(report); }
});

test('plays all final segments in order with fresh clocks', async ({ page }, info) => {
  const file = artifact('segments', info), control = await oracle(page, true);
  const report = { ...file.provenance, scope: 'Actual media playback of three final controlled segments, no real TTS/model quality',
    rows: [] as Sample[], requests: control.requests, mediaEvents: [] as unknown[], completed: false, failure: null as string | null };
  file.save(report);
  try {
    await open(page); await chat(page, true); report.rows = await samples(page, control.mapping, 480); file.save(report);
    expect(control.requests.map(row => row.text).join('')).toBe(readFileSync('../evals/interaction/cycle-08/final-three-segments.txt', 'utf8').trim());
    expect(control.requests).toHaveLength(3); expect(control.requests.every(row => row.headerToken)).toBe(true);
    const seen = [...new Set(report.rows.filter(row => !row.paused && row.frameSegment !== null).map(row => row.frameSegment))];
    expect(seen).toEqual([1, 2, 3]);
    expect(report.rows.slice(-6).every(row => row.ended && row.open === '0.000' && !row.speaking)).toBe(true);
    report.completed = true;
  } catch (error) { report.failure = String(error); throw error; }
  finally { report.mediaEvents = await mediaEvents(page).catch(() => []); file.save(report); }
});

test('stop during prefetch survives injected queued play and late completion', async ({ page }, info) => {
  const file = artifact('prefetch-stop', info), control = await oracle(page, true, true);
  const report = { ...file.provenance, scope: 'Controlled queued-event injection after real playback release; no natural incidence claim',
    injectedPlayEvent: true, rows: [] as Sample[], requests: control.requests, cancels: control.cancels,
    mediaEvents: [] as unknown[], completed: false, failure: null as string | null };
  file.save(report);
  try {
    await open(page); await chat(page, true); await expect.poll(() => control.requests.length).toBe(2);
    await page.getByRole('button', { name: '停止播放', exact: true }).click();
    await page.getByLabel(/语音播放器$/).evaluate((a: HTMLAudioElement) => a.dispatchEvent(new Event('play')));
    control.releaseSecond(); report.rows = await samples(page, control.mapping, 60); file.save(report);
    expect(report.rows.every(row => row.src === '' && row.open === '0.000' && !row.speaking)).toBe(true);
    expect(control.requests).toHaveLength(2); expect(control.cancels.length).toBeGreaterThan(0); report.completed = true;
  } catch (error) { report.failure = String(error); throw error; }
  finally { control.releaseSecond(); report.mediaEvents = await mediaEvents(page).catch(() => []); file.save(report); }
});
