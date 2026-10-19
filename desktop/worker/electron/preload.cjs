const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('worker', {
  call: (action, args = {}) => ipcRenderer.invoke('worker:command', action, args),
});
