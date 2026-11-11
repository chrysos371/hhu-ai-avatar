import { chromium } from '../../../../../frontend/node_modules/playwright/index.mjs';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { createHash } from 'node:crypto';
import { openSync, closeSync, readFileSync, writeFileSync, readdirSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here=dirname(fileURLToPath(import.meta.url)), root=resolve(here,'../../../../../');
const ev=join(here,'../实验'), base='http://127.0.0.1:18765';
const token='mission-control-disposable-e2e-token';
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
function walk(folder){return readdirSync(folder,{withFileTypes:true}).flatMap(entry=>entry.isDirectory()?walk(join(folder,entry.name)):[join(folder,entry.name)]);}
const sources=[...walk(join(root,'frontend/src')), ...['src/avatar/brain/speaker_context.py','src/avatar/brain/speaker_scope.py',
  'src/avatar/web_api.py','src/avatar/conversation_changes.py','tests/helpers/serve_admin_e2e.py',
  'evals/interaction/cycle-18/explicit-context-protocol.json'].map(p=>join(root,p)),fileURLToPath(import.meta.url)];
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const fingerprint=()=>Object.fromEntries(sources.sort().map(p=>[relative(root,p),hash(readFileSync(p))]));
const report={scope:'Actual Chromium and authenticated HTTP with owned disposable fixture; no real models/physical/human quality',
  sourceSha256:fingerprint(),steps:[],completed:false,failure:null,fixturePid:null,fixtureExit:null};
const save=()=>writeFileSync(join(ev,'browser-before.json'),JSON.stringify(report,null,2)+'\n');
save();
try { await fetch(base); throw Error('Fixture port already occupied; no existing service reused'); }
catch(error){if(!String(error).includes('fetch failed'))throw error;}
const log=openSync(join(ev,'browser-before-fixture.log'),'wx');
const fixture=spawn(join(root,'../envs/hhu-ai-avatar/bin/python'),['tests/helpers/serve_admin_e2e.py'],
  {cwd:root,env:{...process.env,AVATAR_E2E_EMPTY_PROFILE:'1'},stdio:['ignore',log,log]});
report.fixturePid=fixture.pid;const exited=once(fixture,'exit');let browser;
try {
  while(true){
    if(fixture.exitCode!==null)throw Error('Owned fixture exited before ready');
    try{const ready=await fetch(base);if(ready.ok)break;}catch{}
    await sleep(50);
  }
  const headers={'X-Avatar-Token':token};
  for(const path of ['/api/v1/conversation/speaker','/api/v1/conversation/changes?instance_id=baseline-different&revision=0']){
    const response=await fetch(base+path,{headers});
    report.steps.push({kind:'http',path,status:response.status,body:await response.json()});save();
  }
  if(report.steps[0].status!==404)throw Error('Expected before-state missing speaker endpoint');
  if(Object.keys(report.steps[1].body.data).sort().join(',')!=='instance_id,revision')throw Error('Legacy watch contract differs');
  browser=await chromium.launch({headless:true});report.browserVersion=browser.version();
  for(const [name,width,height] of [['desktop',1440,900],['mobile',390,844]]){
    const page=await browser.newPage({viewport:{width,height}});const errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.goto(base+'/chat#'+token);
    await page.locator('.chat-history[data-history-ready="true"]').waitFor();
    const state={kind:'browser',name,width,roleButtons:await page.getByRole('button',{name:'进入角色',exact:true}).count(),
      realButtons:await page.getByRole('button',{name:'以本人说话',exact:true}).count(),
      contextPanels:await page.locator('[data-speaker-context]').count(),errors,
      overflow:await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)};
    if(state.roleButtons||state.realButtons||state.contextPanels||errors.length||state.overflow)throw Error(JSON.stringify(state));
    await page.screenshot({path:join(ev,'browser-before-'+name+'.png'),fullPage:true});
    report.steps.push(state);save();await page.close();
  }
  if(JSON.stringify(fingerprint())!==JSON.stringify(report.sourceSha256))throw Error('Sources changed during baseline');
  report.completed=true;
}catch(error){report.failure=String(error);}
finally{
  if(browser)await browser.close();
  if(fixture.exitCode===null)fixture.kill('SIGTERM');
  const [code]=await exited;report.fixtureExit=code;closeSync(log);save();
}
if(!report.completed||report.fixtureExit!==0)throw Error(JSON.stringify({completed:report.completed,exit:report.fixtureExit,failure:report.failure}));
console.log(JSON.stringify({completed:report.completed,fixturePid:report.fixturePid,fixtureExit:report.fixtureExit,steps:report.steps}));
