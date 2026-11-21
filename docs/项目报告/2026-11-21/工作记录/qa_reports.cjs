const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { fileURLToPath, pathToFileURL } = require('node:url');
const { chromium } = require('/data/Users/zrh/data/hhu-ai-avatar/frontend/release-renderer-dev-v1/node_modules/@playwright/test');
const ROOT = '/data/Users/zrh/repo/hhu-ai-avatar';
const folder = path.join(ROOT, 'docs/项目报告/2026-11-21');
const raw = process.argv[2];
fs.mkdirSync(raw, { recursive: false });
const inventory = JSON.parse(fs.readFileSync(path.join(folder, '工作记录/历史资料与提交清单.json'), 'utf8'));
const commits = new Set(inventory.commits.map(row => row.sha));
const files = ['接手以来项目推进全景报告.html', '2.0.0技术发布报告.html', '2.0.0用户使用说明书.html'];
const kinds = ['history', 'technical', 'manual'];
const result = { passed: false, views: [], local_links_checked: 0, generated_commit_links_checked: 0,
  external_network_availability_claimed: false, search_checks: [], navigation_checks: [], print_checks: [], errors: [] };
let server, browser, waited;
(async () => {
  try {
    server = await chromium.launchServer({ headless: true, channel: 'chromium', args: [
      '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
    const child = server.process();
    result.browser_pid = child.pid;
    waited = new Promise(resolve => child.once('exit', (code, signal) => resolve({ code, signal })));
    browser = await chromium.connect(server.wsEndpoint());
    result.browser_version = browser.version();
    for (let index = 0; index < files.length; index++) {
      for (const width of [1440, 390]) {
        const page = await browser.newPage({ viewport: { width, height: width === 1440 ? 1000 : 844 } });
        page.on('pageerror', error => result.errors.push(String(error)));
        page.on('console', message => { if (message.type() === 'error') result.errors.push(message.text()); });
        const filename = path.join(folder, files[index]);
        await page.goto(pathToFileURL(filename).href);
        await page.locator('h1').waitFor();
        assert.equal(await page.locator('body').getAttribute('class'), kinds[index]);
        assert.equal(await page.locator('h1').count(), 1);
        const dimensions = await page.evaluate(() => ({ viewport: innerWidth, root: document.documentElement.scrollWidth,
          color: getComputedStyle(document.body).color, background: getComputedStyle(document.body).backgroundColor }));
        assert(dimensions.root <= dimensions.viewport, 'root overflow '+files[index]+' '+width);
        const ids = await page.locator('[id]').evaluateAll(nodes => nodes.map(node => node.id));
        assert.equal(ids.length, new Set(ids).size, 'duplicate anchors');
        const hrefs = await page.locator('a[href]').evaluateAll(nodes => nodes.map(node => node.href));
        for (const href of hrefs) {
          const url = new URL(href);
          if (url.protocol === 'file:') {
            const local = fileURLToPath(url);
            assert(fs.statSync(local).isFile(), 'missing local target '+href);
            if (local === filename && url.hash) assert(ids.includes(decodeURIComponent(url.hash.slice(1))), 'missing anchor '+href);
            result.local_links_checked++;
          } else {
            assert.equal(url.origin, 'https://github.com');
            const match = url.pathname.match(/^\/chrysos371\/hhu-ai-avatar\/commit\/([a-f0-9]{40})$/);
            assert(match && commits.has(match[1]), 'unregistered external commit URL');
            result.generated_commit_links_checked++;
          }
        }
        assert.equal(await page.locator('img').evaluateAll(nodes => nodes.every(node => node.complete && node.naturalWidth > 0)), true);
        assert.equal(await page.locator('pre').evaluateAll(nodes => nodes.every(node => !/^\+  /m.test(node.textContent))), true, 'patch markers in commands');
        if (index === 0) {
          assert.equal(await page.locator('[data-search-scope="cycles"]').count(), 57);
          assert.equal(await page.locator('[data-search-scope="commits"]').count(), 2432);
          const search = page.getByLabel('搜索周期', { exact: true });
          await search.fill('目标表达对照中断');
          assert.equal(await page.locator('#cycle-54').evaluate(node => node.hidden), false);
          assert.equal(await page.locator('[data-search-scope="cycles"]').evaluateAll(nodes => nodes.filter(n => !n.hidden).length), 1);
          await search.fill('no-such-cycle-907341');
          assert.equal(await page.locator('[data-search-scope="cycles"]').evaluateAll(nodes => nodes.filter(n => !n.hidden).length), 0);
          await search.fill('');
          await page.getByText('展开全部2432笔提交（含接手前背景，可检索）', { exact: true }).click();
          const commitSearch = page.getByLabel('搜索提交', { exact: true });
          await commitSearch.fill('349160c2');
          assert.equal(await page.locator('[data-search-scope="commits"]').evaluateAll(nodes => nodes.filter(n => !n.hidden).length), 1);
          await commitSearch.fill('spinner-bot');
          assert.equal(await page.locator('[data-search-scope="commits"]').evaluateAll(nodes => nodes.filter(n => !n.hidden).length), 2414);
          await commitSearch.fill('');
          await page.getByText('展开全部2432笔提交（含接手前背景，可检索）', { exact: true }).click();
          result.search_checks.push({ width, cycles: 57, commits: 2432, author_matches: 2414, absent_query: 0 });
        }
        for (let other = 0; other < files.length; other++) {
          await page.locator('.report-nav a').nth(other).click();
          assert.equal(await page.locator('body').getAttribute('class'), kinds[other]);
        }
        await page.goto(pathToFileURL(filename).href);
        result.navigation_checks.push({ report: kinds[index], width, cross_report_pages: 3 });
        await page.screenshot({ path: path.join(raw, kinds[index]+'-'+width+'.png') });
        await page.locator(index === 0 ? '#cycles' : index === 1 ? '#gates' : '#voice').scrollIntoViewIfNeeded();
        await page.screenshot({ path: path.join(raw, kinds[index]+'-section-'+width+'.png') });
        await page.emulateMedia({ media: 'print' });
        assert.equal(await page.locator('.top').evaluate(node => getComputedStyle(node).display), 'none');
        assert.equal(await page.locator('.toc').evaluate(node => getComputedStyle(node).display), 'none');
        if (width === 1440) await page.pdf({ path: path.join(raw, kinds[index]+'-print-first-page.pdf'), format: 'A4', pageRanges: '1', printBackground: true });
        result.print_checks.push({ report: kinds[index], width, navigation_hidden: true });
        result.views.push({ report: kinds[index], width, dimensions });
        await page.close();
      }
    }
    const nojs = await browser.newPage({ javaScriptEnabled: false, viewport: { width: 390, height: 844 } });
    await nojs.goto(pathToFileURL(path.join(folder, files[0])).href);
    assert.equal(await nojs.locator('[data-search-scope="cycles"]').count(), 57);
    await nojs.getByText('展开全部2432笔提交（含接手前背景，可检索）', { exact: true }).click();
    assert.equal(await nojs.locator('[data-search-scope="commits"]').count(), 2432);
    result.no_javascript_full_history_readable = true;
    await nojs.close();
    assert.equal(result.errors.length, 0);
    result.passed = true;
  } catch (error) {
    result.error = String(error.stack || error); process.exitCode = 1;
  } finally {
    if (browser) await browser.close();
    if (server) {
      await server.close(); result.browser_exit = await waited;
      result.browser_pid_retired = !fs.existsSync('/proc/'+result.browser_pid);
      if (result.browser_exit.code !== 0 || !result.browser_pid_retired) { result.passed = false; process.exitCode = 1; }
    }
    fs.writeFileSync(path.join(raw, 'result.json'), JSON.stringify(result, null, 2)+'\n');
    console.log(JSON.stringify(result));
  }
})();
