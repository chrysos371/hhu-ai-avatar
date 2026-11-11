import { test, expect, type Page, type CDPSession } from '@playwright/test';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const token = 'mission-control-disposable-e2e-token';
const draft = 'draft-0123456789-abcdefgh';
type ClockRow = { wall: number; media: number; lag: number | null; open: string; radius: number | null;
  paused: boolean; ended: boolean; seeking: boolean };
type InputRow = { start: number; end: number; insertedValue: string; renderedValue: string; media: number };
type Instrument = { decisions: number; inputRows: InputRow[] };
type Scope = typeof window & { __historyAudit: Instrument };
const digest = (path: string) => createHash('sha256').update(readFileSync(path)).digest('hex');
const p95 = (values: number[]) => [...values].sort((a, b) => a - b)[Math.ceil(values.length * .95) - 1] ?? Infinity;

function pcm() {
  const bytes = Buffer.alloc(44 + 8 * 16000 * 2);
  bytes.write('RIFF', 0); bytes.writeUInt32LE(bytes.length - 8, 4); bytes.write('WAVEfmt ', 8);
  bytes.writeUInt32LE(16, 16); bytes.writeUInt16LE(1, 20); bytes.writeUInt16LE(1, 22);
  bytes.writeUInt32LE(16000, 24); bytes.writeUInt32LE(32000, 28); bytes.writeUInt16LE(2, 32);
  bytes.writeUInt16LE(16, 34); bytes.write('data', 36); bytes.writeUInt32LE(bytes.length - 44, 40);
  for (let i = 0; i < 8 * 16000; i++) bytes.writeInt16LE(Math.round(.1 * 32767 * Math.sin(2 * Math.PI * 220 * i / 16000)), 44 + 2 * i);
  return bytes;
}
async function resources(page: Page, cdp: CDPSession) {
  for (let i = 0; i < 3; i++) await cdp.send('HeapProfiler.collectGarbage');
  const result = await cdp.send('Performance.getMetrics');
  return { metrics: Object.fromEntries(result.metrics.map((row: { name: string; value: number }) => [row.name, row.value])),
    counters: await cdp.send('Memory.getDOMCounters'),
    dom: await page.evaluate(() => ({ elements: document.querySelectorAll('*').length,
      messages: document.querySelectorAll('.chat-message').length,
      closedPre: document.querySelectorAll('.trace:not([open]) pre').length,
      traceTextChars: [...document.querySelectorAll('.trace pre')].reduce((n, node) => n + (node.textContent?.length ?? 0), 0) })) };
}
async function position(page: Page, rate: number, at: number) {
  await page.getByLabel(/语音播放器$/).evaluate(async (audio: HTMLAudioElement, args) => {
    audio.pause(); audio.playbackRate = args.rate;
    const seeked = new Promise<void>(resolve => audio.addEventListener('seeked', () => resolve(), { once: true }));
    audio.currentTime = args.at; await seeked; await audio.play();
    await new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
  }, { rate, at });
}
async function sample(page: Page): Promise<ClockRow[]> {
  return page.evaluate(async () => {
    const mapping = Object.fromEntries(Array.from({ length: 800 }, (_, i) => [((i + 1) / 801).toFixed(3), i * .01]));
    const audio = document.querySelector('audio[aria-label$="语音播放器"]') as HTMLAudioElement;
    const stage = document.querySelector('.avatar-stage')!, rows: ClockRow[] = [];
    await new Promise<void>(resolve => {
      const tick = () => {
        const open = stage.getAttribute('data-mouth-open') ?? '', at = mapping[open];
        const radius = stage.querySelector('ellipse[cy="156"]')?.getAttribute('ry');
        rows.push({ wall: performance.now(), media: audio.currentTime, lag: at === undefined ? null : (audio.currentTime - at) * 1000,
          open, radius: radius === undefined ? null : Number(radius), paused: audio.paused, ended: audio.ended, seeking: audio.seeking });
        if (rows.length < 48) requestAnimationFrame(tick); else resolve();
      }; requestAnimationFrame(tick);
    }); return rows;
  });
}
function clockGate(rows: ClockRow[]) {
  const active = rows.slice(2).filter(row => !row.paused && !row.ended && !row.seeking);
  const lag = active.filter(row => row.lag !== null).map(row => Math.abs(row.lag!));
  const geometry = active.every(row => Number(row.open) <= .04 ? row.radius === null
    : row.radius !== null && Math.abs(row.radius - (2 + Number(row.open) * 15)) <= .01);
  return { samples: active.length, unmapped: active.length - lag.length, p95Ms: p95(lag), maxMs: Math.max(...lag), geometry,
    passed: active.length >= 30 && lag.length === active.length && p95(lag) <= 50 && Math.max(...lag) <= 100 && geometry
      && active.at(-1)!.media > active[0].media };
}

