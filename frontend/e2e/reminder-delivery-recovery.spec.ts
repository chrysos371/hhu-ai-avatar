import { test, expect } from '@playwright/test';
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
const token = 'mission-control-disposable-e2e-token';
const scenario = process.env.AVATAR_E2E_REMINDER_DELIVERY_CASE;
test('durable reminders recover faults and persist explicit client confirmation', async ({ page }, info) => {
  test.skip(!scenario, 'explicit disposable recovery protocol only'); test.setTimeout(0);
  if (!['normal_claim','response_drop_after_commit','navigation_before_response','ack_response_drop_after_commit'].includes(scenario!)) throw Error('Unknown case');
  const folder = process.env.AVATAR_E2E_EVIDENCE_DIR ?? info.outputDir; mkdirSync(folder,{recursive:true});
  const output = join(folder,'recovery-browser.json'); if (existsSync(output)) throw Error('Fresh output required');
  const files = (path:string): string[] => readdirSync(path,{withFileTypes:true}).flatMap(e => e.isDirectory() ? files(join(path,e.name)) : [join(path,e.name)]);
  const inputs = [...files('src'),...files('../src/avatar').filter(p=>p.endsWith('.py')),...files('dist'),
    'e2e/reminder-delivery-recovery.spec.ts','../tests/helpers/serve_admin_e2e.py','../evals/interaction/cycle-24/reminder-recovery-protocol.json'];
  const report: Record<string,unknown> = {case:scenario,completed:false,head:execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim(),
    scope:'Actual headless Chromium/HTTP/SQLite, controlled response faults; no physical notification or human-read proof.',virtualClock:false,
    sourceSha256:Object.fromEntries(inputs.map(p=>[p,createHash('sha256').update(readFileSync(p)).digest('hex')]))};
  const save = () => writeFileSync(output,JSON.stringify(report,null,2)+'\n'); save();
  const errors:string[]=[], failures:unknown[]=[], posts:string[]=[];
  page.on('pageerror',e=>errors.push(e.message)); page.on('requestfailed',r=>failures.push({url:r.url(),error:r.failure()?.errorText}));
  page.on('request',r=>{if(r.method()==='POST')posts.push(new URL(r.url()).pathname);});
  const pending: {data:{items:{delivery_id:number;id:number}[]}}[]=[]; const acks: {data:{acknowledged_at:number}}[]=[];
  let release!:()=>void, processed=0; const paused=new Promise<void>(r=>{release=r;});
  const notice=()=>page.locator('.notice[role="status"]').filter({hasText:'到期提醒'});
  await page.route('**/api/v1/reminders/deliveries/pending',async route=>{
    const response=await route.fetch(); const body=await response.json(); const first=pending.length===0; pending.push(body);
    try {
      if(first&&scenario==='response_drop_after_commit') await route.abort('failed');
      else {
        if(first&&scenario==='navigation_before_response') await paused;
        await route.fulfill({response});
      }
    } catch(error) { report.routeReleaseDiagnostic=String(error); if (!(first&&scenario==='navigation_before_response')) throw error; }
    finally {processed+=1;}
  });
  await page.route('**/api/v1/reminders/deliveries/*/ack',async route=>{
    const response=await route.fetch(); acks.push(await response.json());
    if(acks.length===1&&scenario==='ack_response_drop_after_commit') await route.abort('failed'); else await route.fulfill({response});
  });
  const list=async()=>{
    const r=await page.request.get('/api/v1/reminders',{headers:{'X-Avatar-Token':token}});expect(r.ok()).toBe(true);return(await r.json()).data;
  };
  try {
    await page.setViewportSize({width:1440,height:900}); await page.goto('/reminders#'+token);
    await expect(page.getByRole('heading',{name:'提醒',exact:true})).toBeVisible();
    await expect.poll(()=>pending.length,{timeout:30000}).toBe(1);
    const event=pending[0].data.items[0]; expect(event).toBeTruthy(); report.firstPending=pending[0];
    report.afterClaimList=await list(); expect((report.afterClaimList as {notified_at:unknown}[])[0].notified_at).not.toBeNull();
    if(scenario==='navigation_before_response'){
      await page.getByRole('link',{name:'总览',exact:true}).click();
      await expect(page.getByRole('heading',{name:'数字人大脑总览',exact:true})).toBeVisible();
      report.navigationBeforeRelease=true; release(); await expect.poll(()=>processed,{timeout:15000}).toBeGreaterThan(0);
      await page.getByRole('link',{name:'提醒',exact:true}).click();
    } else if(scenario==='response_drop_after_commit'){
      await expect.poll(()=>processed,{timeout:15000}).toBe(1); await expect(notice()).toHaveCount(0); report.firstDisplay=false;
      await page.reload();
    } else {await expect(notice()).toBeVisible();report.firstDisplay=true;await page.reload();}
    await expect(notice()).toBeVisible({timeout:30000});
    await expect.poll(()=>pending.length,{timeout:15000}).toBeGreaterThanOrEqual(2);
    expect(pending[1].data.items[0].delivery_id).toBe(event.delivery_id); expect(acks).toHaveLength(0);
    report.recoveredEvent=event;report.noAckBeforeExplicitClick=true;report.recoveredNotice=await notice().innerText();
    await page.screenshot({path:join(folder,'recovered-desktop.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:join(folder,'recovered-mobile.png'),fullPage:true});
    report.overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);expect(report.overflow).toBe(false);
    await page.getByRole('button',{name:'确认已看到提醒 #'+event.id,exact:true}).click();
    await expect.poll(()=>acks.length,{timeout:15000}).toBe(1);expect(acks[0].data.acknowledged_at).toBeTruthy();
    await expect(notice()).toHaveCount(0,{timeout:30000});
    const row=page.getByRole('row').filter({hasText:'到期投递实验提醒'});
    await expect(row).toContainText('网页已确认（客户端）',{timeout:30000});
    report.afterAckList=await list();report.ack=acks[0];
    await page.reload();await expect(row).toContainText('网页已确认（客户端）');
    const afterReload=page.waitForResponse(r=>r.url().endsWith('/reminders/deliveries/pending'));
    // An explicit read verifies the durable server state even if the page's
    // immediate post-reload read completed before waitForResponse registered.
    const check=await page.request.post('/api/v1/reminders/deliveries/pending',{headers:{'X-Avatar-Token':token},data:{}});
    report.finalPending=(await check.json()).data;expect((report.finalPending as {items:unknown[]}).items).toEqual([]);
    await expect(notice()).toHaveCount(0);report.finalList=await list();
    await page.screenshot({path:join(folder,'acknowledged-mobile.png'),fullPage:true});
    // Observe a browser read after reload; timing may be immediate or periodic.
    const next=await afterReload;expect((await next.json()).data.items).toEqual([]);
    report.pendingResponses=pending;report.acks=acks;report.posts=posts;report.errors=errors;report.requestFailures=failures;
    expect(errors).toEqual([]);report.completed=true;save();
  } catch(error){report.failure=String(error);report.pendingResponses=pending;report.acks=acks;report.errors=errors;report.requestFailures=failures;save();throw error;}
  finally{release();}
});
