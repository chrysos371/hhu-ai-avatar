import { chromium } from '../../../../../frontend/node_modules/playwright/index.mjs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';
import { writeFileSync, readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
const here = dirname(fileURLToPath(import.meta.url));
const browser = await chromium.launch({headless:true});
const results=[];
try {
  for (const [name,width,height] of [['desktop',1440,900],['mobile',390,844]]) {
    const page=await browser.newPage({viewport:{width,height}});
    const errors=[];page.on('pageerror', error=>errors.push(error.message));
    await page.goto(pathToFileURL(join(here,'认知事实事务来源修复报告.html')).href);
    const result=await page.evaluate(()=>({title:document.title,h1:document.querySelectorAll('h1').length,
      tables:document.querySelectorAll('table').length,links:document.querySelectorAll('a').length,
      overflow:document.documentElement.scrollWidth>innerWidth,width:innerWidth}));
    if(result.h1!==1||result.tables!==4||result.overflow||errors.length) throw Error(JSON.stringify({result,errors}));
    await page.screenshot({path:join(here,'fact-report-'+name+'.png'),fullPage:true});
    if(name==='mobile')await page.screenshot({path:join(here,'fact-report-mobile-viewport.png')});
    results.push({name,...result,errors});await page.close();
  }
  writeFileSync(join(here,'工作目录/010-认知事实事务来源/report-browser.json'),JSON.stringify({reportSha256:createHash('sha256').update(readFileSync(join(here,'认知事实事务来源修复报告.html'))).digest('hex'),browserVersion:browser.version(),results},null,2)+'\n');
  console.log(JSON.stringify(results));
} finally { await browser.close(); }
