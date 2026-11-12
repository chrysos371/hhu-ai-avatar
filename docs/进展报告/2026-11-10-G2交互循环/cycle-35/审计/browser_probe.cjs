const fs = require('node:fs'), path = require('node:path');
const {execFileSync} = require('node:child_process');
const root = execFileSync('git', ['rev-parse', '--show-toplevel'], {cwd: __dirname, encoding: 'utf8'}).trim();
const {chromium} = require(path.join(root, 'frontend/node_modules/@playwright/test'));
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
(async () => {
  const browser = await chromium.launch({channel: 'chromium', headless: true});
  const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
  const errors = [], calls = [], versionRequests = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => {
    if (request.url().includes('/conversation/changes?')) versionRequests.push(new URL(request.url()).pathname + new URL(request.url()).search);
  });
  const query = async (route, data) => {
    const response = await page.request.fetch(input.base_url + route, {
      method: data === undefined ? 'GET' : 'POST', data,
      headers: {'X-Avatar-Token': input.token},
    });
    const raw = await response.text();
    calls.push({route, payload: data ?? null, status: response.status(), raw_response: raw});
    if (!response.ok()) throw Error('Controlled HTTP request failed: ' + response.status());
    return JSON.parse(raw);
  };
  const card = () => page.locator('article').filter({has: page.getByRole('heading', {name: '角色自动状态', exact: true})});
  const dom = async () => input.page === 'emotion'
    ? {values: await page.locator('.grid.three .metric-number').allTextContents(),
       form: {valence: await page.getByLabel('愉悦度 P：', {exact: false}).inputValue().catch(() => null),
              arousal: await page.getByLabel('唤醒度 A：', {exact: false}).inputValue().catch(() => null)}}
    : {values: await card().locator('p.muted').allTextContents(),
       eventRows: await page.locator('article').filter({has: page.getByRole('heading', {name: '最近对话事件', exact: true})}).locator('tbody tr').count()};
  try {
    await page.goto(input.base_url + (input.page === 'emotion' ? '/emotion' : '/') + '#' + input.token);
    await (input.page === 'emotion' ? page.locator('.grid.three .metric-number').first() : card()).waitFor();
    const before = await dom(), beforeApi = await query('/api/v1/' + input.page);
    const beforeAutomatic = beforeApi.data.automatic || beforeApi.data.emotion;
    if (beforeAutomatic.arousal >= 0) throw Error('Required nonzero preparation absent');
    const start = performance.now();
    await query('/api/forget', {id: input.fragment_id});
    const afterApi = await query('/api/v1/' + input.page), automatic = afterApi.data.automatic || afterApi.data.emotion;
    if (automatic.valence !== 0 || automatic.arousal !== 0) throw Error('Backend not cleared');
    const immediate = await dom();
    await page.waitForTimeout(input.observation_ms);
    const delayed = await dom(), delayedMs = performance.now() - start;
    await page.screenshot({path: input.screenshot});
    await page.waitForFunction(which => {
      if (which === 'emotion') {
        const nodes = [...document.querySelectorAll('.grid.three .metric-number')];
        return nodes.length === 3 && nodes.every(element => element.textContent.replace(/\s/g, '') === 'P0.00/A0.00');
      }
      const heading = [...document.querySelectorAll('h2')].find(element => element.textContent === '角色自动状态');
      const text = heading?.closest('article')?.querySelector('p.muted')?.textContent?.replace(/\s/g, '');
      return text === '愉悦度0.00·唤醒度0.00';
    }, input.page, {timeout: input.eventual_timeout_ms});
    const eventual = await dom(), eventualMs = performance.now() - start;
    if (errors.length) throw Error(JSON.stringify(errors));
    const result = {completed: true, before, before_api: beforeApi.data, immediate, delayed, delayed_ms: delayedMs,
      after_api: afterApi.data, eventual, eventual_ms: eventualMs,
      stale_immediate: JSON.stringify(immediate.values) === JSON.stringify(before.values),
      stale_at_fixed_observation: JSON.stringify(delayed.values) === JSON.stringify(before.values),
      browser_reloaded_or_navigated_after_forget: false, calls, version_requests: versionRequests, errors};
    if (input.phase === 'after' && result.stale_at_fixed_observation) throw Error('After phase still displays old values at fixed observation');
    process.stdout.write(JSON.stringify(result) + '\n');
  } finally { await browser.close(); }
})().catch(error => {process.stderr.write(String(error) + '\n'); process.exitCode = 1;});
