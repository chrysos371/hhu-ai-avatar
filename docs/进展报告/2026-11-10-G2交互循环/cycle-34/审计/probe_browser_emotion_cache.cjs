const fs = require('node:fs'), path = require('node:path');
const {execFileSync} = require('node:child_process');
const root = execFileSync('git', ['rev-parse', '--show-toplevel'], {cwd: __dirname, encoding: 'utf8'}).trim();
const {chromium} = require(path.join(root, 'frontend/node_modules/@playwright/test'));
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
(async () => {
  const browser = await chromium.launch({channel: 'chromium', headless: true});
  const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
  const errors = [], calls = [];
  page.on('pageerror', error => errors.push(error.message));
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
  const dom = () => page.locator('.grid.three .metric-number').allTextContents();
  try {
    await page.goto(input.base_url + '/emotion#' + input.token);
    await page.locator('.grid.three .metric-number').first().waitFor();
    const before = await dom(), beforeApi = await query('/api/v1/emotion');
    if (beforeApi.data.automatic.arousal >= 0) throw Error('Required nonzero preparation absent');
    const start = performance.now();
    await query('/api/forget', {id: input.fragment_id});
    const afterApi = await query('/api/v1/emotion');
    if (afterApi.data.automatic.valence !== 0 || afterApi.data.automatic.arousal !== 0) throw Error('Backend not cleared');
    const immediate = await dom();
    await page.waitForTimeout(input.observation_ms);
    const delayed = await dom(), delayedMs = performance.now() - start;
    await page.screenshot({path: input.screenshot});
    await page.waitForFunction(() => [...document.querySelectorAll('.grid.three .metric-number')]
      .every(element => element.textContent.replace(/\s/g, '') === 'P0.00/A0.00'), null, {timeout: 15000});
    const eventual = await dom(), eventualMs = performance.now() - start;
    if (errors.length) throw Error(JSON.stringify(errors));
    process.stdout.write(JSON.stringify({completed: true, before, before_api: beforeApi.data,
      immediate, delayed, delayed_ms: delayedMs, after_api: afterApi.data,
      eventual, eventual_ms: eventualMs, stale_immediate: JSON.stringify(immediate) === JSON.stringify(before),
      stale_at_fixed_observation: JSON.stringify(delayed) === JSON.stringify(before),
      browser_reloaded_or_navigated_after_forget: false, calls, errors}) + '\n');
  } finally { await browser.close(); }
})().catch(error => {process.stderr.write(String(error) + '\n'); process.exitCode = 1;});
