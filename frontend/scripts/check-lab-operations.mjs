/** Real product acceptance. --run-gpu explicitly adds one short 3060 cancellation. */
import assert from 'node:assert/strict';
import { readFile,mkdir,writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { randomBytes } from 'node:crypto';
import { chromium } from 'playwright';

const privateRoot=process.env.HETEROES_PRIVATE_CONFIG??path.join(os.homedir(),'.config/heteroes-integration');
const config=JSON.parse(await readFile(path.join(privateRoot,'config.json'),'utf8'));
const credentials=JSON.parse(await readFile(path.join(privateRoot,'credentials.json'),'utf8'));
const base=`http://${config.uiHost}:${config.uiPort??5173}`;const username=`m1check-${Date.now()}`;const password=randomBytes(24).toString('base64url');
const output=path.join(config.productStateDirectory,'m1-browser-evidence',username);await mkdir(output,{recursive:true,mode:0o700});
const browser=await chromium.launch({headless:true});
const adminContext=await browser.newContext({viewport:{width:1440,height:1000}});const memberContext=await browser.newContext({viewport:{width:1440,height:1000}});
const admin=await adminContext.newPage();const member=await memberContext.newPage();const errors=[];
admin.on('pageerror',e=>errors.push(e.message));member.on('pageerror',e=>errors.push(e.message));
let workspaceId,runId,userId,moved=false;
async function api(page,method,route,body,workspace='lab') {
 const token=await page.evaluate(()=>sessionStorage.getItem('heteroes.access-token'));
 const result=await page.request.fetch(base+'/api/v1'+route,{method,data:body,headers:{Authorization:`Bearer ${token}`,'X-Workspace-Id':workspace}});
 return result;
}
async function until(fn,seconds=180) {
 const deadline=Date.now()+seconds*1000;
 while(Date.now()<deadline) { const value=await fn();if(value)return value;await new Promise(r=>setTimeout(r,1000)); }
 throw new Error('Timed out waiting for lab acceptance');
}
async function login(page,name,pass) {
 await page.goto(base+'/login');await page.getByLabel('Username').fill(name);await page.getByLabel('Password',{exact:true}).fill(pass);
 await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.waitForURL('**/workspace');
}
try {
 await member.goto(base+'/register');await member.getByLabel('Username').fill(username);await member.getByLabel('Display name').fill('M1 acceptance member');await member.getByLabel('Password',{exact:true}).fill(password);
 await member.getByRole('button',{name:'Register',exact:true}).click();await member.waitForURL('**/workspace');
 await member.getByText(/Account status: PENDING/).waitFor();assert.equal(await member.getByRole('button',{name:'Create workspace',exact:true}).isDisabled(),true);
 await member.screenshot({path:path.join(output,'pending-account.png'),fullPage:true});
 await login(admin,'admin',credentials.users.admin);await admin.goto(base+'/operations');
 const account=admin.locator(`[data-account="${username}"]`);await account.getByRole('button',{name:'Approve',exact:true}).click();
 await until(async()=>/ACTIVE/.test(await account.innerText()));
 await account.getByRole('button',{name:'Allow workspace creation',exact:true}).click();await until(async()=>/Workspace creation allowed/.test(await account.innerText()));
 await member.getByRole('button',{name:'Refresh',exact:true}).click();await until(async()=>!(await member.getByRole('button',{name:'Create workspace',exact:true}).isDisabled()));
 await member.getByRole('button',{name:'Create workspace',exact:true}).click();await member.getByLabel('Name',{exact:true}).fill('M1 acceptance workspace');await member.getByLabel('Description').fill('Automated product acceptance; no research claim.');
 await member.getByRole('button',{name:'Create workspace',exact:true}).last().click();
 await member.getByRole('link',{name:/M1 acceptance workspace/}).click();await member.getByRole('heading',{name:'M1 acceptance workspace',exact:true}).waitFor();workspaceId=member.url().split('/').at(-1);
 let response=await api(admin,'GET','/experiments',undefined,workspaceId);assert.equal(response.status(),403,'Platform administration must not grant workspace access');
 await member.getByLabel('Invite by username').fill('admin');await member.getByRole('button',{name:'Invite member',exact:true}).click();await member.getByText('Membership operation saved.',{exact:true}).waitFor();
 await admin.goto(base+'/profile');await admin.getByRole('button',{name:'Accept invitation',exact:true}).click();
 await until(async()=>{const s=await (await api(admin,'GET','/auth/session')).json();return s.workspaces.some(w=>w.workspaceId===workspaceId);});
 await admin.locator('#active-workspace').selectOption(workspaceId);await admin.goto(base+'/workers');
 const gpu=admin.locator('[data-contribution="3060"]');await gpu.getByLabel('Contributing workspace').selectOption(workspaceId);await gpu.getByRole('button',{name:'Enable / assign',exact:true}).click();
 await until(async()=>{const c=await (await api(admin,'GET','/contributions')).json();return c.find(w=>w.worker_id==='3060')?.workspace_id===workspaceId;});moved=true;
 await member.goto(base+'/experiments/new');await member.getByLabel('Experiment name').fill('M1 approved member cancellation');await member.getByLabel('Maximum generations').fill('10');await member.getByRole('checkbox',{name:/3060/}).check();
 await member.getByRole('button',{name:'Save draft',exact:true}).click();await member.waitForURL(/\/experiments\/[a-f0-9]{32}$/);runId=member.url().split('/').at(-1);
 response=await api(admin,'GET',`/experiments/${runId}`,undefined,workspaceId);assert.equal(response.status(),404,'Platform admin joined as participant cannot read another owner\'s run');
 if(process.argv.includes('--run-gpu')) {
  await member.getByRole('button',{name:'Start experiment',exact:true}).click();
  await until(async()=>{const r=await (await api(member,'GET',`/experiments/${runId}`,undefined,workspaceId)).json();assert.notEqual(r.status,'FAILED');return r.completedGenerations>=1;},600);
  await member.getByRole('button',{name:'Cancel experiment',exact:true}).click();
  const run=await until(async()=>{const r=await (await api(member,'GET',`/experiments/${runId}`,undefined,workspaceId)).json();return r.status==='CANCELLED'&&r;},300);
  assert.ok(run.completedGenerations>=1&&run.completedGenerations<10);
  const artifacts=await (await api(member,'GET','/artifacts',undefined,workspaceId)).json();assert.ok(artifacts.some(a=>a.experimentId===runId&&a.type==='CHECKPOINT'));
  await member.getByText('CANCELLED',{exact:true}).first().waitFor();
 } else {
  response=await api(member,'POST',`/experiments/${runId}/cancel`,{},workspaceId);assert.equal(response.status(),200);
 }
 await member.screenshot({path:path.join(output,'member-runtime.png'),fullPage:true});
 await admin.goto(base+'/operations');await admin.getByRole('heading',{name:'Lab operations',exact:true}).waitFor();await admin.screenshot({path:path.join(output,'operations.png'),fullPage:true});
 const session=await (await api(member,'GET','/auth/session')).json();userId=session.user.userId;
 response=await api(admin,'PATCH',`/platform/users/${userId}`,{accountStatus:'SUSPENDED'});assert.equal(response.status(),200);
 assert.equal((await api(member,'GET','/auth/session')).status(),401);
 assert.deepEqual(errors,[]);
 await writeFile(path.join(output,'acceptance.json'),JSON.stringify({username,userId,workspaceId,runId,gpuRun:process.argv.includes('--run-gpu'),browserErrors:errors,registrationApproval:true,workspaceCreation:true,invitationAcceptance:true,ownerIsolation:true,sessionRevocation:true},null,2),{mode:0o600});
 console.log(`PASS real registration, approval, workspace permission, invitations, GPU assignment, owner isolation, cancellation and suspension. Evidence: ${output}`);
} finally {
 if(moved) {
  const run=runId&&await (await api(admin,'GET','/platform/operations')).json();
  if(!run?.reservations?.length) {
   const response=await api(admin,'POST','/contributions/3060',{enabled:true,workspaceId:'lab'});
   assert.equal(response.status(),200,'Restore the idle 3060 assignment to the original lab');
  }
 }
 await browser.close();
}
