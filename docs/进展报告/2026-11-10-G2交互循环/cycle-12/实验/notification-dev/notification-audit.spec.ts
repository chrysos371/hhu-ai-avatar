import { test, expect, type Page } from '@playwright/test';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const token = 'mission-control-disposable-e2e-token';
const hash = (p: string) => createHash('sha256').update(readFileSync(p)).digest('hex');
test('notification loss, reconnect, natural fact updates, playback and streaming erasure', async ({ page }, info) => {
  test.skip(process.env.AVATAR_E2E_NOTIFICATION_AUDIT !== '1', 'explicit version-notification fault audit'); test.setTimeout(0);
  const folder = process.env.AVATAR_E2E_EVIDENCE_DIR ?? info.outputDir; mkdirSync(folder, { recursive: true });
  const file = join(folder, 'notification.json'); if (existsSync(file)) throw Error('Use fresh evidence directory');
  const sources = ['src/lib/conversationWatch.ts', 'src/features/chat/useChatHistory.ts', 'src/features/chat/ChatPage.tsx',
    'src/features/chat/useSpeechPlayer.ts', '../src/avatar/web.py', '../src/avatar/conversation_changes.py',
    '../tests/helpers/serve_admin_e2e.py', '../src/avatar/lab/transport_fixture.py', 'e2e/notification-audit.spec.ts',
    '../evals/interaction/cycle-12/notification-protocol.json'];
  const report: any = { head: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(),
    scope: 'One browser, real local HTTP/SSE/PCM, controlled provider; watch-only routed faults, no human or semantic approval',
    sourceSha256: Object.fromEntries(sources.map(p => [p, hash(p)])),
    servedBundleSha256: Object.fromEntries(['dist/index.html', ...readdirSync('dist/assets').filter(p => p.endsWith('.js')).map(p => 'dist/assets/' + p)].map(p => [p, hash(p)])),
    requests: [], steps: [], errors: [], completed: false, failure: null };
  const save = () => writeFileSync(file, JSON.stringify(report, null, 2) + '\n'); save();
  page.on('pageerror', error => report.errors.push(error.message));
  page.on('request', request => {
    const path = new URL(request.url()).pathname;
    if (path.endsWith('/changes') || path.endsWith('/conversation') || path.endsWith('/turns')) {
      report.requests.push({ path, method: request.method(), wall: Date.now(),
        ...(path.endsWith('/turns') ? { id: request.postDataJSON().request_id } : {}) }); save();
    }
  });
  const api = async (path: string, data?: unknown) => {
    const response = await page.request[data === undefined ? 'get' : 'post']('/api/v1' + path,
      { headers: { 'X-Avatar-Token': token }, ...(data === undefined ? {} : { data }) });
    expect(response.ok()).toBe(true); return (await response.json()).data;
  };
  const ready = () => expect(page.locator('.chat-history')).toHaveAttribute('data-history-ready', 'true');
  const send = async (text: string) => {
    await ready(); const count = await page.locator('.chat-message.assistant').count();
    await page.getByLabel('消息', { exact: true }).fill(text);
    await page.getByRole('button', { name: '发送消息', exact: true }).click();
    await expect(page.locator('.chat-message.assistant')).toHaveCount(count + 1);
    await expect(page.locator('.chat-message.assistant').last().getByRole('button', { name: '朗读回复', exact: true })).toBeVisible();
    await ready();
  };
  const erase = async (id: number) => {
    const draft = await api('/memory/batch-draft', { actions: [{ action: 'forget', id }] });
    return api('/operations/' + draft.draft_id + '/confirm', { confirmation_token: draft.confirmation_token });
  };
  const latestJob = async () => {
    const id = report.requests.filter((row: any) => row.path.endsWith('/turns')).at(-1).id;
    return api('/turns/' + id);
  };
  try {
    await page.goto('/chat#' + token); await ready();
    const before = await api('/conversation');
    for (const name of ['版本甲', '版本乙']) {
      await send('我叫' + name);
      const facts = await api('/memory'), snapshot = await api('/conversation'), job = await latestJob();
      expect(job.status).toBe('completed'); expect(snapshot.revision).toBe(before.revision);
      expect(facts.some((fact: any) => fact.content.includes(name))).toBe(true);
      report.steps.push({ name: 'natural-fact-' + name, facts, snapshot, job }); save();
    }

    // Fail only the watch. Ordinary authenticated snapshot reads remain available.
    let first = true, broken = true, release!: () => void;
    let cursor = await api('/conversation');
    await page.route('**/api/v1/conversation/changes?*', async route => {
      if (first) { first = false; await new Promise<void>(resolve => { release = resolve; }); }
      if (broken) return route.abort('failed');
      return route.fulfill({ json: { data: { instance_id: cursor.instance_id, revision: cursor.revision }, error: null, request_id: 'controlled-reconnect' } });
    });
    await page.reload(); await ready();
    await expect.poll(() => !!release).toBe(true); release();
    await expect(page.getByText(/版本同步暂不可用/)).toBeVisible();
    await expect(page.locator('.chat-message')).toHaveCount(0);
    const postCount = report.requests.filter((row: any) => row.method === 'POST' && row.path.endsWith('/turns')).length;
    await page.evaluate(() => window.dispatchEvent(new Event('focus')));
    await page.getByRole('button', { name: '刷新对话记录', exact: true }).click();
    await expect(page.locator('.chat-history')).toHaveAttribute('data-history-ready', 'false');
    await expect(page.locator('.chat-message')).toHaveCount(0);
    report.steps.push({ name: 'outage-paused-even-after-refresh', messages: await page.locator('.chat-message').count() }); save();
    cursor = await api('/conversation'); broken = false;
    // Fulfill just one reconnect; let subsequent requests use the real server.
    await expect(page.locator('.chat-message')).toHaveCount(cursor.items.length); await ready();
    await page.unroute('**/api/v1/conversation/changes?*');
    await page.reload(); await ready();
    expect(report.requests.filter((row: any) => row.method === 'POST' && row.path.endsWith('/turns')).length).toBe(postCount);
    report.steps.push({ name: 'same-version-recovery-no-turn-replay', revision: cursor.revision, messageCount: cursor.items.length }); save();

    // Actual PCM playback must stop on erasure without a frontend privacy event.
    await send('我叫播放丙');
    const fact = (await api('/memory')).find((row: any) => row.content.includes('播放丙')); expect(fact).toBeTruthy();
    await page.locator('.chat-message.assistant').last().getByRole('button', { name: '朗读回复', exact: true }).click();
    const audio = page.getByLabel('小海语音播放器', { exact: true });
    await expect.poll(() => audio.evaluate((node: HTMLAudioElement) => !node.paused && node.currentTime > 0)).toBe(true);
    report.steps.push({ name: 'playing-before-erase', audio: await audio.evaluate((node: HTMLAudioElement) => ({ paused: node.paused, time: node.currentTime, src: node.currentSrc })) }); save();
    await erase(fact.id);
    await expect.poll(() => audio.evaluate((node: HTMLAudioElement) => node.paused && !node.getAttribute('src'))).toBe(true);
    await expect(page.locator('.trace')).toHaveCount(0); await ready();
    report.steps.push({ name: 'external-erase-stops-playback', audio: await audio.evaluate((node: HTMLAudioElement) => ({ paused: node.paused, time: node.currentTime, src: node.getAttribute('src') })), snapshot: await api('/conversation') }); save();

    // A partial long reply is really observed before the independent erasure.
    await send('我叫生成丁');
    const streamFact = (await api('/memory')).find((row: any) => row.content.includes('生成丁')); expect(streamFact).toBeTruthy();
    await page.getByLabel('消息', { exact: true }).fill('fixture-long 通知审计');
    await page.getByRole('button', { name: '发送消息', exact: true }).click();
    const last = page.locator('.chat-message.assistant').last();
    await expect.poll(() => last.locator(':scope > div').textContent()).not.toBe('');
    const draft = await last.locator(':scope > div').textContent(); expect(await latestJob()).toMatchObject({ status: 'running' });
    await erase(streamFact.id);
    await expect.poll(async () => (await latestJob()).status).toBe('cancelled'); await ready();
    const snapshot = await api('/conversation');
    expect(snapshot.items.at(-1).role).toBe('user');
    expect(snapshot.items.some((row: any) => row.role === 'assistant' && row.text === draft)).toBe(false);
    await expect(page.getByRole('button', { name: '停止生成', exact: true })).toHaveCount(0);
    report.steps.push({ name: 'external-erase-cancels-actual-partial-turn', draft, job: await latestJob(), snapshot }); save();
    expect(report.errors).toEqual([]); report.completed = true;
  } catch (error) { report.failure = String(error); throw error; }
  finally { save(); await page.screenshot({ path: join(folder, 'notification-final.png') }).catch(() => {}); }
});
