#!/usr/bin/env python3
"""Manage one CPU production Web/API and two owned tokenless Quick Tunnels."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from urllib.parse import urlsplit

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from backend.deployment import caddyfile, idle, save_private
from backend.addresses import endpoint


def birth(pid):
    try:
        fields=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
        return None if fields[0]=='Z' else fields[19]
    except (FileNotFoundError,ProcessLookupError):
        return None


def alive(record):
    return bool(record.get('birth') and birth(record['pid'])==record['birth'])


def listening(host,port):
    with socket.socket() as sock:
        sock.settimeout(.5)
        return sock.connect_ex((host,port))==0


def load(path):
    return json.loads(path.read_text()) if path.exists() else {}


def spawn(root,name,command,environment,host=None,port=None):
    path=root/(name+'-process.json')
    record=load(path)
    if alive(record):
        if host and not listening(host,port):
            raise RuntimeError(f'Tracked {name} is alive but its port is unavailable')
        return record
    if host and listening(host,port):
        raise RuntimeError(f'{name} port is owned by an untracked process; nothing was stopped')
    log=root/(name+'.log')
    # Truncate only a stopped owned process's private log, removing stale URLs.
    with log.open('wb') as out:
        log.chmod(0o600)
        process=subprocess.Popen(command,cwd=REPO,env=environment,stdin=subprocess.DEVNULL,
            stdout=out,stderr=out,start_new_session=True)
    record={'pid':process.pid,'birth':birth(process.pid),'sourceDirectory':str(REPO)}
    save_private(path,record)
    if host:
        deadline=time.monotonic()+30
        while not listening(host,port):
            if not alive(record) or time.monotonic()>deadline:
                raise RuntimeError(f'{name} failed to start; inspect its private log')
            time.sleep(.2)
    return record


def stop(root,name):
    path=root/(name+'-process.json');record=load(path)
    if alive(record):
        os.kill(record['pid'],signal.SIGTERM)
        deadline=time.monotonic()+30
        while alive(record) and time.monotonic()<deadline:
            time.sleep(.1)
        if alive(record):
            raise RuntimeError(f'{name} did not stop gracefully; ownership retained')
    path.unlink(missing_ok=True)


def quick(root,name,port,cloudflared,environment):
    record=spawn(root,name,[cloudflared,'--config',str(root/'quick-config.yml'),
        'tunnel','--url',f'http://127.0.0.1:{port}','--no-autoupdate'],environment)
    deadline=time.monotonic()+45
    while time.monotonic()<deadline:
        log=(root/(name+'.log')).read_text(errors='replace')
        urls=re.findall(r'https://[a-z0-9-]+\.trycloudflare\.com',log)
        if urls and alive(record):
            return urls[-1]
        if not alive(record):
            break
        time.sleep(.2)
    raise RuntimeError(f'{name} did not obtain a Quick URL; inspect its private log')


def defaults(config,args):
    result=dict(config)
    if args.api_url:
        previous=result.get('apiUrl')
        result['apiUrl']=endpoint(args.api_url,private=True)
        address=urlsplit(result['apiUrl'])
        result['serverHost']=address.hostname;result['serverPort']=address.port or 80
        if result.get('bulkApiUrl') in (None,previous):result['bulkApiUrl']=result['apiUrl']
    if not result.get('apiUrl'):
        if not result.get('uiHost'):
            raise ValueError('Set a private apiUrl in config.json')
        result['apiUrl']=f"http://{result['uiHost']}:{result.get('backendPort',8002)}"
    endpoint(result['apiUrl'],private=True)
    result.setdefault('bulkApiUrl',result['apiUrl'])
    if args.compute_url:result['privateComputeUrl']=endpoint(args.compute_url,private=True)
    if not result.get('privateComputeUrl'):raise ValueError('Set a private compute URL explicitly')
    endpoint(result['privateComputeUrl'],private=True)
    if not result.get('serverInstanceId'):
        import secrets
        result['serverInstanceId']=secrets.token_hex(16)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['start','stop','status','rotate','restart'])
    parser.add_argument('--private',type=Path,default=Path.home()/'.config/heteroes-m2')
    parser.add_argument('--python',default=sys.executable)
    parser.add_argument('--caddy',default=str(Path.home()/'.local/share/heteroes-tools/caddy'))
    parser.add_argument('--cloudflared',default='cloudflared')
    parser.add_argument('--compute-url')
    parser.add_argument('--api-url',help='Private LAN/Tailscale Web/API bind and bulk origin')
    parser.add_argument('--web',type=Path,default=REPO/'frontend/dist')
    parser.add_argument('--downloads',type=Path,default=REPO/'frontend/public/downloads')
    args=parser.parse_args()
    root=args.private/'local-deployment'
    root.mkdir(mode=0o700,parents=True,exist_ok=True)
    lock=os.open(root/'lock',os.O_CREAT|os.O_RDWR,0o600)
    with os.fdopen(lock,'w') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        config=load(args.private/'config.json')
        names=['web-quick','compute-quick','public-entry','cpu-server']
        if args.action=='status':
            print(json.dumps({'services':{n:{'alive':alive(load(root/(n+'-process.json')))} for n in names},
                'webUrl':config.get('publicWebUrl'),'computeUrl':config.get('publicComputeUrl'),
                'privateBulkUrl':config.get('privateComputeUrl'),'serverInstanceId':config.get('serverInstanceId')},indent=2))
            return
        config=defaults(config,args)
        if config.get('deploymentMode')!='agent':
            raise RuntimeError('Local deployment requires agent mode')
        idle(config)
        if args.action in ('stop','rotate','restart'):
            selected=names[:2] if args.action=='rotate' else names[2:] if args.action=='restart' else names
            for name in selected:
                stop(root,name)
            if args.action!='restart':
                config.pop('publicWebUrl',None);config.pop('publicComputeUrl',None)
            save_private(args.private/'config.json',config)
            if args.action=='stop':
                print('Owned CPU service and Quick Tunnels stopped.');return
        if not (args.web/'index.html').is_file():
            raise RuntimeError('Build the production frontend first')
        # Preserve the old private config as a migration receipt, exactly once.
        backup=root/'config-before-production.json'
        if not backup.exists():
            save_private(backup,load(args.private/'config.json'))
        save_private(args.private/'config.json',config)
        entry=root/'Caddyfile'
        entry.write_text(caddyfile(config));entry.chmod(0o600)
        subprocess.run([args.caddy,'validate','--config',str(entry)],check=True,capture_output=True)
        environment={**os.environ,'CUDA_VISIBLE_DEVICES':'','PYTHONNOUSERSITE':'1'}
        address=urlsplit(config['apiUrl'])
        command=[args.python,'-m','backend.server','--private',str(args.private),'--web',str(args.web),'--headless']
        if args.downloads.is_dir():command.extend(['--downloads',str(args.downloads)])
        spawn(root,'cpu-server',command,environment,address.hostname,address.port or 80)
        spawn(root,'public-entry',[args.caddy,'run','--config',str(entry)],environment,'127.0.0.1',config.get('webEntryPort',8080))
        (root/'quick-config.yml').write_text('{}\n');(root/'quick-config.yml').chmod(0o600)
        config['publicWebUrl']=quick(root,'web-quick',config.get('webEntryPort',8080),args.cloudflared,environment)
        config['publicComputeUrl']=quick(root,'compute-quick',config.get('computeEntryPort',8081),args.cloudflared,environment)
        save_private(args.private/'config.json',config)
        print(json.dumps({'webUrl':config['publicWebUrl'],'computeUrl':config['publicComputeUrl'],
            'privateBulkUrl':config['privateComputeUrl'],'dispatchHeld':True,'computeStarted':False},indent=2))


if __name__=='__main__':
    try:
        main()
    except Exception as error:
        # Do not expose credential/config contents in validation exceptions.
        print(f'Local deployment failed ({type(error).__name__}). Check private logs/configuration.',file=sys.stderr)
        raise SystemExit(1)
