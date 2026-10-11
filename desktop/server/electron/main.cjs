const {app,BrowserWindow,ipcMain,Tray,Menu,shell,dialog,nativeImage}=require('electron');
const path=require('node:path');
const {execFile}=require('node:child_process');
const {promisify}=require('node:util');
const {Service}=require('./service.cjs');
const autostart=require('./autostart.cjs');
if(!app.isPackaged&&process.env.HETEROES_SERVER_TEST_DATA)app.setPath('userData',process.env.HETEROES_SERVER_TEST_DATA);
const owns=app.requestSingleInstanceLock();if(!owns)app.quit();
let window,tray,service,exiting=false,busy=false;
const show=()=>{window?.show();window?.focus();};
async function quit(){if(busy)throw Error('ACTION_IN_PROGRESS');await service.stop();service.closeMonitor();exiting=true;app.quit();return {stopped:true};}
app.on('second-instance',show);
app.on('window-all-closed',()=>{});
app.on('before-quit',event=>{if(!exiting){event.preventDefault();quit().catch(show);}});
app.whenReady().then(async()=>{
  if(!owns)return;
  const resources=app.isPackaged?path.join(process.resourcesPath,'server'):path.join(__dirname,'../resources');
  service=new Service(app.getPath('userData'),resources);
  window=new BrowserWindow({width:1050,height:850,minWidth:360,minHeight:540,show:false,
    webPreferences:{preload:path.join(__dirname,'preload.cjs'),sandbox:true,contextIsolation:true,nodeIntegration:false}});
  window.webContents.setWindowOpenHandler(()=>({action:'deny'}));
  window.webContents.on('will-navigate',event=>event.preventDefault());
  window.webContents.session.setPermissionRequestHandler((_a,_b,callback)=>callback(false));
  window.on('close',event=>{if(!exiting){event.preventDefault();window.hide();}});
  tray=new Tray(nativeImage.createFromPath(path.join(resources,'tray.png')));
  tray.setToolTip('HeteroES Lab Server');tray.on('click',show);
  tray.setContextMenu(Menu.buildFromTemplate([{label:'Open Server / Mở Server',click:show},
    {label:'Quit / Thoát',click:()=>quit().catch(show)}]));
  ipcMain.handle('server:command',async(event,action,args)=>{
    if(event.sender!==window.webContents||event.senderFrame!==window.webContents.mainFrame)return {ok:false,error:'IPC_DENIED'};
    const allowed={status:[],install:[],chooseStorage:[],initialize:['username','password','host','port','storageDirectory','storageVolumeUUID'],
      start:[],stop:[],openLab:[],autostart:['enabled'],quit:[]};
    if(!Object.hasOwn(allowed,action)||!args||typeof args!=='object'||Array.isArray(args)||
      Object.keys(args).some(key=>!allowed[action].includes(key)))return {ok:false,error:'INVALID_COMMAND'};
    if(action!=='status'&&busy)return {ok:false,error:'ACTION_IN_PROGRESS'};
    if(action!=='status')busy=true;
    try {
      let result;
      if(action==='status')result={...await service.status(),autostart:autostart.enabled(app)};
      if(action==='install')result=await service.setup.install();
      if(action==='initialize')result=await service.initialize(args);
      if(action==='start')result=await service.start();
      if(action==='stop')result=await service.stop();
      if(action==='chooseStorage'){
        const selected=await dialog.showOpenDialog(window,{properties:['openDirectory','createDirectory']});
        result=null;
        if(!selected.canceled){
          const directory=selected.filePaths[0];let uuid=null;
          if(process.platform==='linux'){
            const response=await promisify(execFile)('findmnt',['-rn','-T',directory,'-o','UUID'],{timeout:5000});
            uuid=response.stdout.trim()||null;
          }
          result={storageDirectory:path.join(directory,'heteroes-artifacts'),storageVolumeUUID:uuid};
        }
      }
      if(action==='openLab'){
        if(!service.child)throw Error('SERVER_NOT_RUNNING');
        await shell.openExternal(service.config().apiUrl);result={opened:true};
      }
      if(action==='autostart'){
        if(typeof args.enabled!=='boolean')throw Error('INVALID_ARGUMENT');
        autostart.set(app,args.enabled);result={enabled:args.enabled};
      }
      if(action==='quit'){busy=false;result=await quit();}
      return {ok:true,result};
    }catch(error){return {ok:false,error:/^[A-Z][A-Z0-9_]+$/.test(error.message)?error.message:'ACTION_FAILED'};}
    finally{if(action!=='status')busy=false;}
  });
  await window.loadFile(path.join(__dirname,'../dist/index.html'));show();
  if(autostart.enabled(app)&&service.config())service.start().catch(show);
}).catch(()=>{exiting=true;app.quit();});
