import { chromium, expect } from '../../../../../frontend/node_modules/@playwright/test/index.mjs';
import { spawn, execFileSync } from 'node:child_process';
import { once } from 'node:events';
import { createHash, randomUUID } from 'node:crypto';
import { openSync, closeSync, readFileSync, writeFileSync, readdirSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';

const here=dirname(fileURLToPath(import.meta.url)), root=resolve(here,'../../../../../');
const ev=join(here,'../实验'), base='http://127.0.0.1:18765', token='mission-control-disposable-e2e-token';
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
function walk(folder){return readdirSync(folder,{withFileTypes:true}).flatMap(entry=>entry.isDirectory()?walk(join(folder,entry.name)):[join(folder,entry.name)]);}
const sourcePaths=[...walk(join(root,'frontend/src')), ...['src/avatar/main.py','src/avatar/web.py','src/avatar/turns.py',
  'src/avatar/brain/speaker_context.py','src/avatar/brain/speaker_scope.py','src/avatar/brain/memory.py',
  'src/avatar/web_api.py','src/avatar/conversation_changes.py','tests/helpers/serve_admin_e2e.py',
  'evals/interaction/cycle-18/explicit-context-protocol.json','evals/interaction/cycle-18/context-admission-protocol.json'].map(p=>join(root,p)),fileURLToPath(import.meta.url)];
const hash=p=>createHash('sha256').update(readFileSync(p)).digest('hex');
const fingerprint=()=>Object.fromEntries(sourcePaths.sort().map(p=>[relative(root,p),hash(p)]));
const report={head:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),
  scope:'Actual Chromium, local HTTP/SSE and read-only disposable DB; controlled providers, no real model or physical device approval',
  sourceSha256:fingerprint(),servedBundleSha256:Object.fromEntries(walk(join(root,'frontend/dist')).map(p=>[relative(root,p),hash(p)])),
  steps:[],posts:[],speechPosts:[],errors:[],completed:false,failure:null,fixturePid:null,fixtureExit:null};
const save=()=>writeFileSync(join(ev,'browser-context-controls.json'),JSON.stringify(report,null,2)+'\n');
const record=(name,data={})=>{report.steps.push({name,...data});save();};
save();
try{await fetch(base);throw Error('Fixture port occupied');}catch(error){if(!String(error).includes('fetch failed'))throw error;}
const tempRoot=resolve(root,'../runtime/tmp');
const prior=new Set(readdirSync(tempRoot).filter(name=>name.startsWith('admin-e2e-')));
const log=openSync(join(ev,'browser-context-controls-fixture.log'),'wx');
const fixture=spawn(join(root,'../envs/hhu-ai-avatar/bin/python'),['tests/helpers/serve_admin_e2e.py'],
  {cwd:root,env:{...process.env,AVATAR_E2E_EMPTY_PROFILE:'1'},stdio:['ignore',log,log]});
