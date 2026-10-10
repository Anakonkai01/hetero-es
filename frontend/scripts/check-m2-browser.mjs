/** CPU/browser acceptance of the isolated agent deployment; no GPU work here. */
import assert from 'node:assert/strict';
import {readFile,mkdir,writeFile} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {chromium} from 'playwright';
const root=process.env.HETEROES_PRIVATE_CONFIG??path.join(os.homedir(),'.config/heteroes-m2');
const config=JSON.parse(await readFile(path.join(root,'config.json'),'utf8'));
const creds=JSON.parse(await readFile(path.join(root,'credentials.json'),'utf8'));
const url=process.env.HETEROES_UI_URL??'http://100.110.165.40:5175';
const output=path.join(config.productStateDirectory,'m2-browser-evidence');await mkdir(output,{recursive:true});
const browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1440,height:1000}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
try {
  await page.goto(url+'/login');await page.getByLabel('Username').fill('admin');await page.getByLabel('Password',{exact:true}).fill(creds.users.admin);
  await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL('**/workspace');
  await page.goto(url+'/workspace/lab');await page.getByRole('heading',{name:'Activity',exact:true}).waitFor();
  await page.goto(url+'/workers');await page.getByRole('heading',{name:'My devices',exact:true}).waitFor();
  await page.locator('[data-device="3060-thao"]').waitFor();
  assert.equal(await page.locator('[data-device]').count(),3);
  await page.screenshot({path:path.join(output,'devices.png'),fullPage:true});
  await page.goto(url+'/operations');await page.getByRole('heading',{name:'Device approval',exact:true}).waitFor();
  await page.screenshot({path:path.join(output,'operations.png'),fullPage:true});
  await page.goto(url+'/experiments/new');await page.getByLabel('Coordinator',{exact:true}).waitFor();
  assert.equal(await page.getByLabel('Coordinator',{exact:true}).locator('option').count(),4);
  assert.equal(await page.getByLabel('Backup every K generations').inputValue(),'1');
  assert.equal(await page.getByLabel('Keep N recovery points').inputValue(),'3');
  await page.screenshot({path:path.join(output,'configuration.png'),fullPage:true});
  assert.deepEqual(errors,[]);
  await writeFile(path.join(output,'validation.json'),JSON.stringify({deviceCount:3,coordinatorSelection:true,backupDefaults:{interval:1,retain:3},browserErrors:errors},null,2));
  console.log('PASS M2 staging browser: three devices, approval, coordinator selection, backup policy, no JS errors');
} finally {await browser.close();}
