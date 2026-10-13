import {chromium} from 'playwright';import fs from 'node:fs/promises';
const [base,out,...pages]=process.argv.slice(2);await fs.mkdir(out,{recursive:true});
const browser=await chromium.launch();const ctx=await browser.newContext({viewport:{width:1360,height:900},locale:'vi-VN'});const page=await ctx.newPage();
const errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error'&&!/401/.test(m.text()))errors.push(m.text())});
await page.addInitScript(()=>{globalThis.__HETEROES_I18N_AUDIT__=true});
for(const name of pages){
 if(name==='home'){await page.goto(base+'/');await page.waitForTimeout(3500);await page.screenshot({path:out+'/home.png',fullPage:true});continue;}
 if(!(await page.url().includes(base))||!await page.evaluate(()=>!!sessionStorage.getItem('heteroes.access-token'))){await page.goto(base+'/login');await page.locator('input[autocomplete="username"]').fill('admin');await page.locator('input[autocomplete="current-password"]').fill('test-admin-pass');await page.locator('form button[type="submit"]').click();await page.waitForURL(u=>!u.pathname.startsWith('/login'));}
 await page.goto(base+'/'+name);await page.waitForTimeout(3500);await page.screenshot({path:out+`/${name.replace(/\//g,'_')}.png`,fullPage:true});
}
console.log(JSON.stringify({errors,missing:await page.evaluate(()=>globalThis.__heteroesMissingI18n?.()??[])}));await browser.close();
