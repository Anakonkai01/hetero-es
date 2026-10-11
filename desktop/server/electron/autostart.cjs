const fs=require('node:fs');
const path=require('node:path');
const os=require('node:os');
const marker='X-HeteroES-Managed=true';
function file(){return path.join(process.env.XDG_CONFIG_HOME??path.join(os.homedir(),'.config'),'autostart','heteroes-server.desktop');}
function enabled(app){return process.platform==='linux'?(fs.existsSync(file())&&fs.readFileSync(file(),'utf8').includes(marker)):app.getLoginItemSettings().openAtLogin;}
function set(app,value){
  if(process.platform!=='linux'){app.setLoginItemSettings({openAtLogin:value});return;}
  const target=file();
  if(fs.existsSync(target)&&(!fs.readFileSync(target,'utf8').includes(marker)||fs.lstatSync(target).isSymbolicLink()))throw Error('AUTOSTART_FILE_NOT_OWNED');
  if(!value){fs.rmSync(target,{force:true});return;}
  const executable=app.getPath('exe');
  if(/[\r\n]/.test(executable))throw Error('INVALID_EXECUTABLE_PATH');
  const quoted='"'+executable.replaceAll('%','%%').replace(/([\\"`$])/g,'\\$1')+'"';
  fs.mkdirSync(path.dirname(target),{recursive:true,mode:0o700});
  fs.writeFileSync(target,`[Desktop Entry]\nType=Application\nName=HeteroES Lab Server\nExec=${quoted}\nTerminal=false\n${marker}\n`,{mode:0o600});
}
module.exports={enabled,set};
