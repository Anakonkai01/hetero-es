import {chromium} from 'playwright';import fs from 'node:fs/promises';
const [base,out]=process.argv.slice(2);await fs.mkdir(out,{recursive:true});
const browser=await chromium.launch();const page=await (await browser.newContext({viewport:{width:1280,height:900},locale:'vi-VN'})).newPage();
const errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error'&&!/401/.test(m.text()))errors.push(m.text())});
await page.addInitScript(()=>{globalThis.__HETEROES_I18N_AUDIT__=true});
await page.goto(base+'/login');await page.locator('input[autocomplete="username"]').fill('admin');await page.locator('input[autocomplete="current-password"]').fill('test-admin-pass');await page.locator('form button[type="submit"]').click();await page.waitForURL(u=>!u.pathname.startsWith('/login'));
await page.goto(base+'/experiments');await page.waitForTimeout(1500);
const link=page.locator('a:has-text("M2 three GPU agent acceptance v2")').first();await link.click();await page.waitForTimeout(1200);
await page.getByRole('tab',{name:/Trực tiếp|Live/}).click();await page.waitForTimeout(2500);
await page.screenshot({path:out+'/live-0.png',fullPage:true});
const scrub=page.locator('.lv-scrub');
for(const [name,v] of [['25',250],['60',600],['95',950]]){await page.getByRole('button',{name:/Tạm dừng|Pause/}).click().catch(()=>{});await scrub.evaluate((el,val)=>{const set=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;set.call(el,String(val));el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));},v);await page.waitForTimeout(400);await page.screenshot({path:out+`/live-${name}.png`,fullPage:true});}
console.log(JSON.stringify({errors,missing:await page.evaluate(()=>globalThis.__heteroesMissingI18n?.()??[])}));
await browser.close();
