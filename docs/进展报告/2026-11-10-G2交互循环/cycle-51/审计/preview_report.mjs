import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const source = fileURLToPath(import.meta.url);
const here = dirname(source);
const root = resolve(here, '../../../../..');
const assets = '/data/Users/zrh/data/hhu-ai-avatar';
const report = join(here, '系统审计与推进报告.html');
const output = join(here, '收尾核验/report-browser.json');
const raw = join(assets, 'artifacts/c51/report-preview-v1');
if (!existsSync(report) || existsSync(output) || existsSync(raw)) throw new Error('fresh C51 report preview required');
process.env.PLAYWRIGHT_BROWSERS_PATH = join(assets, 'runtime/playwright');
const libs = join(assets, 'runtime/browser-libs');
const libPath = join(libs, 'extracted/usr/lib/x86_64-linux-gnu');
if (existsSync(libPath)) process.env.LD_LIBRARY_PATH = libPath + (process.env.LD_LIBRARY_PATH ? ':' + process.env.LD_LIBRARY_PATH : '');
if (existsSync(join(libs, 'fontconfig.xml'))) process.env.FONTCONFIG_FILE = join(libs, 'fontconfig.xml');
const { chromium } = await import(pathToFileURL(join(root, 'frontend/node_modules/playwright/index.mjs')).href);
const sha = path => createHash('sha256').update(readFileSync(path)).digest('hex');
const result = { completed: false, scope: 'static report display/link checks only;not avatar/model/semantic verification',
  reportSha256: sha(report), scriptSha256: sha(source), views: [], errors: [], modelGenerations: 0 };
mkdirSync(raw, { recursive: true });
let browser;
try {
  browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-gpu'] });
  result.browserVersion = browser.version();
  for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    const page = await browser.newPage({ viewport });
    page.on('pageerror', error => result.errors.push(String(error)));
    page.on('console', message => { if (message.type() === 'error') result.errors.push(message.text()); });
    await page.goto(pathToFileURL(report).href, { waitUntil: 'load', timeout: 30000 });
    const observed = await page.evaluate(() => ({
      title: document.querySelector('h1')?.textContent, tableCount: document.querySelectorAll('table').length,
      overflow: document.documentElement.scrollWidth > window.innerWidth,
      links: [...document.querySelectorAll('a')].map(a => ({ text: a.textContent, href: a.href }))
    }));
    for (const link of observed.links) {
      if (!link.href.startsWith('file:') || !existsSync(fileURLToPath(link.href))) throw new Error('missing local link: ' + link.href);
    }
    const horizontalTables = await page.locator('.table-wrap').evaluateAll(elements => elements.map(element => {
      element.scrollLeft = element.scrollWidth;
      const last = element.querySelector('tbody tr:last-child td:last-child');
      const cell = last.getBoundingClientRect(), wrapper = element.getBoundingClientRect();
      return { scrollWidth: element.scrollWidth, clientWidth: element.clientWidth,
        lastCellReadable: cell.left >= wrapper.left - 1 && cell.right <= wrapper.right + 1 };
    }));
    await page.locator('.table-wrap').evaluateAll(elements => elements.forEach(element => { element.scrollLeft = 0; }));
    const screenshot = join(raw, `report-${viewport.width}.png`);
    await page.screenshot({ path: screenshot, fullPage: true });
    result.views.push({ viewport, ...observed, horizontalTables, screenshot, screenshotSha256: sha(screenshot) });
    if (observed.overflow || !observed.title?.startsWith('C51') || horizontalTables.some(t => !t.lastCellReadable)) {
      throw new Error('report layout failed at width ' + viewport.width);
    }
    await page.close();
  }
  if (result.errors.length) throw new Error('report browser errors');
  result.completed = true;
} catch (error) {
  result.failure = String(error);
  throw error;
} finally {
  if (browser) await browser.close();
  writeFileSync(output, JSON.stringify(result, null, 2) + '\n', { flag: 'wx' });
}
console.log('C51 static report:1440/390 screenshots and local links checked;0 model calls');
