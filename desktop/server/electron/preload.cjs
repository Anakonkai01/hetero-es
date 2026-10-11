const {contextBridge,ipcRenderer}=require('electron');
contextBridge.exposeInMainWorld('labServer',{call:(action,args={})=>ipcRenderer.invoke('server:command',action,args)});
