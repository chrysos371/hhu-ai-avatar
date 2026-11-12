const fs = require('node:fs'), path = require('node:path');
const {execFileSync} = require('node:child_process');
const root = execFileSync('git', ['rev-parse', '--show-toplevel'], {cwd: __dirname, encoding: 'utf8'}).trim();
const {chromium, expect} = require(path.join(root, 'frontend/node_modules/@playwright/test'));
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
(async () => {
  const browser = await chromium.launch({channel: 'chromium', headless: true});
  const context = await browser.newContext({viewport: {width: 1440, height: 1000}});
  const page = await context.newPage();
  page.setDefaultTimeout(12000);
  const report = {id: input.id, page: input.page, completed: false, browser_version: browser.version(),
    node_version: process.version, errors: [], calls: [], version_requests: [], observations: {}, failure: null};
  page.on('pageerror', e => report.errors.push(e.message));
  page.on('request', r => { if(r.url().includes('/conversation/changes?')) report.version_requests.push(new URL(r.url()).search); });
  const query = async (route, data) => {
    const response = await page.request.fetch(input.base_url + route, {method: data === undefined ? 'GET' : 'POST', data,
      headers: {'X-Avatar-Token': input.token}});
    const raw = await response.text();
    const value = JSON.parse(raw);
    // Synthetic operation capabilities are not persisted in the public audit.
    const logged = structuredClone(value);
    if (logged.data?.confirmation_token) logged.data.confirmation_token = '[ephemeral capability omitted]';
    report.calls.push({route, payload: data?.confirmation_token ? {confirmation_token: '[omitted]'} : data ?? null,
      status: response.status(), response: logged});
    if (!response.ok()) throw Error('HTTP ' + response.status());
    return value.data ?? value;
  };
  const card = () => page.locator('article').filter({has: page.getByRole('heading', {name: '角色自动状态', exact: true})});
  const values = () => input.page === 'emotion' ? page.locator('.grid.three .metric-number') : card().locator('p.muted');
  const dom = async () => ({values: await values().allTextContents(), alerts: await page.getByRole('alert').allTextContents(),
    ...(input.page === 'emotion' && await page.locator('#override-valence').count() ? {form: {
      valence: await page.locator('#override-valence').inputValue(), arousal: await page.locator('#override-arousal').inputValue(),
      duration: await page.locator('#override-duration').inputValue(), reason: await page.locator('#override-reason').inputValue()}} : {})});
  const zero = async () => {
    await expect(values().first()).toHaveText(input.page === 'emotion' ? /P 0\.00 \/ A 0\.00/ : /愉悦度 0\.00 · 唤醒度 0\.00/);
  };
  let releaseOld, releaseMetadata;
  try {
    if (input.id.includes('manual_fields')) {
      const draft = await query('/api/v1/emotion/draft', {values: {valence: .6, arousal: -.1}, duration_seconds: 600, reason: 'C35独立人工表达'});
      await query('/api/v1/operations/' + draft.draft_id + '/confirm', {confirmation_token: draft.confirmation_token});
    }
    let heldOld = false, heldMetadata = 0, metadataMode = 'hold';
    const late = input.id.includes('late_old_response');
    if (late) {
      const oldGate = new Promise(resolve => releaseOld = resolve);
      await page.route('**/api/v1/' + input.page, async route => {
        if (heldOld) return route.continue();
        heldOld = true;
        const response = await route.fetch();
        report.held_old_response = JSON.parse(await response.text());
        await oldGate;
        try { await route.fulfill({response}); report.old_fulfillment = 'attempt_succeeded_at_route_layer'; }
        catch (error) { report.old_fulfillment = 'cancelled: ' + String(error); }
      });
    }
    const metaFault = input.id.includes('metadata'), broadcast = input.id.includes('broadcast');
    if (metaFault || broadcast) {
      const metadataGate = new Promise(resolve => releaseMetadata = resolve);
      await page.route('**/api/v1/conversation/changes?*', async route => {
        const bootstrap = new URL(route.request().url()).searchParams.get('instance_id') === 'state-bootstrap';
        if (bootstrap || metadataMode === 'recover') return route.continue();
        heldMetadata++;
        await metadataGate;
        if (broadcast) { try { await route.abort(); } catch {} return; }
        try { await route.fulfill({status: input.id.includes('403') ? 403 : 503, contentType: 'application/json',
          body: JSON.stringify({data: null, error: {code: 'c35_injected_fault', message: 'C35受控版本接口故障'}})}); } catch {}
      });
    }
    await page.goto(input.base_url + (input.page === 'emotion' ? '/emotion' : '/') + '#' + input.token);
    const beforeApi = await query('/api/v1/' + input.page);
    report.observations.before_api = beforeApi;
    if ((beforeApi.automatic ?? beforeApi.emotion).arousal >= 0) throw Error('nonzero preparation absent');
    if (late) await expect.poll(() => heldOld && !!report.held_old_response).toBe(true);
    else { await values().first().waitFor(); report.observations.before_dom = await dom(); }
    if (metaFault || broadcast) await expect.poll(() => heldMetadata).toBeGreaterThan(0);
    if (input.id.includes('manual_fields')) {
      const range = page.locator('#override-valence');
      await range.focus(); await range.press('Home');
      for(let step=0; step<20; step++) await range.press('ArrowRight');
      await expect(range).toHaveValue('0');
      await page.locator('#override-duration').fill('900');
      await page.locator('#override-reason').fill('C35保留手工字段');
      report.observations.edited_dom = await dom();
    }
    if (input.id.includes('same_revision')) {
      report.observations.ordinary_result = await query('/api/v1/chat', {text: '这是中性请求。'});
      const state = await query('/api/v1/dashboard');
      if (state.context.revision !== beforeApi.context.revision || state.emotion.arousal >= 0) throw Error('same-revision continuity failed');
      await page.waitForTimeout(1000);
      if (!(await dom()).values[0]?.includes('-')) throw Error('valid role state hidden');
      report.observations.after_api = state;
    } else if (input.id.includes('service_instance_restart')) {
      const response = await page.request.post(input.control_url, {headers: {'X-C35-Control': input.control_token}});
      report.restart = await response.json();
      if (!response.ok() || report.restart.before === report.restart.after) throw Error('new actual service instance absent');
      await zero();
      const state = await query('/api/v1/dashboard');
      if (state.context.instance_id === beforeApi.context.instance_id || state.context.revision !== 0) throw Error('wrong replacement instance');
      report.observations.after_api = state;
    } else {
      await query('/api/forget', {id: input.fragment_id});
      const afterApi = await query('/api/v1/' + input.page);
      const automatic = afterApi.automatic ?? afterApi.emotion;
      if (automatic.valence !== 0 || automatic.arousal !== 0 || afterApi.context.revision !== 1) throw Error('backend boundary absent');
      report.observations.after_api = afterApi;
      if (metaFault) {
        releaseMetadata();
        await expect(page.getByRole('alert')).toContainText('版本同步暂不可用');
        if ((await dom()).values.length) throw Error('stale state visible while metadata unavailable');
        report.observations.fault_dom = await dom();
        metadataMode = 'recover';
        if (input.id.includes('403')) await page.getByRole('button', {name: '重新读取', exact: true}).click();
      }
      if (broadcast) {
        const second = await context.newPage();
        await second.goto(input.base_url + '/tools#' + input.token);
        await second.evaluate(() => {
          const channel = new BroadcastChannel('avatar-conversation-privacy-v1');
          channel.postMessage({type: 'invalidate', sender: 'c35-other-tab'}); channel.close();
        });
        report.native_cross_window_notice = true;
        // Held first-tab watch prevents that request from explaining recovery.
        await zero();
        releaseMetadata();
        await second.close();
      }
      await zero();
      if (late) {
        report.observations.before_late_release = await dom();
        releaseOld();
        await expect.poll(() => !!report.old_fulfillment).toBe(true);
        await page.waitForTimeout(1000); await zero();
        report.late_body_delivered_to_javascript_claim = false;
      }
      if (input.id.includes('manual_fields')) {
        await expect(page.locator('#override-valence')).toHaveValue('0');
        await expect(page.locator('#override-arousal')).toHaveValue('-0.1');
        await expect(page.locator('#override-duration')).toHaveValue('900');
        await expect(page.locator('#override-reason')).toHaveValue('C35保留手工字段');
        if (afterApi.effective.valence !== .6 || afterApi.effective.arousal !== -.1) throw Error('independent override lost');
      }
    }
    report.observations.final_dom = await dom();
    await page.screenshot({path: input.screenshot});
    if (report.errors.length) throw Error(JSON.stringify(report.errors));
    report.completed = true;
  } catch (error) { report.failure = String(error); process.exitCode = 1; }
  finally {
    releaseOld?.(); releaseMetadata?.();
    await browser.close();
    process.stdout.write(JSON.stringify(report) + '\n');
  }
})().catch(error => {process.stderr.write(String(error) + '\n'); process.exitCode = 1;});
