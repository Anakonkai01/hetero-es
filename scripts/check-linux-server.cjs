/** Packaged CPU-only Server: fresh install, bootstrap, same-origin HTTP and lifecycle. */
const {_electron:electron}=require('playwright');
const fs=require('node:fs/promises');
const path=require('node:path');
const crypto=require('node:crypto');
const assert=require('node:assert/strict');
const net=require('node:net');
const {spawnSync}=require('node:child_process');
function argument(name){const index=process.argv.indexOf(name);return index<0?undefined:process.argv[index+1];}
const executable=argument('--executable'),output=argument('--output');
if(!executable||!output||!process.env.XDG_CONFIG_HOME||!process.env.XDG_DATA_HOME)throw Error('Explicit isolated executable/output/XDG paths required');
async function freePort(){const server=net.createServer();await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});const port=server.address().port;await new Promise(resolve=>server.close(resolve));return port;}
(async()=>{
 await fs.mkdir(output,{recursive:true,mode:0o700});const evidence=path.join(output,'packaged-linux-server.json');
 try{await fs.access(evidence);throw Error('Existing evidence is never overwritten');}catch(e){if(e.code!=='ENOENT')throw e;}
 const env={...process.env,CUDA_VISIBLE_DEVICES:'',PYTHONNOUSERSITE:'1',PYTHONUTF8:'1'};
 let app;const launch=()=>electron.launch({executablePath:path.resolve(executable),args:['--disable-gpu'],env,timeout:30000});
 const invoke=(page,action,args={})=>page.evaluate(async ({action,args})=>{const reply=await window.labServer.call(action,args);if(!reply.ok)throw Error(reply.error);return reply.result;},{action,args});
 try{
  app=await launch();let page=await app.firstWindow();
  const observed=await app.evaluate(({app})=>({packaged:app.isPackaged,version:app.getVersion(),userData:app.getPath('userData')}));
  assert.equal(observed.packaged,true);assert.ok(observed.userData.startsWith(path.resolve(process.env.XDG_CONFIG_HOME)+path.sep));
  const before=await invoke(page,'status');assert.equal(before.setup.installed,false);assert.equal(before.initialized,false);assert.equal(before.running,false);assert.equal(before.autostart,false);
  // A cache is optional; every cached archive/wheel still passes its pinned hash.
  const cache=path.join(observed.userData,'downloads');await fs.mkdir(cache,{recursive:true});
  const resources=path.join(path.dirname(path.resolve(executable)),'resources/server');
  const profile=JSON.parse(await fs.readFile(path.join(resources,'profile.json'),'utf8'));
  const python=profile.platforms.linux.python;
  await fs.copyFile('/mnt/Archive-2tb/heteroes-local/downloads/worker-v1/'+python.name,path.join(cache,python.name));
  await fs.cp('/mnt/Archive-2tb/heteroes-local/downloads/server-v1/linux',path.join(cache,'linux'),{recursive:true});
  assert.equal((await invoke(page,'install')).installed,true);
  const port=await freePort(),password=crypto.randomBytes(24).toString('base64url');
  const storage=path.join('/mnt/Archive-2tb/heteroes-local/evidence', 'server-proof-'+crypto.randomBytes(8).toString('hex'));
  const initialized=await invoke(page,'initialize',{username:'ownerproof',password,host:'127.0.0.1',port,storageDirectory:storage,storageVolumeUUID:'10443D1F443D094C'});
  const credentials=await fs.readFile(path.join(observed.userData,'lab/credentials.json'),'utf8');assert.deepEqual(JSON.parse(credentials),{users:{}});assert.ok(!credentials.includes(password));
  assert.equal((await invoke(page,'status')).running,false);
  const started=await invoke(page,'start');assert.equal(started.running,true);
  const monitorDeadline=Date.now()+15000;let monitor;
  while(Date.now()<monitorDeadline){monitor=await invoke(page,'status');if(monitor.resourceTelemetry?.power&&monitor.resourceTelemetry?.host?.cores?.length&&monitor.telemetryHistory?.length>=2)break;await new Promise(resolve=>setTimeout(resolve,500));}
  assert.ok(monitor.resourceTelemetry.host.cores.length>0);assert.ok(monitor.resourceTelemetry.power.components.some(c=>c.kind==='cpu-package'&&c.powerW!=null));assert.ok(monitor.telemetryHistory.length>=2);
  await page.getByRole('button',{name:'Chi tiết',exact:true}).click();assert.ok(await page.locator('.telemetry-cores>div').count()>0);
  const layout=await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth);assert.equal(layout,true);
  await page.screenshot({path:path.join(output,'installed-server-detail.png'),fullPage:true});
  const url=initialized.apiUrl;
  const health=await (await fetch(url+'/api/v1/health')).json();assert.equal(health.ok,true);assert.equal(health.recoveryStorageMode,'local');
  const index=await fetch(url+'/');assert.equal(index.status,200);assert.match(await index.text(),/id="root"/);
  assert.equal((await fetch(url+'/api/v1/missing')).status,404);
  assert.equal((await fetch(url+'/api/v1/experiments')).status,401);
  const login=await fetch(url+'/api/v1/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:'ownerproof',password})});assert.equal(login.status,200);
  const session=await login.json();assert.equal(session.user.platformAdmin,true);
  const headers={Authorization:'Bearer '+session.accessToken,'X-Workspace-Id':'lab'};
  const operations=await (await fetch(url+'/api/v1/platform/operations',{headers})).json();assert.equal(operations.dispatchHeld,true);assert.equal(operations.queueCount,0);
  const runtimes=await fs.readdir(path.join(observed.userData,'runtimes'));assert.equal(runtimes.length,1);
  const isolatedPython=path.join(observed.userData,'runtimes',runtimes[0],'python/bin/python3.12');
  const cpu=spawnSync(isolatedPython,['-c','import importlib.util,fastapi,uvicorn; assert importlib.util.find_spec("torch") is None; print("CPU-only dependencies verified")'],{env,encoding:'utf8',timeout:10000});assert.equal(cpu.status,0);
  await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].close());
  assert.equal(await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].isVisible()),false);
  assert.equal((await fetch(url+'/api/v1/health')).status,200);
  await invoke(page,'stop');assert.equal((await invoke(page,'status')).running,false);
  await assert.rejects(fetch(url+'/api/v1/health',{signal:AbortSignal.timeout(1000)}));
  await app.close();app=null;app=await launch();page=await app.firstWindow();
  const restarted=await invoke(page,'status');assert.equal(restarted.setup.installed,true);assert.equal(restarted.initialized,true);assert.equal(restarted.running,false);assert.equal(restarted.autostart,false);
  await invoke(page,'start');
  // A desktop crash closes the parent pipe; the child must stop itself.
  await app.close();app=null;
  const deadline=Date.now()+15000;let offline=false;
  while(Date.now()<deadline){try{await fetch(url+'/api/v1/health',{signal:AbortSignal.timeout(500)});}catch{offline=true;break;}await new Promise(resolve=>setTimeout(resolve,100));}
  assert.equal(offline,true);
  const record={actualPackagedApp:true,freshIsolatedRuntime:true,cpuOnlyDependencies:true,sameOriginWebAndApi:true,
    bootstrapPasswordOnlyArgon2:true,queueInitiallyHeld:true,manualStart:true,closeToTray:true,confirmedStop:true,
    restartRetainsLabAndStaysStopped:true,parentPipeStopsOrphanApi:true,
    displayEnvironment:'Xvfb',ordinaryOwnerDesktopWalkthrough:false,windowsHardwareAcceptance:false,
    realHostDetailAndCpuPower:true,persistentEnergyComponents:true,detailRendererNoOverflow:true,
    runtimeSha256:profile.runtimeSha256,version:observed.version};
  await fs.writeFile(evidence,JSON.stringify(record,null,2)+'\n',{flag:'wx',mode:0o600});
  console.log('PASS packaged Linux CPU Server install/bootstrap/same-origin/lifecycle.');
 }finally{if(app)await app.close();}
})().catch(error=>{console.error(error.message);process.exitCode=1;});
