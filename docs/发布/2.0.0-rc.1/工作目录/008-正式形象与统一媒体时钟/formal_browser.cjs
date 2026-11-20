const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium, expect } = require('/data/Users/zrh/data/hhu-ai-avatar/frontend/release-renderer-dev-v1/node_modules/@playwright/test');
const raw = path.resolve(process.argv[2]);
assert(raw.startsWith('/data/Users/zrh/data/hhu-ai-avatar/artifacts/release/formal-browser-v'));
const token = 'mission-control-disposable-e2e-token';
const report = { passed: false, physical_device_approved: false, software_webgl_only: true, viewports: [], page_errors: [], console_errors: [] };
let server, browser;
const started = performance.now();
function identity(child) {
  const stat = fs.readFileSync(`/proc/${child.pid}/stat`, 'utf8');
  return { pid: child.pid, start_ticks: Number(stat.slice(stat.lastIndexOf(')') + 2).trim().split(/\s+/)[19]),
    argv: fs.readFileSync(`/proc/${child.pid}/cmdline`, 'utf8').split('\0').filter(Boolean) };
}
async function snapshot(player, canvas) {
  return { audio: await player.evaluate(a => ({ time: a.currentTime, paused: a.paused, rate: a.playbackRate })),
    render: await canvas.evaluate(c => ({ time: Number(c.dataset.mediaTime), open: Number(c.dataset.mouthOpen),
      height: Number(c.dataset.mouthHeight), count: Number(c.dataset.renderCount) })) };
}
(async () => {
  try {
    server = await chromium.launchServer({ headless: true, channel: 'chromium', host: '127.0.0.1', args: [
      '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader',
      '--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream' ] });
    report.browser_process = identity(server.process()); report.executable = chromium.executablePath();
    browser = await chromium.connect(server.wsEndpoint()); report.browser_version = browser.version();
    for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
      const name = String(viewport.width), context = await browser.newContext({ viewport });
      await context.tracing.start({ screenshots: true, snapshots: true, sources: true });
      const page = await context.newPage(); page.setDefaultTimeout(15000);
      page.on('pageerror', error => report.page_errors.push({ viewport, message: error.message }));
      page.on('console', message => { if (message.type() === 'error') report.console_errors.push({ viewport, message: message.text() }); });
      const row = { viewport, samples: [], pause_ms: [], same_canvas_recovered: false, disposed: false };
      report.viewports.push(row);
      try {
        await page.goto('http://127.0.0.1:18765/chat#' + token);
        await expect(page.getByRole('heading', { name: '对话观测', exact: true })).toBeVisible();
        await expect(page.locator('.chat-history')).toHaveAttribute('data-history-ready', 'true');
        const stage = page.locator('.avatar-stage'), canvas = stage.locator('canvas');
        await expect(stage).toHaveAttribute('data-renderer', 'ready');
        row.webgl = await canvas.evaluate(c => {
          const gl = c.getContext('webgl2'); if (!gl) return null;
          const info = gl.getExtension('WEBGL_debug_renderer_info');
          return { version: gl.getParameter(gl.VERSION), renderer: info ? gl.getParameter(info.UNMASKED_RENDERER_WEBGL) : '',
            lost: gl.isContextLost(), width: c.width, height: c.height };
        });
        assert(row.webgl && !row.webgl.lost && /SwiftShader|llvmpipe/i.test(row.webgl.renderer), 'software renderer identity required');
        const before = await page.locator('.chat-message.assistant').count();
        await page.getByLabel('消息', { exact: true }).fill('你好');
        await page.getByRole('button', { name: '发送消息' }).click();
        await expect(page.locator('.chat-message.assistant')).toHaveCount(before + 1);
        const audioResponse = page.waitForResponse(r => r.url().includes('/speech/audio/'));
        const speechResponse = page.waitForResponse(r => r.url().endsWith('/api/v1/speech') && r.request().method() === 'POST');
        await page.getByRole('button', { name: '朗读回复' }).last().click();
        const audio = await audioResponse; assert(audio.ok());
        assert(!audio.url().includes(token)); assert.equal(audio.request().headers()['x-avatar-token'], token);
        fs.writeFileSync(path.join(raw, `audio-${name}.wav`), await audio.body(), { flag: 'wx' });
        fs.writeFileSync(path.join(raw, `speech-${name}.json`), JSON.stringify(await (await speechResponse).json(), null, 2), { flag: 'wx' });
        const player = page.getByLabel(/语音播放器$/); await expect(player).toBeVisible();
        for (const target of [.10, .35, .85, 1.15, 1.40]) {
          await player.evaluate(async (a, target) => { a.currentTime = target; await a.play(); }, target);
          await page.waitForFunction(target => {
            const a = document.querySelector('audio'), c = document.querySelector('.avatar-stage canvas');
            return a && c && a.currentTime >= target + .04 && Number(c.dataset.mediaTime) >= target - .08;
          }, target);
          const sample = await snapshot(player, canvas); sample.seek_target = target;
          sample.media_error_seconds = Math.abs(sample.audio.time - sample.render.time);
          assert(sample.media_error_seconds <= .25); row.samples.push(sample);
          const begin = await page.evaluate(() => performance.now()); await player.evaluate(a => a.pause());
          await expect(canvas).toHaveAttribute('data-mouth-open', '0.000', { timeout: 1000 });
          row.pause_ms.push(await page.evaluate(() => performance.now()) - begin);
          assert(row.pause_ms.at(-1) <= 1000);
        }
        await player.evaluate(async a => { a.currentTime = .1; a.playbackRate = 1.5; await a.play(); });
        await page.waitForFunction(() => {
          const a = document.querySelector('audio'), c = document.querySelector('.avatar-stage canvas');
          return a && c && a.currentTime > .2 && Number(c.dataset.mediaTime) > .15;
        });
        row.rate_sample = await snapshot(player, canvas); assert.equal(row.rate_sample.audio.rate, 1.5);
        assert(Math.abs(row.rate_sample.audio.time-row.rate_sample.render.time) <= .25);
        await player.evaluate(a => { a.pause(); a.playbackRate = 1; });
        await expect(canvas).toHaveAttribute('data-mouth-open', '0.000');
        await page.screenshot({ path: path.join(raw, `page-${name}.png`), fullPage: true });
        await canvas.screenshot({ path: path.join(raw, `avatar-${name}.png`) });
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'root overflow');
        const canvasHandle = await canvas.elementHandle();
        await player.evaluate(async a => { a.currentTime = .1; await a.play(); });
        const loss = await canvasHandle.evaluateHandle(c => c.getContext('webgl2').getExtension('WEBGL_lose_context'));
        await loss.evaluate(extension => { if (!extension) throw Error('context-loss extension required'); extension.loseContext(); });
        await expect(stage).toHaveAttribute('data-renderer', 'lost');
        const previousTime = await player.evaluate(a => a.currentTime);
        await page.waitForFunction(previous => document.querySelector('audio').currentTime > previous + .1, previousTime);
        await loss.evaluate(extension => extension.restoreContext());
        await expect(stage).toHaveAttribute('data-renderer', 'ready');
        assert(await canvasHandle.evaluate(c => c === document.querySelector('.avatar-stage canvas')));
        row.same_canvas_recovered = true;
        await page.getByRole('button', { name: '停止播放', exact: true }).click();
        await expect(player).not.toHaveAttribute('src'); await expect(canvas).toHaveAttribute('data-mouth-open', '0.000');
        await page.getByRole('link', { name: '总览', exact: true }).click();
        await page.waitForFunction(c => c.dataset.disposed === 'true' && !c.isConnected && c.getContext('webgl2').isContextLost(), canvasHandle);
        row.disposed = true;
        await loss.dispose();
        assert(row.disposed, 'actual WebGL context must be retired after unmount');
        fs.writeFileSync(path.join(raw, 'browser-progress.json'), JSON.stringify(report, null, 2));
      } finally {
        await context.tracing.stop({ path: path.join(raw, `trace-${name}.zip`) }); await context.close();
      }
    }
    assert.deepEqual(report.page_errors, []); assert.deepEqual(report.console_errors, []);
    report.passed = true;
  } catch (error) { report.error = String(error.stack || error); process.exitCode = 1; }
  finally {
    if (browser) await browser.close().catch(error => { report.close_error = String(error); report.passed = false; process.exitCode = 1; });
    if (server) {
      await server.close().catch(error => { report.server_close_error = String(error); report.passed = false; process.exitCode = 1; });
      report.browser_wait_exit_code = server.process().exitCode;
      report.browser_wait_signal = server.process().signalCode;
      try { report.browser_pid_retired = identity(server.process()).start_ticks !== report.browser_process.start_ticks; }
      catch (error) { if (error.code === 'ENOENT') report.browser_pid_retired = true; else throw error; }
      if (report.browser_wait_exit_code !== 0 || !report.browser_pid_retired) { report.passed = false; process.exitCode = 1; }
    }
    report.seconds = (performance.now() - started) / 1000;
    fs.writeFileSync(path.join(raw, 'browser-result.json'), JSON.stringify(report, null, 2), { flag: 'wx' });
    console.log(JSON.stringify({ passed: report.passed, viewports: report.viewports.length, seconds: report.seconds, error: report.error }));
  }
})();
