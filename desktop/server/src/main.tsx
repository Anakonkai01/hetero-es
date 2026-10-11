import {useEffect,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {ProductProvider,PreferencesControl,StepHeader,Status,Alert,useProduct} from '@heteroes/product-ui';
import '@heteroes/product-ui/theme.css';
import '../../worker/src/style.css';

type State={setup:{installed:boolean;running:boolean;progress:{stage:string;received?:number;total?:number}},initialized:boolean,running:boolean,error?:string,addresses:string[],apiUrl:string|null,storageDirectory:string|null,autostart:boolean};
type Storage={storageDirectory:string,storageVolumeUUID:string|null};
declare global {interface Window {labServer:{call:(action:string,args?:Record<string,unknown>)=>Promise<{ok:boolean,result?:unknown,error?:string}>}}}
function App(){
 const {t}=useProduct();
 const [state,setState]=useState<State>();const [busy,setBusy]=useState('');const [error,setError]=useState('');
 const [host,setHost]=useState('127.0.0.1');const [port,setPort]=useState(8000);
 const [username,setUsername]=useState('admin');const [password,setPassword]=useState('');const [storage,setStorage]=useState<Storage>();
 useEffect(()=>{let active=true,inFlight=false;const refresh=async()=>{if(inFlight)return;inFlight=true;try{const reply=await window.labServer.call('status');if(active&&reply.ok)setState(reply.result as State);}finally{inFlight=false;}};void refresh();const timer=setInterval(()=>void refresh(),1000);return()=>{active=false;clearInterval(timer);};},[]);
 async function command(action:string,args:Record<string,unknown>={}){
  setBusy(action);setError('');
  try {const reply=await window.labServer.call(action,args);if(!reply.ok)throw Error(reply.error);return reply.result;}
  catch(e){setError(e instanceof Error?e.message:'ACTION_FAILED');return undefined;}
  finally{setBusy('');}
 }
 const locked=!!busy||!!state?.setup.running;
 const errors:Record<string,string>={SERVER_START_FAILED:'Server could not start. Check that the address and port are available.',SERVER_START_TIMEOUT:'Server did not become ready. Retry or review the local diagnostics.',LAB_ADDRESS_UNAVAILABLE:'The selected network address is offline. Reconnect LAN or Tailscale.',INSUFFICIENT_DISK_SPACE:'Free some disk space and retry.',RUNTIME_PROCESS_FAILED:'Setup failed. Check your network and selected storage, then retry.',SERVER_SHUTDOWN_PENDING:'Server is still shutting down. Keep this app open and retry.',ACTION_FAILED:'The action failed. Check the selected storage and network.'};
 return <div className="desktop-shell">
  <header className="desktop-header"><div className="brand">HeteroES <span>Lab Server</span></div><PreferencesControl/></header>
  <div className="intro"><div><p className="eyebrow">{t('Your local lab')}</p><h1>{t('Start a lab on this computer')}</h1><p className="hint">{t('Share one lab address with GPU contributors on LAN or Tailscale.')}</p></div><Status value={state?.running?'ONLINE':'OFF'}/></div>
  <StepHeader steps={['Install Server','Create your lab','Start Server']} current={!state?.setup.installed?0:!state.initialized?1:2}/>
  {(error||state?.error)&&<Alert tone="error">{t(errors[error||state?.error||'']??error??state?.error??'')}</Alert>}
  {!state?.setup.installed?<section className="panel"><h2>{t('Install Server')}</h2><p>{t('Install the private Server runtime. This computer does not need a GPU.')}</p><p>{t(state?.setup.progress.stage??'NOT_INSTALLED')}</p>{state?.setup.progress.total&&<progress value={state.setup.progress.received} max={state.setup.progress.total}/>}
    <button disabled={locked} onClick={()=>void command('install')}>{t(locked?'Installing…':'Install Server')}</button></section>:
   !state.initialized?<form className="panel" onSubmit={event=>{event.preventDefault();if(storage){void command('initialize',{username,password,host,port,...storage}).then(()=>setPassword(''));}}}>
    <h2>{t('Create your lab')}</h2>
    <label>{t('Lab address')}<select value={host} onChange={e=>setHost(e.target.value)}>{state.addresses.map(address=><option key={address}>{address}</option>)}</select></label>
    {host==='127.0.0.1'&&<Alert>{t('This address works only on this computer. Select LAN or Tailscale to connect other computers.')}</Alert>}
    <label>{t('Port')}<input type="number" min={1024} max={65535} value={port} onChange={e=>setPort(Number(e.target.value))} required/></label>
    <label>{t('Administrator username')}<input value={username} onChange={e=>setUsername(e.target.value)} pattern="[a-zA-Z0-9_.-]+" minLength={2} maxLength={100} autoComplete="username" required/></label>
    <label>{t('Administrator password')}<input type="password" value={password} onChange={e=>setPassword(e.target.value)} minLength={12} maxLength={200} autoComplete="new-password" required/></label>
    <p>{t('Choose a disk for checkpoints and models.')}</p><p><code>{storage?.storageDirectory??t('No storage selected')}</code></p>
    <button type="button" className="secondary" disabled={locked} onClick={()=>void command('chooseStorage').then(result=>{if(result)setStorage(result as Storage);})}>{t('Choose storage')}</button>
    <button disabled={locked||!storage} type="submit">{t('Create your lab')}</button>
   </form>:<section className="panel"><h2>{t('Start Server')}</h2><p><code>{state.apiUrl}</code></p><p className="hint">{t('New labs start with the queue held. Sign in and enable dispatch in Operations after pairing workers.')}</p>
    <div className="secondary-actions"><button disabled={locked} onClick={()=>void command(state.running?'stop':'start')}>{t(state.running?'Stop Server':'Start Server')}</button>
    <button className="secondary" disabled={locked||!state.running} onClick={()=>void command('openLab')}>{t('Open lab')}</button></div>
    <label style={{display:'flex',alignItems:'center',marginTop:20}}><input style={{width:'auto'}} type="checkbox" disabled={locked} checked={state.autostart} onChange={e=>void command('autostart',{enabled:e.target.checked})}/>{t('Start my lab when I sign in to this computer')}</label>
    <p className="hint">{t('Closing this window keeps the Server in the tray. Quit stops the Server; workers keep outage evidence locally.')}</p>
   </section>}
  <footer className="desktop-footer"><button className="secondary" disabled={locked} onClick={()=>void command('quit')}>{t('Quit')}</button></footer>
 </div>;
}
createRoot(document.getElementById('root')!).render(<ProductProvider><App/></ProductProvider>);
