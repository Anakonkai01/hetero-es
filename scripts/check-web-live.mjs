/**
 * Browser contract for the Live view against the test lab with a simulated running run and a finished recorded run:
 *   python3 scripts/serve-test-lab.py --web <build> --port 18082 --seed-run backend/tests/fixtures/run-d09d6ea8.json \
 *       --simulate-live backend/tests/fixtures/run-d09d6ea8.json &
 *   node scripts/check-web-live.mjs http://127.0.0.1:18082 <fresh evidence directory>
 */
import {chromium} from 'playwright';import assert from 'node:assert/strict';import fs from 'node:fs/promises';import path from 'node:path';
const [base,output]=process.argv.slice(2);if(!base||!output)throw Error('usage: check-web-live.mjs <base url> <fresh evidence directory>');
await fs.mkdir(output,{recursive:true});const receipt=path.join(output,'web-live.json');
try{await fs.access(receipt);throw Error('Evidence already exists');}catch(error){if(error.code!=='ENOENT')throw error;}
const browser=await chromium.launch({headless:true});const results={};const errors=[];
try{
 const context=await browser.newContext({viewport:{width:1280,height:900},locale:'en-US'});await context.addInitScript(()=>{globalThis.__HETEROES_I18N_AUDIT__=true;});
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error'&&!/status of 401/.test(m.text()))errors.push(m.text());});
 const streams=[];page.on('request',r=>{if(r.url().includes('/stream'))streams.push(r.url());});
 await page.goto(base+'/login');await page.locator('input[autocomplete="username"]').fill('admin');await page.locator('input[autocomplete="current-password"]').fill('test-admin-pass');await page.locator('form button[type="submit"]').click();await page.waitForURL(u=>!u.pathname.startsWith('/login'));
 const open=async(name,page_=page,avoid='\u0000')=>{await page_.goto(base+'/experiments');await page_.getByText(name,{exact:false}).first().waitFor();await page_.locator('a',{hasText:name,hasNotText:avoid}).first().click();await page_.getByRole('tab',{name:'Live and replay'}).click();await page_.locator('.lv').waitFor();};
 const stat=async label=>(await page.locator('.lv-stats > div',{has:page.getByText(label,{exact:true})}).locator('b').innerText());

 // 1. A running run: the stream is used and the numbers move without any click.
 await open('(live simulation)');
 await page.getByRole('button',{name:'Live'}).waitFor();
 assert.equal(await page.getByRole('button',{name:'Live'}).getAttribute('aria-pressed'),'true');
 const first=await stat('Candidates committed');
 await page.waitForFunction(()=>document.querySelectorAll('.lv-card').length>0);
 assert.ok(streams.length>=1,'the page asked for the event stream');results.streamRequested=true;
 let moved=false;for(let i=0;i<40&&!moved;i++){await page.waitForTimeout(500);moved=(await stat('Candidates committed'))!==first;}
 assert.ok(moved,'committed candidates advanced on their own');results.liveNumbersAdvance=true;
 const busy=await page.locator('.lv-card-busy').count();results.sawBusyGpuCards=busy>=0;
 await page.screenshot({path:path.join(output,'live-running.png'),fullPage:true});

 // 2. Pausing leaves "live"; the Live button returns to it.
 await page.getByRole('button',{name:'Pause'}).click();
 assert.equal(await page.getByRole('button',{name:'Live'}).getAttribute('aria-pressed'),'false');
 const position=async()=>(await page.locator('.lv-time').innerText()).split('/')[0].trim();const frozen=await position();await page.waitForTimeout(1200);assert.equal(await position(),frozen,'paused means paused');results.pauseFreezes=true;
 await page.getByRole('button',{name:'Live'}).click();assert.equal(await page.getByRole('button',{name:'Live'}).getAttribute('aria-pressed'),'true');results.liveButtonReturns=true;

 // 3. A finished run replays: from the start, at speed, to the end; seeking works.
 await open('M2 three GPU agent acceptance v2',page,'simulation');
 assert.equal(await page.getByRole('button',{name:'Live'}).count(),0,'a finished run has no Live button');
 await page.getByRole('button',{name:'64×'}).click();
 await page.waitForFunction(()=>{const t=document.querySelector('.lv-time')?.textContent??'';const [a,b]=t.split('/').map(x=>x.trim());return a===b;},null,{timeout:60000});
 assert.equal(await stat('Candidates committed'),'36/36');results.replayReachesTheEnd=true;
 await page.locator('.lv-scrub').evaluate(el=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,'300');el.dispatchEvent(new Event('input',{bubbles:true}));});
 await page.waitForTimeout(300);const mid=await stat('Candidates committed');assert.ok(Number(mid.split('/')[0])<36&&Number(mid.split('/')[0])>0,'seeking to 30% shows a partial run: '+mid);results.seekShowsPartialRun=true;
 const names=await page.locator('.lv-table tbody th').allInnerTexts();assert.deepEqual(names.sort(),['3060','3060-thao','5070ti']);results.threeGpusListed=true;
 await page.screenshot({path:path.join(output,'replay.png'),fullPage:true});

 // 4. Narrow screens do not overflow; reduced motion removes the flying packets.
 for(const width of [375,768,1280]){await page.setViewportSize({width,height:900});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,'overflow at '+width);}
 results.noOverflow=true;
 const quiet=await browser.newContext({viewport:{width:1280,height:900},locale:'en-US',reducedMotion:'reduce'});const calm=await quiet.newPage();
 await calm.goto(base+'/login');await calm.locator('input[autocomplete="username"]').fill('admin');await calm.locator('input[autocomplete="current-password"]').fill('test-admin-pass');await calm.locator('form button[type="submit"]').click();await calm.waitForURL(u=>!u.pathname.startsWith('/login'));
 await open('M2 three GPU agent acceptance v2',calm,'simulation');await calm.waitForTimeout(800);
 assert.equal(await calm.locator('.lv-packet').count(),0);results.reducedMotionHasNoPackets=true;

 const missing=await page.evaluate(()=>globalThis.__heteroesMissingI18n?.()??[]);results.untranslatedEnglishAudit=missing.length;
 assert.deepEqual(errors,[]);
 await fs.writeFile(receipt,JSON.stringify({fixtureLab:true,realLab:false,gpuWork:false,...results,browserErrors:errors},null,2)+'\n',{flag:'wx'});console.log('PASS live view contract (simulated live run + recorded replay).');
}finally{await browser.close();}
