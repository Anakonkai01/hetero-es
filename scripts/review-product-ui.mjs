/** Read-only live UI review. No dispatch, device changes, or GPU compute. */
import {chromium} from 'playwright';
import {readFile,mkdir,writeFile} from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
const base=process.env.HETEROES_UI_URL??'http://100.110.165.40:5181';
const root=process.env.HETEROES_PRIVATE_CONFIG??path.join(os.homedir(),'.config/heteroes-m2');
const output=process.env.HETEROES_UI_EVIDENCE??path.join(os.homedir(),'.local/share/heteroes-ui-review');
await mkdir(output,{recursive:true,mode:0o700});
const browser=await chromium.launch({headless:true});
const errors=[];const responses=[];const checks=[];
try{
 for(const theme of ['light','dark']){
  const context=await browser.newContext({viewport:{width:1440,height:1000}});
  await context.addInitScript(({theme})=>localStorage.setItem('heteroes.preferences',JSON.stringify({language:'vi',theme,accent:'teal'})),{theme});
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  page.on('response',r=>{if(r.status()>=400&&r.url().includes('/api/'))responses.push({path:new URL(r.url()).pathname,status:r.status()});});
  for(const route of ['/','/register','/login']){await page.goto(base+route);await page.waitForTimeout(700);await page.screenshot({path:path.join(output,`${theme}-${route==='/'?'home':route.slice(1)}.png`),fullPage:true});checks.push({theme,route,overflow:await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)});}
  await page.setViewportSize({width:390,height:844});
  for(const route of ['/register','/login']){await page.goto(base+route);await page.waitForTimeout(500);await page.screenshot({path:path.join(output,`${theme}-mobile-${route.slice(1)}.png`),fullPage:true});checks.push({theme,route,mobile:true,anonymousFormVisible:await page.locator('input[autocomplete=username]').isVisible(),overflow:await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)});}
  await page.setViewportSize({width:1440,height:1000});await page.goto(base+'/login');
  const credentials=JSON.parse(await readFile(path.join(root,'credentials.json'),'utf8'));
  await page.getByLabel('Tên đăng nhập',{exact:true}).fill('admin');await page.locator('input[autocomplete=current-password]').fill(credentials.users.admin);
  await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();await page.waitForURL('**/workspace');
  for(const route of ['/dashboard','/workspace','/workers','/workers/5070ti','/experiments','/experiments/new','/models','/events','/artifacts','/profile','/operations']){await page.goto(base+route);await page.waitForTimeout(900);await page.screenshot({path:path.join(output,`${theme}-${route.slice(1).replaceAll('/','-')}.png`),fullPage:true});checks.push({theme,route,overflow:await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)});}
  const token=await page.evaluate(()=>sessionStorage.getItem('heteroes.access-token'));
  const response=await page.request.get(base+'/api/v1/experiments',{headers:{Authorization:'Bearer '+token,'X-Workspace-Id':'lab'}});
  let runPath;
  if(response.ok()){
   const experiments=await response.json();const run=experiments.find(e=>e.completedGenerations>0);
   if(run){runPath='/experiments/'+run.experimentId;await page.goto(base+runPath);await page.waitForTimeout(900);await page.screenshot({path:path.join(output,`${theme}-experiment.png`),fullPage:true});checks.push({theme,route:'experiment',seedVisible:await page.locator('.inspector-table').count()>0,overflow:await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)});
    const candidate=await page.locator('.inspector-table tbody tr td:first-child a').first().getAttribute('href');
    const generation=await page.locator('.experiment-inspector > p a').first().getAttribute('href');
    for(const [name,route] of [['candidate',candidate],['generation',generation]])if(route){await page.goto(base+route);await page.waitForTimeout(700);await page.screenshot({path:path.join(output,`${theme}-${name}.png`),fullPage:true});checks.push({theme,route:name,overflow:await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)});}
   }
  }
  await page.setViewportSize({width:390,height:844});
  for(const route of ['/','/dashboard','/workers','/workers/5070ti','/experiments','/experiments/new',...(runPath?[runPath]:[])] ){await page.goto(base+route);await page.waitForTimeout(700);await page.screenshot({path:path.join(output,`${theme}-mobile-${route.slice(1).replaceAll('/','-')||'home'}.png`),fullPage:true});checks.push({theme,route,mobile:true,overflow:await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)});}
  await context.close();
 }
 const result={readOnly:true,gpuCompute:false,checks,browserErrors:errors,apiErrors:responses};await writeFile(path.join(output,'web-review.json'),JSON.stringify(result,null,2),{mode:0o600});
 console.log(JSON.stringify(result));if(errors.length||checks.some(c=>c.overflow||c.seedVisible===false||c.anonymousFormVisible===false)||responses.some(r=>r.status!==401||r.path!=='/api/v1/auth/session'))process.exitCode=1;
}finally{await browser.close();}