test('audits full chat history input diagnostics playback and navigation resources', async ({ page, context }, info) => {
  test.skip(process.env.AVATAR_E2E_HISTORY_AUDIT !== '1', 'explicit full-history research opt-in');
  test.setTimeout(0);
  const folder = process.env.AVATAR_E2E_EVIDENCE_DIR ?? info.outputDir; mkdirSync(folder, { recursive: true });
  const path = join(folder, 'history.json'); if (existsSync(path)) throw Error('Use fresh history evidence path');
  const sources = ['src/features/chat/ChatPage.tsx', 'src/features/chat/useSpeechPlayer.ts', 'src/features/chat/AvatarStage.tsx',
    'src/features/chat/SpeechAvatarStage.tsx', 'src/features/chat/speechFrames.ts', 'e2e/history-audit.spec.ts',
    '../tests/helpers/serve_admin_e2e.py', '../src/avatar/lab/transport_fixture.py', '../evals/interaction/cycle-10/history-protocol.json'];
  for (const optional of ['src/features/chat/ChatMessage.tsx', 'src/features/chat/ChatTrace.tsx']) if (existsSync(optional)) sources.push(optional);
  const report = { head: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(),
    startedUtc: new Date().toISOString(), elapsedSeconds: 0,
    scope: 'Full production ChatPage, real local HTTP/SSE controlled provider, disposable DB, actual PCM playback with intercepted speech oracle; no real model or physical/multi-day approval',
    sourceSha256: Object.fromEntries(sources.map(p => [p, digest(p)])),
    servedBundleSha256: Object.fromEntries(['dist/index.html', ...readdirSync('dist/assets').filter(p => p.endsWith('.js')).map(p => 'dist/assets/' + p)].map(p => [p, digest(p)])),
    turns: [] as { id: string; text: string; result?: any; streamError?: string }[],
    checkpoints: [] as any[], initial: null as unknown, afterNavigation: null as unknown,
    violations: [] as string[], errors: [] as string[], allCheckpointsObserved: false, completed: false, failure: null as string | null };
  const started = Date.now(), pending: Promise<void>[] = [];
  const save = () => { report.elapsedSeconds = (Date.now() - started) / 1000; writeFileSync(path, JSON.stringify(report, null, 2) + '\n'); };
  save();
  page.on('pageerror', error => report.errors.push(error.message));
  page.on('request', request => {
    if (new URL(request.url()).pathname === '/api/v1/turns' && request.method() === 'POST') {
      const body = request.postDataJSON(); report.turns.push({ id: body.request_id, text: body.text });
    }
  });
  page.on('response', response => {
    if (!/\/api\/v1\/turns\/[^/]+\/events$/.test(new URL(response.url()).pathname)) return;
    const job = new URL(response.url()).pathname.split('/').at(-2)!;
    pending.push((async () => {
      const row = report.turns.find(row => row.id === job); if (!row) throw Error('Missing matching submitted turn');
      try {
        const body = await response.text();
        for (const block of body.split(/\r?\n\r?\n/)) if (block.startsWith('event: result\n')) {
          row.result = JSON.parse(block.split('\n').find(line => line.startsWith('data:'))!.slice(5));
        }
      } catch (error) { row.streamError = String(error); }
    })());
  });
  await page.addInitScript(() => {
    const scope = window as Scope; scope.__historyAudit = { decisions: 0, inputRows: [] };
    const original = JSON.stringify;
    JSON.stringify = function(value: unknown, ...args: any[]) {
      if (value && typeof value === 'object' && 'speech_rate' in value && 'mouth_intensity' in value) scope.__historyAudit.decisions++;
      return Reflect.apply(original, JSON, [value, ...args]);
    };
    document.addEventListener('input', event => {
      const input = event.target as HTMLTextAreaElement; if (input.id !== 'chat-message') return;
      const record: InputRow = { start: performance.now(), end: 0, insertedValue: input.value, renderedValue: '', media: 0 };
      scope.__historyAudit.inputRows.push(record);
      requestAnimationFrame(() => {
        record.end = performance.now(); record.renderedValue = input.value;
        record.media = (document.querySelector('audio[aria-label$="语音播放器"]') as HTMLAudioElement).currentTime;
      });
    }, true);
  });
  const bytes = pcm();
  await page.route('**/api/v1/speech', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data: {
    audio_id: 'history_audit_pcm_identifier', duration: 8, warning: null,
    frames: Array.from({ length: 800 }, (_, i) => ({ time: i * .01, mouth_open: (i + 1) / 801, vowel: 'a', energy: 1 })),
  }, error: null }) }));
  await page.route('**/api/v1/speech/audio/*', route => route.fulfill({ status: 200, contentType: 'audio/wav', body: bytes }));
  const cdp = await context.newCDPSession(page); await cdp.send('Performance.enable');
  try {
    await page.goto('/chat#' + token);
    await expect(page.getByRole('heading', { name: '对话观测', exact: true })).toBeVisible();
    await expect(page.getByLabel(/语音播放器$/)).toBeAttached();
    report.initial = await resources(page, cdp); save();
    for (let turn = 1; turn <= 100; turn++) {
      await page.getByLabel('消息', { exact: true }).fill(`这是第${turn}次界面负载回合，请继续。`);
      await page.getByRole('button', { name: '发送消息', exact: true }).click();
      await expect(page.locator('.chat-message.assistant details')).toHaveCount(turn);
      await expect(page.getByRole('button', { name: '发送消息', exact: true })).toBeDisabled();
      await Promise.all(pending); save();
      if (![1, 25, 100].includes(turn)) continue;
      const entry: any = { replies: turn, closed: await resources(page, cdp), clocks: [], input: null, trace: null, stopped: null };
      report.checkpoints.push(entry); save();
      await page.getByRole('button', { name: '朗读回复', exact: true }).last().click();
      await expect.poll(() => page.getByLabel(/语音播放器$/).evaluate((audio: HTMLAudioElement) => audio.currentTime)).toBeGreaterThan(.03);
      await position(page, 1, .5);
      await page.evaluate(() => { (window as Scope).__historyAudit = { decisions: 0, inputRows: [] }; });
      const playing = sample(page);
      for (const char of draft) {
        await page.getByLabel('消息', { exact: true }).press('End');
        await page.keyboard.insertText(char);
        await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => resolve())));
      }
      const rows = await playing, stats = await page.evaluate(() => (window as Scope).__historyAudit);
      entry.clocks.push({ rate: 1, typing: true, rows, gate: clockGate(rows) });
      const inputValues = stats.inputRows.length === draft.length && stats.inputRows.every((r, i) => r.end > 0
        && r.renderedValue === draft.slice(0, i + 1) && r.insertedValue === r.renderedValue);
      entry.input = { ...stats, valuesMatch: inputValues, p95NextRafMs: p95(stats.inputRows.map(row => row.end - row.start)) };
      if (!inputValues || entry.input.p95NextRafMs > 100) report.violations.push(`${turn}: input integrity/next-RAF gate`);
      if (stats.decisions !== 0) report.violations.push(`${turn}: ${stats.decisions} closed-trace decision serializations during typing`);
      if (entry.closed.dom.closedPre !== 0) report.violations.push(`${turn}: ${entry.closed.dom.closedPre} closed-trace pre nodes`);
      if (report.turns.length !== turn || await page.locator('.chat-message.user').count() !== turn
        || await page.locator('.chat-message.assistant').count() !== turn) report.violations.push(`${turn}: message/request counts`);
      await position(page, 2, 2); const faster = await sample(page);
      entry.clocks.push({ rate: 2, typing: false, rows: faster, gate: clockGate(faster) });
      for (const clock of entry.clocks) if (!clock.gate.passed) report.violations.push(`${turn}: rate${clock.rate} clock gate`);
      const detail = page.locator('.chat-message.assistant details').last();
      await detail.locator('summary').click(); await expect(detail.locator('pre')).toHaveCount(5);
      const decision = await detail.locator('pre').first().textContent();
      entry.trace = { openPre: await detail.locator('pre').count(), decisionMatches: decision !== null
        && JSON.stringify(JSON.parse(decision)) === JSON.stringify(report.turns.at(-1)?.result?.trace.decision) };
      if (!entry.trace.decisionMatches) report.violations.push(`${turn}: opened decision differs from delivered trace`);
      await detail.locator('summary').click();
      await page.getByRole('button', { name: '停止播放', exact: true }).click();
      entry.stopped = await page.getByLabel(/语音播放器$/).evaluate((audio: HTMLAudioElement) => ({ src: audio.getAttribute('src'),
        mouth: document.querySelector('.avatar-stage')?.getAttribute('data-mouth-open') }));
      if (entry.stopped.src !== null || entry.stopped.mouth !== '0.000') report.violations.push(`${turn}: stop release`);
      await page.getByLabel('消息', { exact: true }).fill(''); save();
    }
    report.allCheckpointsObserved = true;
    // SPA navigation is required: a document reload would hide component cleanup.
    await page.getByRole('link', { name: '工具', exact: true }).click();
    await expect(page.getByRole('heading', { name: '工具', exact: true })).toBeVisible();
    await page.getByRole('link', { name: '对话观测', exact: true }).click();
    await expect(page.getByRole('heading', { name: '开始一段对话', exact: true })).toBeVisible();
    report.afterNavigation = await resources(page, cdp);
    await Promise.all(pending);
    if (report.turns.length !== 100 || report.turns.some(turn => !turn.result || turn.streamError)) report.violations.push('100 complete HTTP/SSE results');
    if (report.errors.length) report.violations.push('page errors');
    save();
    expect(report.violations).toEqual([]); report.completed = true;
    await page.screenshot({ path: join(folder, 'history-after-navigation.png') });
  } catch (error) { report.failure = String(error); throw error; }
  finally { await Promise.allSettled(pending); save(); await cdp.detach(); }
});
