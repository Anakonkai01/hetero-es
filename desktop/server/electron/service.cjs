const fs=require('node:fs');
const fsp=fs.promises;
const path=require('node:path');
const os=require('node:os');
const {spawn}=require('node:child_process');
const {Setup,run}=require('./setup.cjs');
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));

function addresses() {
  const result=new Set(['127.0.0.1']);
  for(const entries of Object.values(os.networkInterfaces()))for(const entry of entries??[]) {
    if(entry.family!=='IPv4')continue;
    const parts=entry.address.split('.').map(Number);
    if(parts[0]===10||(parts[0]===172&&parts[1]>=16&&parts[1]<=31)||
      (parts[0]===192&&parts[1]===168)||(parts[0]===100&&parts[1]>=64&&parts[1]<=127))result.add(entry.address);
  }
  return [...result];
}
class Service {
  constructor(root,resources,options={}) {
    this.root=root;this.resources=resources;this.options=options;
    this.setup=options.setup??new Setup(root,resources);
    this.deployment=path.join(root,'lab');this.child=null;this.stopping=false;this.error=null;
  }
  config() {
    const file=path.join(this.deployment,'config.json');
    return fs.existsSync(file)?JSON.parse(fs.readFileSync(file,'utf8')):null;
  }
  async status() {
    const config=this.config();
    return {setup:this.setup.status(),initialized:!!config,running:!!this.child&&!this.stopping,
      error:this.error,addresses:addresses(),apiUrl:config?.apiUrl??null,
      storageDirectory:config?.storageDirectory??null};
  }
  environment() {
    return {...process.env,CUDA_VISIBLE_DEVICES:'',PYTHONNOUSERSITE:'1',PYTHONUTF8:'1',
      PYTHONPATH:this.setup.paths().source};
  }
  async initialize(args) {
    if(!this.setup.status().installed)throw Error('RUNTIME_NOT_INSTALLED');
    if(this.config())throw Error('LAB_ALREADY_INITIALIZED');
    if(!addresses().includes(args.host))throw Error('INVALID_LAB_ADDRESS');
    await fsp.mkdir(this.root,{recursive:true,mode:0o700});
    const p=this.setup.paths();
    const output=await run(p.python,['-m','backend.server','--initialize','--private',this.deployment],
      {cwd:p.root,env:this.environment(),input:args});
    const result=JSON.parse(output);
    if(result.error)throw Error(result.error);
    return result;
  }
  async start() {
    if(this.child)throw Error('SERVER_ALREADY_RUNNING');
    if(!this.setup.status().installed)throw Error('RUNTIME_NOT_INSTALLED');
    const config=this.config();if(!config)throw Error('LAB_NOT_INITIALIZED');
    if(!addresses().includes(config.serverHost))throw Error('LAB_ADDRESS_UNAVAILABLE');
    const p=this.setup.paths();this.error=null;
    const log=path.join(this.root,'server.log');const fd=fs.openSync(log,'a',0o600);
    let child;
    const downloads=path.join(this.resources,'downloads');
    const args=['-m','backend.server','--private',this.deployment,'--web',p.web];
    if(fs.existsSync(downloads))args.push('--downloads',downloads);
    try {child=(this.options.spawn??spawn)(p.python,args,
      {cwd:p.root,env:this.environment(),windowsHide:true,stdio:['pipe',fd,fd]});}
    finally {fs.closeSync(fd);}
    this.child=child;
    child.stdin.on('error',()=>{});
    child.on('error',()=>{if(this.child===child){this.child=null;this.error='SERVER_START_FAILED';}});
    child.on('exit',()=>{if(this.child===child){this.child=null;if(!this.stopping)this.error='SERVER_STOPPED';}});
    const deadline=Date.now()+30000;
    try {
      while(Date.now()<deadline) {
        if(this.child!==child)throw Error('SERVER_START_FAILED');
        try {
          const response=await (this.options.fetch??fetch)(config.apiUrl+'/api/v1/health',
            {signal:AbortSignal.timeout(1500)});
          const health=await response.json();
          if(response.ok&&health.serverInstanceId===config.serverInstanceId&&health.agentMode) {
            await wait(100);
            if(this.child!==child)throw Error('SERVER_START_FAILED');
            return this.status();
          }
        }catch(error){if(error.message==='SERVER_START_FAILED')throw error;}
        await wait(100);
      }
      throw Error('SERVER_START_TIMEOUT');
    }catch(error){await this.stop();this.error=error.message;throw error;}
  }
  async stop() {
    const child=this.child;if(!child)return this.status();
    this.stopping=true;
    try {
      // Closing the lifetime pipe works on Windows and Linux and signals only
      // the CPU process launched by this app, including during API startup.
      child.stdin.end();
      const deadline=Date.now()+15000;
      while(this.child===child&&Date.now()<deadline)await wait(100);
      if(this.child===child)throw Error('SERVER_SHUTDOWN_PENDING');
      this.error=null;return this.status();
    }finally{this.stopping=false;}
  }
}
module.exports={Service,addresses};
