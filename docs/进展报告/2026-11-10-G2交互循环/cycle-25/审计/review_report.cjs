const fs=require('node:fs'), path=require('node:path');
const {pathToFileURL}=require('node:url');
const {createHash}=require('node:crypto');
const {execFileSync}=require('node:child_process');
const root=execFileSync('git',['rev-parse','--show-toplevel'],{cwd:__dirname,encoding:'utf8'}).trim();
const {chromium}=require(path.join(root,'frontend/node_modules/@playwright/test'));
const report=path.join(__dirname,'系统审计与推进报告.html');
const output=path.join(__dirname,'收尾核验/report-browser.json');
if(fs.existsSync(output))throw Error('Fresh report review output required');
(async()=>{
 const browser=await chromium.launch({channel:'chromium',headless:true});
 const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const results=[];
 try{
  await page.goto(pathToFileURL(report).href);
  for(const viewport of [{width:1440,height:1000},{width:390,height:844}]){
   await page.setViewportSize(viewport);
   const state=await page.evaluate(()=>({title:document.title,tableCount:document.querySelectorAll('table').length,overflow:document.documentElement.scrollWidth>innerWidth,
    links:[...document.querySelectorAll('a[href]')].map(a=>a.getAttribute('href'))}));
   if(state.overflow||state.tableCount!==4)throw Error('Report layout failed');
   const links=state.links.map(href=>/^https?:\/\//.test(href)?{href,external:true,exists:null}:{href,external:false,exists:fs.existsSync(path.resolve(path.dirname(report),decodeURIComponent(href.split('#')[0])))});
   if(links.some(link=>!link.external&&!link.exists))throw Error('Broken report link: '+JSON.stringify(links.filter(x=>!x.exists)));
   await page.screenshot({path:path.join(__dirname,viewport.width===1440?'final-report-desktop.png':'final-report-mobile-viewport.png'),fullPage:viewport.width===1440});
   if(viewport.width===390)await page.locator('table').first().screenshot({path:path.join(__dirname,'final-report-mobile-table.png')});
   results.push({viewport,...state,links});
  }
  if(errors.length)throw Error(JSON.stringify(errors));
  fs.writeFileSync(output,JSON.stringify({reportSha256:createHash('sha256').update(fs.readFileSync(report)).digest('hex'),views:results,errors,completed:true},null,2)+'\n',{flag:'wx'});
  process.stdout.write('Report verified in 1440/390: four tables, all links, no overflow or page errors.\n');
 }finally{await browser.close();}
})().catch(e=>{process.stderr.write(String(e)+'\n');process.exitCode=1;});
