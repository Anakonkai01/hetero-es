import json
from pathlib import Path
items=[]
def m(name,file,old,new):
 assert Path(file).read_text().count(old)==1,(name,Path(file).read_text().count(old));items.append(dict(name=name,file=file,old=old,new=new))
p='frontend/src/app/identity.ts'
m('implicit token flow',p,"response_type: 'code'","response_type: 'token'")
m('PKCE disabled',p,'disablePKCE: false','disablePKCE: true')
m('automatic renewal disabled',p,'automaticSilentRenew: true','automaticSilentRenew: false')
m('user tokens written to session storage',p,'store: new InMemoryWebStorage()','store: storage')
m('PKCE state is lost on redirect',p,'stateStore: new WebStorageStateStore({ store: storage })','stateStore: new WebStorageStateStore({ store: new InMemoryWebStorage() })')
m('callback URL cleanup omitted',p,"browser.history.replaceState(null, '', config.basePath + (complete ? 'workspace' : 'login'));",'void complete;')
m('callback error discloses raw provider error',p,'throw new Error(\'Identity sign-in could not complete\');','throw new Error(\'private-code\');')
m('expired access token remains active',p,"identity.events.addAccessTokenExpired(() => publish(''));",'identity.events.addAccessTokenExpired(() => {});')
p='frontend/src/api/token.ts'
m('OIDC stores access tokens on disk',p,"persistentStorage = mode === 'local' ? storage : undefined;",'persistentStorage = storage;')
m('OIDC reuses a stale local session',p,"accessToken = mode === 'local' ? (storage.getItem(TOKEN_KEY) ?? '') : '';","accessToken = storage.getItem(TOKEN_KEY) ?? '';")
p='scripts/lib/wait-for-counter.mjs'
m('zero counter is treated as acceptance',p,"typeof receipt[name] === 'number' && receipt[name] >= minimum","typeof receipt[name] === 'number'")
Path('.scratch/review-2026-11/B5/frontend-mutants.json').write_text(json.dumps(items,indent=2)+'\n');print(len(items),'mutants')