report.fixturePid=fixture.pid;const exited=once(fixture,'exit');let browser, page, held, releaseHeld, routeDone;
const api=async(path,data)=>{
  const response=await fetch(base+'/api/v1'+path,{method:data===undefined?'GET':'POST',
    headers:{'X-Avatar-Token':token,'Content-Type':'application/json'},...(data===undefined?{}:{body:JSON.stringify(data)})});
  const body=await response.json(); record('http',{path,status:response.status,request:data,response:body});
  assert(response.ok);return body.data;
};
const mode=(page,scope)=>expect(page.locator('[data-speaker-context]')).toHaveAttribute('data-speaker-context',scope);
const ready=page=>expect(page.locator('.chat-history')).toHaveAttribute('data-history-ready','true');
const settled=async page=>{await expect(page.getByRole('button',{name:'等待回复…',exact:true})).toHaveCount(0);await ready(page);};
const controls=async(page,button,scope)=>{await page.getByRole('button',{name:button,exact:true}).click();await settled(page);await mode(page,scope);};
const send=async(page,text)=>{await page.getByLabel('消息',{exact:true}).fill(text);await page.getByRole('button',{name:'发送消息',exact:true}).click();await settled(page);};
try{
  while(true){if(fixture.exitCode!==null)throw Error('Fixture exited early');try{if((await fetch(base)).ok)break;}catch{}await sleep(50);}
  const folders=readdirSync(tempRoot).filter(name=>name.startsWith('admin-e2e-')&&!prior.has(name));
  assert.equal(folders.length,1);const dbPath=join(tempRoot,folders[0],'browser.db');
  const database=()=>JSON.parse(execFileSync(join(root,'../envs/hhu-ai-avatar/bin/python'),['-c',
    'import sqlite3,json,sys; c=sqlite3.connect("file:"+sys.argv[1]+"?mode=ro",uri=True); c.row_factory=sqlite3.Row; print(json.dumps({t:[dict(r) for r in c.execute("SELECT * FROM "+t)] for t in ["memory_messages","memory_fragments","memory_reminders","memory_web_speaker_state"]},ensure_ascii=False))',dbPath],{encoding:'utf8'}));
  browser=await chromium.launch({headless:true});report.browserVersion=browser.version();
  page=await browser.newPage({viewport:{width:1440,height:900}});
  page.on('pageerror',error=>report.errors.push(error.message));
  page.on('request',request=>{const path=new URL(request.url()).pathname;
    if(request.method()==='POST'&&path==='/api/v1/turns')report.posts.push(request.postDataJSON());
    if(request.method()==='POST'&&path==='/api/v1/speech')report.speechPosts.push(request.postDataJSON());save();});
  await page.goto(base+'/chat#'+token);await ready(page);await mode(page,'current_user');
  await page.getByLabel('消息',{exact:true}).fill('提醒我明天下午3点去码头');
  await page.getByLabel('本轮允许联网工具',{exact:true}).check();await page.getByLabel('自动分段朗读新回复',{exact:true}).check();
  await controls(page,'进入角色','fictional_character');
  await expect(page.getByLabel('消息',{exact:true})).toHaveValue('提醒我明天下午3点去码头');
  assert.deepEqual(Object.keys(report.posts[0]).sort(),['request_id','text','use_web']);
  assert.equal(report.posts[0].text,'我来扮演一个虚构角色。');assert.equal(report.posts[0].use_web,false);
  assert.equal(report.speechPosts.length,0);await page.getByLabel('自动分段朗读新回复',{exact:true}).uncheck();
  let db=database();assert.equal(db.memory_reminders.length,0);assert.equal(db.memory_fragments.length,0);
  record('role-control-preserves-reminder-draft-no-side-effects',{db});
  await send(page,'我叫角色许照。');await mode(page,'fictional_character');
  db=database();assert.equal(db.memory_fragments.length,0);assert.equal(db.memory_reminders.length,0);
  assert.deepEqual(Object.keys(report.posts[1].expected_context).sort(),['context_cursor','instance_id','revision']);
  record('role-name-stays-out-of-real-profile',{db});
  const other=await browser.newPage({viewport:{width:390,height:844}});
  other.on('pageerror',error=>report.errors.push(error.message));
  await other.goto(base+'/chat#'+token);await ready(other);await mode(other,'fictional_character');
  await page.getByLabel('消息',{exact:true}).fill('尚未发送的本页草稿');
  const before=await page.locator('.chat-message').count();
  await controls(other,'以本人说话','current_user');await mode(page,'current_user');
  await expect(page.getByLabel('消息',{exact:true})).toHaveValue('尚未发送的本页草稿');
  assert.equal(await page.locator('.chat-message').count(),before);
  record('external-context-event-keeps-local-history-and-draft',{before,after:await page.locator('.chat-message').count()});
  await controls(other,'进入角色','fictional_character');await mode(page,'fictional_character');
  let observed=false;let release, finishRoute;
  const gate=new Promise(resolve=>{release=resolve;releaseHeld=resolve;});
  routeDone=new Promise(resolve=>{finishRoute=resolve;});
  const intercept=async route=>{
    observed=true;held=route;
    try{await gate;await route.continue();}
    catch(error){record('route-release-error',{message:String(error)});}
    finally{held=null;finishRoute();}
  };
  await page.route('**/api/v1/turns',intercept);
  await page.getByLabel('消息',{exact:true}).fill('我叫角色许照。');
  await page.getByRole('button',{name:'发送消息',exact:true}).click();
  await expect.poll(()=>observed).toBe(true);
  const external=await api('/turns',{request_id:randomUUID(),text:'回到现实。',use_web:false});
  const response=await fetch(base+'/api/v1/turns/'+external.job_id+'/events',{headers:{'X-Avatar-Token':token}});
  const raw=await response.text();assert(raw.includes('event: result'));record('external-real-control-sse',{raw});
  await mode(page,'current_user');
  // Ordinary source notification must not abort or erase the pending submission.
  assert(held);await expect(page.getByRole('button',{name:'停止生成',exact:true})).toBeVisible();
  release();await routeDone;await page.unroute('**/api/v1/turns',intercept);await settled(page);
  await expect(page.getByLabel('消息',{exact:true})).toHaveValue('我叫角色许照。');
  await expect(page.getByText('语境已变化，请确认当前模式后重新发送。',{exact:true})).toBeVisible();
  const rejected=report.posts.at(-1);const job=await api('/turns/'+rejected.request_id);
  assert.equal(job.status,'failed');db=database();assert.equal(db.memory_fragments.length,0);assert.equal(db.memory_reminders.length,0);
  assert.equal(db.memory_messages.filter(row=>row.role==='user'&&row.content==='我叫角色许照。').length,1);
  record('stale-ordinary-turn-rejected-no-source-or-replay',{job,db,posts:report.posts.length});
  await send(page,'我叫陈原。');await mode(page,'current_user');
  await send(page,'提醒我明天下午3点去图书馆');await mode(page,'current_user');
  db=database();assert(db.memory_fragments.some(row=>row.content.includes('陈原')));
  assert(!db.memory_fragments.some(row=>row.content.includes('许照')));
  assert.equal(db.memory_reminders.length,1);assert.equal(db.memory_reminders[0].title,'去图书馆');
  record('real-positive-controls',{db});
  for(const [name,target] of [['desktop',page],['mobile',other]]){
    await target.reload();await ready(target);await mode(target,'current_user');
    const snapshot=await api('/conversation/speaker');
    const state={name,context:await target.locator('[data-speaker-context]').getAttribute('data-speaker-context'),snapshot,
      roleButtons:await target.getByRole('button',{name:'进入角色',exact:true}).count(),
      realButtons:await target.getByRole('button',{name:'以本人说话',exact:true}).count(),
      overflow:await target.evaluate(()=>document.documentElement.scrollWidth>innerWidth)};
    assert.equal(state.roleButtons,1);assert.equal(state.realButtons,1);assert.equal(state.overflow,false);
    await target.screenshot({path:join(ev,'browser-context-controls-'+name+'.png'),fullPage:true});record('reload-viewport',state);
  }
  assert.equal(report.errors.length,0);assert.deepEqual(fingerprint(),report.sourceSha256);report.completed=true;
}catch(error){report.failure=String(error);if(page)await page.screenshot({path:join(ev,'browser-context-controls-failure.png'),fullPage:true}).catch(()=>{});}
finally{
  releaseHeld?.();
  if(routeDone)await routeDone;
  if(browser)await browser.close();
  if(fixture.exitCode===null)fixture.kill('SIGTERM');const[code]=await exited;report.fixtureExit=code;closeSync(log);save();
}
assert(report.completed,report.failure);assert.equal(report.fixtureExit,0);
console.log(JSON.stringify({completed:true,steps:report.steps.length,posts:report.posts.length,fixturePid:report.fixturePid,fixtureExit:report.fixtureExit}));
