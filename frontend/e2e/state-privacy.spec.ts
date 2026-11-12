import { expect, test } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
const protocol = JSON.parse(readFileSync(new URL('../../evals/interaction/cycle-36/maintained-state-privacy-protocol.json', import.meta.url), 'utf8')) as {
  scope: string; preparation: Record<'emotion' | 'dashboard', string>; fixed_observation_ms: number;
};

const token = 'mission-control-disposable-e2e-token';
for (const which of ['emotion', 'dashboard'] as const) {
  test(`${which} drops source-derived state after independent confirmed erasure`, async ({ page }, info) => {
    test.skip(Boolean(process.env.AVATAR_E2E_LLM_PROVIDER || process.env.AVATAR_E2E_REMINDER_DELIVERY_CASE),
      'This default regression requires the exact controlled cognitive fixture, not a model or reminder-only fixture.');
    const report: any = { scope: protocol.scope, page: which, completed: false, failure: null,
      head: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(),
      fixedObservationMs: protocol.fixed_observation_ms, calls: [], errors: [], versionRequests: [],
      nativeOrGpuClaim: false, noReloadNavigationOrUiPrivacyNoticeAfterErasure: true };
    const output = info.outputPath('state-privacy-evidence.json');
    page.on('pageerror', error => report.errors.push(error.message));
    page.on('request', request => {
      if (request.url().includes('/conversation/changes?')) report.versionRequests.push(new URL(request.url()).search);
    });
    const api = async (path: string, data?: unknown) => {
      const response = await page.request.fetch('/api/v1' + path, { method: data === undefined ? 'GET' : 'POST',
        headers: { 'X-Avatar-Token': token }, data });
      const body = await response.json();
      const logged = structuredClone(body);
      if (logged.data?.confirmation_token) logged.data.confirmation_token = '[ephemeral fixture capability omitted]';
      report.calls.push({ path, status: response.status(), response: logged });
      expect(response.ok()).toBe(true);
      return body.data;
    };
    const confirm = async (draft: any) => api('/operations/' + draft.draft_id + '/confirm',
      { confirmation_token: draft.confirmation_token });
    const role = () => page.locator('article').filter({ has: page.getByRole('heading', { name: '角色自动状态', exact: true }) });
    const values = () => which === 'emotion' ? page.locator('.grid.three .metric-number') : role().locator('p.muted');
    try {
      // Other default tests share only this disposable fixture. Remove its prior
      // explicit override via the same public draft/confirm contract.
      if ((await api('/emotion')).override) await confirm(await api('/emotion/draft', { clear: true, reason: 'C36隔离默认回归前的覆盖' }));
      const text = protocol.preparation[which];
      const prepared = await api('/chat', { text });
      report.prepared = prepared;
      expect(prepared.analysis_mode).toBe('llm'); // Controlled HTTP fixture, never native model evidence.
      expect(prepared.user_arousal).toBe(.4);
      const name = which === 'emotion' ? '缓存小岚' : '缓存小川';
      const memories = await api('/memory?q=' + encodeURIComponent(name));
      const fragment = memories.find((row: any) => row.content.includes(name));
      expect(fragment).toBeTruthy();
      expect(fragment.confirmation_status).toBe('source_backed');
      const inspected = await api('/memory/' + fragment.id);
      expect(inspected.sources.some((source: any) => source.source_message_id === prepared.conversation.user_message_id)).toBe(true);
      report.fragment = inspected;
      await page.goto((which === 'emotion' ? '/emotion' : '/') + '#' + token);
      await values().first().waitFor();
      report.beforeDom = await values().allTextContents();
      report.beforeApi = await api('/' + which);
      const before = report.beforeApi.automatic ?? report.beforeApi.emotion;
      expect(before.arousal).not.toBe(0);
      expect(report.beforeDom.join('')).toContain(before.arousal.toFixed(2));
      await confirm(await api('/memory/batch-draft', { actions: [{ action: 'forget', id: fragment.id }] }));
      const boundary = performance.now();
      report.afterApi = await api('/' + which);
      const automatic = report.afterApi.automatic ?? report.afterApi.emotion;
      expect(automatic.valence).toBe(0); expect(automatic.arousal).toBe(0);
      expect(report.afterApi.context.revision).toBe(report.beforeApi.context.revision + 1);
      const conversation = await api('/conversation');
      const source = conversation.items.find((row: any) => row.id === prepared.conversation.user_message_id);
      expect(source.redacted).toBe(true);
      report.sourceAfter = source;
      await page.waitForTimeout(protocol.fixed_observation_ms);
      report.sampleMs = performance.now() - boundary;
      report.fixedDom = await values().allTextContents();
      // Snapshot assertions are deliberately not retrying until a later poll.
      if (which === 'emotion') {
        expect(report.fixedDom.map((v: string) => v.replace(/\s/g, ''))).toEqual(['P0.00/A0.00', 'P0.00/A0.00', 'P0.00/A0.00']);
        report.form = { valence: await page.locator('#override-valence').inputValue(), arousal: await page.locator('#override-arousal').inputValue() };
        expect(report.form).toEqual({ valence: '0', arousal: '0' });
      } else {
        expect(report.fixedDom.map((v: string) => v.replace(/\s/g, ''))).toEqual(['愉悦度0.00·唤醒度0.00']);
        expect(await page.locator('article').filter({ has: page.getByRole('heading', { name: '最近对话事件', exact: true }) }).locator('tbody tr').count()).toBe(0);
      }
      expect(report.errors).toEqual([]);
      await page.screenshot({ path: info.outputPath('state-privacy-fixed.png') });
      report.completed = true;
    } catch (error) { report.failure = String(error); throw error; }
    finally {
      writeFileSync(output, JSON.stringify(report, null, 2) + '\n');
      await info.attach('state-privacy-evidence', { path: output, contentType: 'application/json' });
    }
  });
}
