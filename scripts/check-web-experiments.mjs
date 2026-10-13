/**
 * Browser contract for the experiment tools (compare, run again, templates, exports) against the test lab seeded with two
 * recorded runs:
 *   python3 scripts/serve-test-lab.py --web <build> --port 18084 --seed-run backend/tests/fixtures/run-d09d6ea8.json --seed-run backend/tests/fixtures/run-95b34770.json &
 *   node scripts/check-web-experiments.mjs http://127.0.0.1:18084 <fresh evidence directory>
 */
import {chromium} from 'playwright';import assert from 'node:assert/strict';import fs from 'node:fs/promises';import path from 'node:path';
const [base,output]=process.argv.slice(2);if(!base||!output)throw Error('usage: check-web-experiments.mjs <base url> <fresh evidence directory>');
await fs.mkdir(output,{recursive:true});const receipt=path.join(output,'web-experiments.json');
try{await fs.access(receipt);throw Error('Evidence already exists');}catch(error){if(error.code!=='ENOENT')throw error;}
const browser=await chromium.launch({headless:true});const results={};const errors=[];
try{
 const context=await browser.newContext({viewport:{width:1280,height:900},locale:'en-US',acceptDownloads:true});await context.addInitScript(()=>{globalThis.__HETEROES_I18N_AUDIT__=true;});
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error'&&!/status of (401|404)/.test(m.text()))errors.push(m.text());});
 await page.goto(base+'/login');await page.locator('input[autocomplete="username"]').fill('admin');await page.locator('input[autocomplete="current-password"]').fill('test-admin-pass');await page.locator('form button[type="submit"]').click();await page.waitForURL(u=>!u.pathname.startsWith('/login'));

 const choose=async text=>{const value=await page.locator('#template-picker option').evaluateAll((options,needle)=>options.find(o=>o.textContent.includes(needle))?.value,text);assert.ok(value,'template option '+text);await page.getByLabel('Start from').selectOption(value);};
 // 1. Pick two runs and compare them.
 await page.goto(base+'/experiments');await page.locator('.run-card').first().waitFor();
 await page.getByText('Compare',{exact:true}).first().waitFor();
 const picks=page.locator('.compare-pick-card input');assert.ok(await picks.count()>=2);
 await picks.nth(0).check();await page.getByText('1 selected · pick one more').waitFor();assert.equal(await page.locator('.compare-bar .btn.pri').isDisabled(),true);
 await picks.nth(1).check();await page.getByText('2 selected').waitFor();assert.equal(await page.locator('.compare-bar .btn.pri').isDisabled(),false);
 results.selectionBar=true;
 await page.locator('.compare-bar .btn.pri').click();await page.waitForURL('**/experiments/compare?ids=*');
 await page.locator('.compare-chart').waitFor();await page.getByRole('heading',{name:'What was different'}).waitFor();
 assert.equal(await page.locator('.compare-legend li').count(),2);results.compareShowsTwoRuns=true;
 assert.ok(await page.locator('.compare-chart path').count()>=4,'two series, mean and best');results.compareChartDrawn=true;
 const download=page.waitForEvent('download');await page.getByRole('button',{name:'Table (CSV)'}).click();const file=await download;assert.equal(file.suggestedFilename(),'comparison.csv');
 const csv=await fs.readFile(await file.path(),'utf8');assert.match(csv.split('\n')[0],/^run,status,best_reward/);assert.equal(csv.trim().split('\n').length,3);results.compareCsv=true;
 await page.screenshot({path:path.join(output,'compare.png'),fullPage:true});
 await page.goto(base+'/experiments/compare?ids=only-one');await page.getByText('Pick at least two experiments').waitFor();results.needsTwoRuns=true;

 // 2. A run: export, save as template, run again.
 await page.goto(base+'/experiments');await page.locator('a',{hasText:'M2 three GPU agent acceptance v2'}).first().click();
 await page.getByRole('button',{name:'Run again like this'}).waitFor();
 const csvDownload=page.waitForEvent('download');await page.getByText('Export ▾').click();await page.getByRole('menuitem',{name:'Generations (CSV)'}).click();
 const generations=await csvDownload;assert.match(generations.suggestedFilename(),/generations\.csv$/);const text=await fs.readFile(await generations.path(),'utf8');assert.match(text,/^generation,status,candidates,committed,reward_mean,reward_best/);assert.equal(text.trim().split('\n').length,4);results.generationsCsv=true;
 const png=page.waitForEvent('download');await page.getByText('Export ▾').click();await page.getByRole('menuitem',{name:'Reward chart (PNG)'}).click();const image=await png;
 const bytes=await fs.readFile(await image.path());assert.equal(bytes.subarray(1,4).toString(),'PNG');results.chartPng=true;
 const md=page.waitForEvent('download');await page.getByText('Export ▾').click();await page.getByRole('menuitem',{name:'One-page summary (Markdown)'}).click();const summary=await md;
 assert.match(await fs.readFile(await summary.path(),'utf8'),/^# M2 three GPU agent acceptance v2/);results.markdownSummary=true;

 await page.getByRole('button',{name:'Save settings as template'}).click();await page.getByLabel('Template name').fill('Three GPU 3x12');await page.getByRole('button',{name:'Save',exact:true}).click();
 await page.getByText('Template saved.').waitFor();results.templateSaved=true;
 await page.getByRole('button',{name:'Run again like this'}).click();await page.waitForURL('**/experiments/new');
 assert.equal(await page.getByLabel('Experiment name').inputValue(),'M2 three GPU agent acceptance v2 (copy)');
 assert.equal(await page.getByLabel('Candidates per generation').inputValue(),'12');assert.equal(await page.getByLabel('Maximum generations').inputValue(),'3');results.runAgainPrefills=true;
 await choose('Three GPU 3x12');
 assert.equal(await page.getByLabel('Experiment name').inputValue(),'Three GPU 3x12');assert.equal(await page.getByLabel('Candidates per generation').inputValue(),'12');results.savedTemplateApplies=true;
 await choose('Quick smoke test');assert.equal(await page.getByLabel('Candidates per generation').inputValue(),'4');assert.equal(await page.getByLabel('Experiment name').inputValue(),'');results.builtInTemplateApplies=true;
 await page.screenshot({path:path.join(output,'create-from-template.png'),fullPage:true});
 page.once('dialog',d=>d.accept());await choose('Three GPU 3x12');await page.getByRole('button',{name:'Delete template'}).click();
 await page.waitForFunction(()=>![...document.querySelectorAll('#template-picker option')].some(o=>o.textContent.includes('Three GPU 3x12')));results.templateDeleted=true;

 for(const width of [375,768,1280]){await page.setViewportSize({width,height:900});for(const url of ['/experiments','/experiments/compare?ids=a,b']){await page.goto(base+url);await page.waitForTimeout(500);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,`overflow ${url} ${width}`);}}results.noOverflow=true;
 const missing=await page.evaluate(()=>globalThis.__heteroesMissingI18n?.()??[]);results.untranslatedEnglishAudit=missing.length;
 assert.deepEqual(errors,[]);
 await fs.writeFile(receipt,JSON.stringify({fixtureLab:true,realLab:false,gpuWork:false,...results,browserErrors:errors},null,2)+'\n',{flag:'wx'});console.log('PASS experiment tools contract (fixture lab, Chromium).');
}finally{await browser.close();}
