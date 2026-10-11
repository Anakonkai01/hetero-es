/** Live read-only monitoring review: sizing, views, periods, and real sensor presence. */
import {chromium} from 'playwright';import {readFile,writeFile,mkdir} from 'node:fs/promises';import os from 'node:os';import path from 'node:path';
const output=process.env.HETEROES_UI_EVIDENCE??path.join(os.homedir(),'.local/share/heteroes-monitoring-review');await mkdir(output,{recursive:true,mode:0o700});
const browser=await chromium.launch({headless:true}),checks=[],errors=[];
try{
 const context=await browser.newContext({viewport:{width:1440,height:1000}});const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://100.110.165.40:5181/login');
 const credentials=JSON.parse(await readFile(path.join(os.homedir(),'.config/heteroes-m2/credentials.json'),'utf8'));
 await page.getByLabel('Tên đăng nhập',{exact:true}).fill('admin');await page.locator('input[autocomplete=current-password]').fill(credentials.users.admin);await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();await page.waitForURL('**/workspace');
 for(const theme of ['light','dark'])for(const language of ['vi','en']){
  await page.goto('http://100.110.165.40:5181/workers/5070ti');
  await page.evaluate(({theme,language})=>localStorage.setItem('heteroes.preferences',JSON.stringify({language,theme,accent:'teal'})),{theme,language});await page.reload();
  const monitor=page.locator('.resource-telemetry');await monitor.waitFor();
  for(const view of ['overview','detail']){
   await monitor.getByRole('button',{name:language==='vi'?(view==='overview'?'Tổng quan':'Chi tiết'):(view==='overview'?'Overview':'Detail'),exact:true}).click();
   for(const textSize of ['standard','large'])for(const width of [1440,768,390]){
    await page.setViewportSize({width,height:1000});await page.evaluate(size=>document.documentElement.dataset.textSize=size,textSize);await page.waitForTimeout(80);
    const layout=await page.evaluate(()=>{
     const overlaps=[];for(const e of document.querySelectorAll('.telemetry-metric')){const a=e.querySelector('dt').getBoundingClientRect(),b=e.querySelector('dd').getBoundingClientRect();if(a.bottom>b.top+.5)overlaps.push(e.querySelector('dt').textContent);}
     return {overflow:document.documentElement.scrollWidth>innerWidth,metricOverlaps:overlaps,cores:document.querySelectorAll('.telemetry-cores>div').length,energyRows:document.querySelectorAll('.telemetry-energy-table tbody tr').length};
    });checks.push({theme,language,view,textSize,width,...layout});
    if(language==='vi'&&textSize==='standard'&&width===1440){await monitor.scrollIntoViewIfNeeded();await page.screenshot({path:path.join(output,`live-monitor-${theme}-${view}-viewport.png`)});}
   }
   const periods=language==='vi'?['Phiên','Hôm nay','Tháng này','Toàn bộ lịch sử']:['Session','Today','This month','Lifetime'];
   for(const period of periods)await monitor.getByRole('button',{name:period,exact:true}).click();
  }
 }
 const result={readOnly:true,gpuCompute:false,checks,browserErrors:errors};await writeFile(path.join(output,'monitoring-layout.json'),JSON.stringify(result,null,2),{mode:0o600});
 console.log(JSON.stringify({cases:checks.length,browserErrors:errors,failures:checks.filter(c=>c.overflow||c.metricOverlaps.length||c.energyRows<3||(c.view==='detail'&&c.cores!==28))}));
 if(errors.length||checks.some(c=>c.overflow||c.metricOverlaps.length||c.energyRows<3||(c.view==='detail'&&c.cores!==28)))process.exitCode=1;
}finally{await browser.close();}
