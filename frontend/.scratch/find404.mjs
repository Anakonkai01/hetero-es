import {chromium} from 'playwright';
const [base]=process.argv.slice(2);const b=await chromium.launch();const p=await (await b.newContext()).newPage();
p.on('response',r=>{if(r.status()>=400&&r.status()!==401)console.log(r.status(),r.url())});
await p.goto(base+'/login');await p.locator('input[autocomplete="username"]').fill('admin');await p.locator('input[autocomplete="current-password"]').fill('test-admin-pass');await p.locator('form button[type="submit"]').click();await p.waitForURL(u=>!u.pathname.startsWith('/login'));
for(const r of ['/dashboard','/workers','/operations','/experiments']){await p.goto(base+r);await p.waitForTimeout(2500);}await b.close();
