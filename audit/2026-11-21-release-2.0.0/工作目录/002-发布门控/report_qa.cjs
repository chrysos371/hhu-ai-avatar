const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {fileURLToPath,pathToFileURL}=require('node:url');
const {chromium}=require('/data/Users/zrh/data/hhu-ai-avatar/frontend/release-renderer-dev-v1/node_modules/@playwright/test');
const ROOT='/data/Users/zrh/repo/hhu-ai-avatar';
const reportPath=path.join(ROOT,'audit/2026-11-21-release-2.0.0/系统审计与发布报告.html');
const raw=process.argv[2];fs.mkdirSync(raw,{recursive:false});
const result={passed:false,viewports:[],links_checked:0,page_errors:[],console_errors:[],physical_approved:false};
let server,browser,wait;
(async()=>{try {
 server=await chromium.launchServer({headless:true,channel:'chromium',args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
 const child=server.process();result.browser_pid=child.pid;
 wait=new Promise(resolve=>child.once('exit',(code,signal)=>resolve({code,signal})));
 browser=await chromium.connect(server.wsEndpoint());
 for(const width of [1440,390]) {
  const page=await browser.newPage({viewport:{width,height:1000}});
  page.on('pageerror',e=>result.page_errors.push(String(e)));
  page.on('console',m=>{if(m.type()==='error')result.console_errors.push(m.text())});
  await page.goto(pathToFileURL(reportPath).href);await page.locator('h1').waitFor();
  const dimensions=await page.evaluate(()=>({body:document.documentElement.scrollWidth,viewport:innerWidth}));
  assert(dimensions.body<=dimensions.viewport,'root horizontal overflow');
  const links=await page.locator('a[href]').evaluateAll(a=>a.map(x=>x.href));
  for(const href of links) {
   const url=new URL(href);assert.equal(url.protocol,'file:','portable local report links only');
   const target=fileURLToPath(url);assert(fs.statSync(target).isFile(),'missing local link '+href);
   if(url.hash&&target===reportPath)assert(await page.locator(url.hash).count(),'missing report anchor');
   result.links_checked++;
  }
  await page.screenshot({path:path.join(raw,'report-'+width+'.png'),fullPage:true});result.viewports.push(width);await page.close();
 }
 assert(result.links_checked>0);assert.equal(result.page_errors.length,0);assert.equal(result.console_errors.length,0);
 result.passed=true;
}catch(error){result.error=String(error);process.exitCode=1;}
finally {
 if(browser)await browser.close();if(server){await server.close();result.browser_exit=await wait;assert.equal(result.browser_exit.code,0);result.browser_pid_retired=!fs.existsSync('/proc/'+result.browser_pid);assert(result.browser_pid_retired);}
 fs.writeFileSync(path.join(raw,'result.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
}})();
