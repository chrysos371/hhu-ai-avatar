import { test, expect } from '@playwright/test';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';

const token='mission-control-disposable-e2e-token';
test('records audio ownership before and after twenty actual route commits', async ({ page },info) => {
  test.skip(process.env.AVATAR_E2E_NAVIGATION_AUDIO!=='1','explicit navigation/audio diagnosis');test.setTimeout(0);
  const folder=process.env.AVATAR_E2E_EVIDENCE_DIR??info.outputDir;mkdirSync(folder,{recursive:true});
  const output=join(folder,'navigation-audio.json');if(existsSync(output))throw Error('Use fresh navigation evidence');
  const names=['src/features/chat/useSpeechPlayer.ts','src/features/chat/ChatPage.tsx','e2e/speech.spec.ts',
    'e2e/navigation-audio-audit.spec.ts','../tests/helpers/serve_admin_e2e.py','dist/index.html'];
  const report:{scope:string;head:string;sourceSha256:Record<string,string>;rounds:unknown[];errors:string[];completed:boolean;failure?:string}={
    scope:'Real Chromium, actual PCM and controlled local app HTTP, fixed20 route transitions. No physical audio/model quality or field incidence claim.',
    head:execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim(),
    sourceSha256:Object.fromEntries(names.map(path=>[path,createHash('sha256').update(readFileSync(path)).digest('hex')])),
    rounds:[],errors:[],completed:false};
  const save=()=>writeFileSync(output,JSON.stringify(report,null,2)+'\n');save();
  page.on('pageerror',error=>report.errors.push(error.message));
  try {
    for(let index=0;index<20;index++){
      await page.goto('/chat#'+token);
      await expect(page.locator('.chat-history')).toHaveAttribute('data-history-ready','true');
      if(await page.getByRole('button',{name:'朗读回复',exact:true}).count()===0){
        await page.getByLabel('消息',{exact:true}).fill('你好');
        await page.getByRole('button',{name:'发送消息',exact:true}).click();
        await expect(page.getByRole('button',{name:'朗读回复',exact:true}).last()).toBeVisible();
      }
      await page.getByRole('button',{name:'朗读回复',exact:true}).last().click();
      const player=page.getByLabel(/语音播放器$/);
      await expect.poll(()=>player.evaluate((audio:HTMLAudioElement)=>audio.currentTime)).toBeGreaterThan(.05);
      const audio=await player.elementHandle();if(!audio)throw Error('Missing owned audio');
      await audio.evaluate((element:HTMLAudioElement)=>{
        const samples:unknown[]=[];
        Object.assign(window,{__navigationAudio:samples});
        function sample(){
          samples.push({wall:performance.now(),chatPresent:!!document.querySelector('.chat-history'),
            heading:document.querySelector('h1')?.textContent,paused:element.paused,src:element.hasAttribute('src'),
            connected:element.isConnected,mediaTime:element.currentTime});
          if(samples.length<30)requestAnimationFrame(sample);
        }requestAnimationFrame(sample);
      });
      await page.getByRole('link',{name:'总览',exact:true}).click();
      const immediate=await audio.evaluate((element:HTMLAudioElement)=>({wall:performance.now(),
        heading:document.querySelector('h1')?.textContent,chatPresent:!!document.querySelector('.chat-history'),
        connected:element.isConnected,paused:element.paused,src:element.hasAttribute('src')}));
      await expect(page.getByRole('heading',{name:'数字人大脑总览',exact:true})).toBeVisible();
      const committed=await audio.evaluate((element:HTMLAudioElement)=>({wall:performance.now(),
        heading:document.querySelector('h1')?.textContent,chatPresent:!!document.querySelector('.chat-history'),
        connected:element.isConnected,paused:element.paused,src:element.hasAttribute('src')}));
      const samples=await page.evaluate(async()=>{
        const target=window as unknown as {__navigationAudio:unknown[]};
        while(target.__navigationAudio.length<30)await new Promise(requestAnimationFrame);
        return target.__navigationAudio;
      });
      report.rounds.push({index,immediate,committed,samples});save();
      // Diagnose without discarding failing observations; final classification
      // uses every recorded commit/frame, never retries until one happens to pass.
    }
    expect(report.errors).toEqual([]);report.completed=true;
  }catch(error){report.failure=String(error);throw error;}
  finally{save();}
});
