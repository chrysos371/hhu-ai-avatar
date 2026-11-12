import { test, expect } from '@playwright/test';
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';

const token = 'mission-control-disposable-e2e-token';
const scenario = process.env.AVATAR_E2E_REMINDER_DELIVERY_CASE;
test('reminder claim response and actual page presentation baseline', async ({ page }, info) => {
  test.skip(!scenario, 'explicit isolated reminder delivery baseline only');
  test.setTimeout(0);
  if (!['normal_claim', 'response_drop_after_commit', 'navigation_before_response'].includes(scenario!)) {
    throw Error('Unregistered reminder case');
  }
  const folder = process.env.AVATAR_E2E_EVIDENCE_DIR ?? info.outputDir;
  mkdirSync(folder, { recursive: true });
  const output = join(folder, 'reminder-browser.json');
  if (existsSync(output)) throw Error('Use fresh evidence output');
  const files = (path: string): string[] => readdirSync(path, { withFileTypes: true }).flatMap(entry =>
    entry.isDirectory() ? files(join(path, entry.name)) : [join(path, entry.name)]);
  const inputs = [...files('src'), ...files('../src/avatar').filter(p => p.endsWith('.py')), ...files('dist'),
    'e2e/reminder-delivery-audit.spec.ts', '../tests/helpers/serve_admin_e2e.py'];
  const report: Record<string, unknown> = {
    case: scenario, scope: 'Actual Chromium/HTTP/SQLite, controlled response faults and real page poll timer; no model/physical notification/human perception.',
    head: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(), completed: false,
    sourceSha256: Object.fromEntries(inputs.map(p => [p, createHash('sha256').update(readFileSync(p)).digest('hex')])),
    virtualClock: false,
  };
  const errors: string[] = [];
  const failedRequests: { url: string; error: string | null }[] = [];
  const postRequests: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('requestfailed', request => failedRequests.push({ url: request.url(), error: request.failure()?.errorText ?? null }));
  page.on('request', request => { if (request.method() === 'POST') postRequests.push(new URL(request.url()).pathname); });
  const save = () => writeFileSync(output, JSON.stringify(report, null, 2) + '\n');
  save();
  const apiList = async () => {
    const response = await page.request.get('/api/v1/reminders', { headers: { 'X-Avatar-Token': token } });
    expect(response.ok()).toBe(true);
    return (await response.json()).data;
  };
  const title = '到期投递实验提醒';
  const notice = () => page.locator('.notice[role="status"]').filter({ hasText: '到期提醒' });
  const row = () => page.getByRole('row').filter({ hasText: title });
  const upstream: unknown[] = [];
  let released = false;
  let release!: () => void;
  const paused = new Promise<void>(resolve => { release = () => { released = true; resolve(); }; });
  let fulfilled = 0;
  await page.route('**/api/v1/reminders/due', async route => {
    const response = await route.fetch();
    const data = await response.json();
    const index = upstream.length;
    upstream.push(data);
    if (index === 0 && scenario === 'response_drop_after_commit') {
      await route.abort('failed');
    } else {
      if (index === 0 && scenario === 'navigation_before_response') await paused;
      await route.fulfill({ response });
    }
    fulfilled += 1;
  });
  try {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/reminders#' + token);
    await expect(page.getByRole('heading', { name: '提醒', exact: true })).toBeVisible();
    await expect(row()).toBeVisible();
    await expect(notice()).toHaveCount(0);
    report.initialList = await apiList(); save();
    await expect.poll(() => upstream.length, { timeout: 30000 }).toBe(1);
    report.firstUpstream = upstream[0];
    report.afterClaimList = await apiList(); save();
    const claimed = report.afterClaimList as { notified_at: number | null }[];
    expect(claimed).toHaveLength(1);
    expect(claimed[0].notified_at).not.toBeNull();
    if (scenario === 'navigation_before_response') {
      await page.getByRole('link', { name: '总览', exact: true }).click();
      await expect(page.getByRole('heading', { name: '总览', exact: true })).toBeVisible();
      report.navigatedBeforeResponseRelease = true;
      release();
      await expect.poll(() => fulfilled, { timeout: 15000 }).toBe(1);
      await page.getByRole('link', { name: '提醒', exact: true }).click();
      await expect(row()).toBeVisible();
      await expect(notice()).toHaveCount(0);
      report.firstNoticeVisible = false;
    } else if (scenario === 'normal_claim') {
      await expect(notice()).toBeVisible();
      report.firstNoticeVisible = true;
      report.firstNoticeText = await notice().innerText();
      await page.screenshot({ path: join(folder, 'notice-first.png'), fullPage: true });
      const before = postRequests.length;
      await page.getByRole('button', { name: '已看到', exact: true }).click();
      await expect(notice()).toHaveCount(0);
      report.dismissButtonAdditionalPostRequests = postRequests.length - before;
    } else {
      await expect.poll(() => fulfilled, { timeout: 15000 }).toBe(1);
      await expect(notice()).toHaveCount(0);
      report.firstNoticeVisible = false;
    }
    save();
    await page.reload();
    await expect(row()).toBeVisible();
    await expect(row()).toContainText('本机已提示');
    await expect(notice()).toHaveCount(0);
    await expect.poll(() => upstream.length, { timeout: 30000 }).toBe(2);
    await expect.poll(() => fulfilled, { timeout: 15000 }).toBe(2);
    await expect(notice()).toHaveCount(0);
    report.secondUpstream = upstream[1];
    expect((upstream[1] as { data: unknown[] }).data).toEqual([]);
    report.afterReloadNoticeVisible = await notice().isVisible();
    report.listLabelAfterReload = await row().innerText();
    report.finalList = await apiList();
    await page.screenshot({ path: join(folder, 'after-reload-desktop.png'), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: join(folder, 'after-reload-mobile.png'), fullPage: true });
    report.overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
    report.errors = errors;
    report.requestFailures = failedRequests;
    report.postRequests = postRequests;
    expect(errors).toEqual([]);
    expect(report.overflow).toBe(false);
    report.completed = true; save();
  } catch (error) {
    report.failure = String(error); report.errors = errors; report.requestFailures = failedRequests; save();
    throw error;
  } finally {
    if (!released) release();
  }
});
