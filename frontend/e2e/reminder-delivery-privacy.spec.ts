import { test, expect } from '@playwright/test';
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
const token='mission-control-disposable-e2e-token';
test('in-flight reminder snapshots respect external privacy revision before client acknowledgement',async({page},info)=>{
  test.skip(process.env.AVATAR_E2E_REMINDER_PRIVACY_AUDIT!=='1','explicit disposable privacy audit only');test.setTimeout(0);
  const folder=process.env.AVATAR_E2E_EVIDENCE_DIR??info.outputDir;mkdirSync(folder,{recursive:true});const output=join(folder,'privacy-browser.json');
  if(existsSync(output))throw Error('Fresh evidence required');
  const files=(p:string):string[]=>readdirSync(p,{withFileTypes:true}).flatMap(e=>e.isDirectory()?files(join(p,e.name)):[join(p,e.name)]);
  const inputs=[...files('src'),...files('../src/avatar').filter(p=>p.endsWith('.py')),...files('dist'),'e2e/reminder-delivery-privacy.spec.ts','../tests/helpers/serve_admin_e2e.py'];
  const report:Record<string,unknown>={head:execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim(),completed:false,
    scope:'Actual Chromium, authenticated external forget draft/confirmation, paused old and new pending responses. Legal reminders persist; client confirmation is not human-read proof.',
    sourceSha256:Object.fromEntries(inputs.map(p=>[p,createHash('sha256').update(readFileSync(p)).digest('hex')]))};
  const save=()=>writeFileSync(output,JSON.stringify(report,null,2)+'\n');save();const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  const calls:unknown[]=[];
  const api=async(path:string,data?:unknown)=>{
    const r=await page.request.fetch('/api/v1'+path,{method:data===undefined?'GET':'POST',headers:{'X-Avatar-Token':token},...(data===undefined?{}:{data})});
    const envelope=await r.json();calls.push({path,status:r.status(),envelope});return{status:r.status(),...envelope};
  };
  let releaseOld!:()=>void,releaseFresh!:()=>void;const oldGate=new Promise<void>(r=>{releaseOld=r;}),freshGate=new Promise<void>(r=>{releaseFresh=r;});
  const snapshots:{data:{instance_id:string;revision:number;items:{delivery_id:number;id:number}[]}}[]=[];let oldProcessed=false;
  await page.route('**/api/v1/reminders/deliveries/pending',async route=>{
    const r=await route.fetch();const body=await r.json();const index=snapshots.length;snapshots.push(body);
    if(index===0)await oldGate;else if(index===1)await freshGate;
    try{await route.fulfill({response:r});}catch(error){if(index!==0)throw error;report.oldReleaseDiagnostic=String(error);}
    finally{if(index===0)oldProcessed=true;}
  });
  const notice=()=>page.locator('.notice[role="status"]').filter({hasText:'到期提醒'});
  try{
    const chat=await api('/chat',{text:'我叫队列审计名'});expect(chat.status).toBe(200);
    const memories=await api('/memory');const fragment=memories.data.find((r:{content:string})=>r.content.includes('队列审计名'));expect(fragment).toBeTruthy();
    await page.goto('/reminders#'+token);await expect.poll(()=>snapshots.length,{timeout:30000}).toBe(1);
    const old=snapshots[0].data;expect(old.items).toHaveLength(1);await expect(notice()).toHaveCount(0);
    const draft=await api('/memory/batch-draft',{actions:[{action:'forget',id:fragment.id}]});expect(draft.status).toBe(201);
    const confirmed=await api('/operations/'+draft.data.draft_id+'/confirm',{confirmation_token:draft.data.confirmation_token});expect(confirmed.status).toBe(200);
    await expect.poll(()=>snapshots.length,{timeout:30000}).toBe(2);const fresh=snapshots[1].data;
    expect(fresh.revision).toBeGreaterThan(old.revision);expect(fresh.items[0].delivery_id).toBe(old.items[0].delivery_id);
    releaseOld();await expect.poll(()=>oldProcessed,{timeout:15000}).toBe(true);
    await expect(notice()).toHaveCount(0);report.oldResponseDidNotInstallWhileNewResponseHeld=true;
    const event=old.items[0];const rejected=await api('/reminders/deliveries/'+event.delivery_id+'/ack',{instance_id:old.instance_id,revision:old.revision});
    expect(rejected.status).toBe(409);expect(rejected.error.code).toBe('delivery_revision_changed');report.staleAck=rejected;
    await page.screenshot({path:join(folder,'old-response-discarded.png'),fullPage:true});
    releaseFresh();await expect(notice()).toBeVisible();
    await page.getByRole('button',{name:'确认已看到提醒 #'+event.id,exact:true}).click();await expect(notice()).toHaveCount(0,{timeout:30000});
    await expect(page.getByRole('row').filter({hasText:'到期投递实验提醒'})).toContainText('网页已确认（客户端）');
    report.finalPending=(await api('/reminders/deliveries/pending',{})).data;expect((report.finalPending as {items:unknown[]}).items).toEqual([]);
    report.snapshots=snapshots;report.externalRequests=calls;report.errors=errors;expect(errors).toEqual([]);report.completed=true;save();
  }catch(error){report.failure=String(error);report.snapshots=snapshots;report.externalRequests=calls;report.errors=errors;save();throw error;}
  finally{releaseOld();releaseFresh();}
});
