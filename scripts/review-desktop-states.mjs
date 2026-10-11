/** Renderer fixtures: isolated UI states, never device/GPU acceptance evidence. */
import {chromium} from 'playwright';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';

const output=process.env.HETEROES_UI_EVIDENCE??path.join(os.homedir(),'.local/share/heteroes-ui-review');
await mkdir(output,{recursive:true,mode:0o700});
const now=Date.now()/1000;
const sample=JSON.parse(await readFile(path.join(output,'telemetry-sample.json'),'utf8'));
const observation={...sample.observation,sampledAt:now,receivedAt:now};
const history=sample.history.map(p=>({...p,at:now-(sample.history.at(-1).at-p.at)}));
const setup={installed:true,running:false,profileAvailable:true,progress:{stage:'ready'}};
const device={deviceId:'fixture-device',workerId:'fixture-worker',displayName:'UI review fixture',approvalStatus:'APPROVED'};
const base={serverUrl:'http://lab.invalid:8000',signedIn:true,session:{user:{displayName:'Fixture user'}},connection:'ONLINE',device,selfTest:{passed:true,gpuName:observation.gpu.name,gpuUUID:observation.gpu.uuid,vramTotalMb:observation.gpu.vramTotalMb},setup,telemetry:observation,telemetryHistory:history,agent:{enabled:false,drained:true,assignments:[]}};
const assignment={assignmentId:'fixture-assignment-with-a-long-identifier-20261011',epoch:2,ready:true,workerAlive:true,coordinatorAlive:false};
const states=[
 ['worker','off',base,false],
 ['worker','active',{...base,agent:{enabled:true,drained:false,assignments:[assignment]}},false],
 ['worker','draining',{...base,agent:{enabled:false,drained:false,assignments:[assignment]}},true],
 ['worker','unknown',{...base,agent:{enabled:false,drained:false,assignments:[{...assignment,workerAlive:null}]}},true],
 ['worker','approval',{...base,device:{...device,approvalStatus:'PENDING'}},true],
 ['worker','stale',{...base,connection:'OFFLINE',telemetry:{...observation,sampledAt:now-100,receivedAt:now-100}},false],
 ['worker','missing',{...base,telemetry:null,telemetryHistory:[]},false],
 ['worker','signin',{...base,device:undefined,signedIn:false},false],
 ['worker','install',{...base,device:undefined,selfTest:undefined,setup:{...setup,installed:false}},false],
 ['worker','pair',{...base,device:undefined},false],
 ['server','setup',{setup,initialized:false,running:false,addresses:['127.0.0.1','100.64.0.1'],apiUrl:null,storageDirectory:null,autostart:false},false],
 ['server','online',{setup,initialized:true,running:true,addresses:['127.0.0.1'],apiUrl:'http://lab.invalid:8000',storageDirectory:'/mnt/artifact-disk/heteroes-artifacts',autostart:false,resourceTelemetry:observation,telemetryHistory:history},false],
 ['server','error',{setup,initialized:true,running:false,error:'LAB_ADDRESS_UNAVAILABLE',addresses:['127.0.0.1'],apiUrl:'http://lab.invalid:8000',storageDirectory:'/mnt/artifact-disk/heteroes-artifacts',autostart:false,resourceTelemetry:observation,telemetryHistory:history},false],
];
const browser=await chromium.launch({headless:true});const results=[];
try{
 for(const [name,stateName,state,mustBlock] of states){
  for(const theme of ['light','dark']){
   const context=await browser.newContext({viewport:{width:1100,height:900}});
   await context.addInitScript(({name,state,theme})=>{
    localStorage.setItem('heteroes.preferences',JSON.stringify({language:'vi',theme,accent:'teal'}));
    window[name==='worker'?'worker':'labServer']={call:async action=>action==='status'?{ok:true,result:state}:{ok:false,error:'FIXTURE_ACTION_DISABLED'}};
   },{name,state,theme});
   const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
   await page.route('**/*',async route=>{
    const url=new URL(route.request().url());
    if(url.hostname!=='desktop.invalid')throw Error('Fixture attempted an external request');
    const relative=decodeURIComponent(url.pathname).replace(/^\//,'');
    if(relative.includes('..'))throw Error('Invalid fixture resource');
    const file=path.resolve('desktop',name,'dist',relative||'index.html');
    const contentType=file.endsWith('.html')?'text/html':file.endsWith('.js')?'application/javascript':file.endsWith('.css')?'text/css':file.endsWith('.woff2')?'font/woff2':'application/octet-stream';
    await route.fulfill({body:await readFile(file),contentType});
   });
   await page.goto('http://desktop.invalid/index.html');await page.waitForTimeout(250);
   const disabled=mustBlock?await page.locator('.contribution button').isDisabled():undefined;
   const checks=[];
   for(const view of ['overview','detail']){
    const monitor=page.locator('.resource-telemetry');
    if(await monitor.count())await monitor.getByRole('button',{name:view==='overview'?'Tổng quan':'Chi tiết',exact:true}).click();
    for(const textSize of ['standard','large']){
     await page.evaluate(size=>document.documentElement.dataset.textSize=size,textSize);
     for(const width of [1100,390]){
      await page.setViewportSize({width,height:900});
      await page.waitForTimeout(50);
      const layout=await page.evaluate(()=>{
       const overlaps=[];
       for(const card of document.querySelectorAll('.telemetry-metric')){
        const a=card.querySelector('dt').getBoundingClientRect(),b=card.querySelector('dd').getBoundingClientRect();
        if(a.bottom>b.top+.5)overlaps.push(card.querySelector('dt').textContent);
       }
       return {overflow:document.documentElement.scrollWidth>innerWidth,metricOverlaps:overlaps};
      });
      checks.push({view,textSize,width,...layout});
     }
    }
    if(await monitor.count()){
     for(const label of ['Phiên','Hôm nay','Tháng này','Toàn bộ lịch sử'])await monitor.getByRole('button',{name:label,exact:true}).click();
     await page.setViewportSize({width:1100,height:900});
     await page.screenshot({path:path.join(output,`fixture-${name}-${stateName}-${theme}-${view}.png`),fullPage:true});
    }
   }
   await page.setViewportSize({width:1100,height:900});
   await page.screenshot({path:path.join(output,`fixture-${name}-${stateName}-${theme}.png`),fullPage:true});
   await page.setViewportSize({width:390,height:844});checks.push({width:390,overflow:await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)});
   results.push({name,state:stateName,theme,fixture:true,hardwareAcceptance:false,checks,browserErrors:errors,enableBlocked:disabled});
   await context.close();
  }
 }
 await writeFile(path.join(output,'desktop-states-review.json'),JSON.stringify(results,null,2),{mode:0o600});
 console.log(JSON.stringify({states:results.length,browserErrors:results.flatMap(r=>r.browserErrors),overflow:results.filter(r=>r.checks.some(c=>c.overflow||c.metricOverlaps?.length)),blockedChecksPassed:results.filter(r=>r.enableBlocked===false).length===0}));
 if(results.some(r=>r.browserErrors.length||r.checks.some(c=>c.overflow||c.metricOverlaps?.length)||r.enableBlocked===false))process.exitCode=1;
}finally{await browser.close();}
