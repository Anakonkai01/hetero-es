/** Real Electron render review with isolated user data; no install or GPU computation. */
const {_electron:electron}=require('playwright');
const fs=require('node:fs/promises');const path=require('node:path');const os=require('node:os');
(async()=>{
 const output=path.join(os.homedir(),'.local/share/heteroes-ui-review');await fs.mkdir(output,{recursive:true,mode:0o700});const evidence=[];
 const packaged=process.env.HETEROES_PACKAGED_UI_DIRECTORY;
 for(const name of ['worker','server']){
  const isolated=await fs.mkdtemp(path.join(os.tmpdir(),'heteroes-ui-'+name+'-'));await fs.mkdir(path.join(isolated,'config'));await fs.mkdir(path.join(isolated,'data'));
  let app;try{
   app=await electron.launch({executablePath:packaged?path.join(packaged,name,'linux-unpacked','heteroes-'+name):path.resolve('node_modules/electron/dist/electron'),args:packaged?['--disable-gpu']:['--disable-gpu',path.resolve('desktop/'+name)],env:{...process.env,XDG_CONFIG_HOME:path.join(isolated,'config'),XDG_DATA_HOME:path.join(isolated,'data')},timeout:30000});
   const page=await app.firstWindow();const errors=[];page.on('pageerror',e=>errors.push(e.message));await page.waitForTimeout(900);
   for(const theme of ['light','dark']){
    await page.locator('.preference-menu summary').click();await page.locator('.preferences select').nth(1).selectOption(theme);await page.locator('.preference-menu summary').click();
    await page.screenshot({path:path.join(output,`${packaged?'packaged':'native'}-${name}-${theme}.png`),fullPage:true});
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);evidence.push({name,theme,packaged:!!packaged,realElectron:true,isolated:true,gpuCompute:false,overflow,browserErrors:[...errors]});
   }
   await page.evaluate(async name=>{if(name==='worker')await window.worker.call('quit');else await window.labServer.call('quit');},name).catch(()=>{});
  }finally{if(app)await app.close().catch(()=>{});}
 }
 await fs.writeFile(path.join(output,packaged?'packaged-desktop-review.json':'desktop-review.json'),JSON.stringify(evidence,null,2),{mode:0o600});console.log(JSON.stringify(evidence));if(evidence.some(e=>e.overflow||e.browserErrors.length))process.exitCode=1;
})().catch(e=>{console.error(e.message);process.exitCode=1;});
