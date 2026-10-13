#!/usr/bin/env python3
"""Manage one CPU production Web/API and its public tunnel (two Quick Tunnels, or one named tunnel).

    start | stop | restart | rotate | status    operator actions; a restart holds the queue while the services are down
                                                and reopens it afterwards if the lab was idle and open
    boot                                        start whatever is not running (for a boot service); a lab that had a run
                                                or a GPU reservation when it went down stays held for an administrator
"""
import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request
from urllib.parse import urlsplit

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from backend.deployment import caddyfile, idle, save_private
from backend.addresses import endpoint, is_private

REGISTRATION_SECONDS=45


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


def tunnel_names(config):
    return ['named-tunnel'] if config.get('namedTunnelConfig') else ['web-quick','compute-quick']


def named(root,name,config_file,cloudflared,environment):
    """Run an owner-created Cloudflare tunnel (fixed host names) and wait until it has registered."""
    record=spawn(root,name,[cloudflared,'--no-autoupdate','tunnel','--config',str(config_file),'run'],environment)
    deadline=time.monotonic()+REGISTRATION_SECONDS
    while time.monotonic()<deadline:
        log=(root/(name+'.log')).read_text(errors='replace')
        if alive(record) and 'Registered tunnel connection' in log:
            return record
        if not alive(record):
            break
        time.sleep(.2)
    raise RuntimeError(f'{name} did not register with Cloudflare; inspect its private log')


def check_named(config):
    if not config.get('namedTunnelConfig'):
        return
    if not Path(config['namedTunnelConfig']).is_file():
        raise ValueError('namedTunnelConfig does not point to a file')
    urls=[config.get('publicWebUrl'),config.get('publicComputeUrl')]
    for value in urls:
        if not isinstance(value,str) or not value.startswith('https://') or is_private(value):
            raise ValueError('A named tunnel needs fixed HTTPS publicWebUrl and publicComputeUrl')
        endpoint(value)
    if urls[0]==urls[1]:
        raise ValueError('Web and compute need different host names')


def mounted_uuid(directory):
    """UUID of the filesystem that holds `directory` ('' when the path does not exist, e.g. the disk is not mounted)."""
    found=subprocess.run(['findmnt','-n','-o','UUID','-T',str(directory)],capture_output=True,text=True)
    return found.stdout.strip() if found.returncode==0 else ''


def check_storage(config,probe=None):
    """The storage disk must be mounted before anything is stopped or started: otherwise the Web/API dies a moment
    later with a traceback only the private log shows (what happened after the reboot of 2026-10-13)."""
    uuid,directory=config.get('storageVolumeUUID'),config.get('storageDirectory')
    if not uuid or not directory:
        return
    if (probe or mounted_uuid)(directory)!=uuid:
        raise RuntimeError(f'The storage disk (UUID {uuid}) is not mounted at {directory}; mount it and the lab will retry')


EXECUTING={'STARTING','RUNNING','CANCELLING','RECOVERING','DRAINING','PAUSING'}


def lab_state(db_path):
    """{'held': dispatch hold, 'busy': a run is executing or a GPU is reserved}. Reads the product database only."""
    with sqlite3.connect(Path(db_path).as_uri()+'?mode=ro',uri=True,timeout=20) as db:
        held=json.loads(db.execute("SELECT value FROM settings WHERE key='dispatchHold'").fetchone()[0]) is True
        reserved=sum(db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in ('device_reservations','physical_reservations'))
        running=any(json.loads(row[0]).get('status') in EXECUTING for row in db.execute('SELECT body FROM experiments'))
    return {'held':held,'busy':bool(reserved) or running}


def set_hold(db_path,value):
    with sqlite3.connect(db_path,timeout=20) as db:
        db.execute("INSERT OR REPLACE INTO settings VALUES ('dispatchHold',?)",(json.dumps(bool(value)),))


@contextmanager
def held_while_idle(db_path,allow_busy=False):
    """Hold the queue for the length of the block so nothing can launch while services are down.
    An open, idle queue is reopened afterwards; a queue that was held stays held; a busy lab refuses
    (a boot may proceed, and then stays held until an administrator confirms in Operations)."""
    plan=lab_state(db_path)
    if plan['busy'] and not allow_busy:
        raise RuntimeError('A run or a GPU reservation is active; wait until the lab is idle')
    reopen=not plan['held'] and not plan['busy']
    if not plan['held']:
        set_hold(db_path,True)
    try:
        yield {**plan,'reopen':reopen}
    finally:
        if reopen:
            set_hold(db_path,False)


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
    parser.add_argument('action',choices=['start','stop','status','rotate','restart','boot'])
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
        tunnels=tunnel_names(config);servers=['public-entry','cpu-server'];names=tunnels+servers
        if args.action=='status':
            print(json.dumps({'services':{n:{'alive':alive(load(root/(n+'-process.json')))} for n in names},
                'webUrl':config.get('publicWebUrl'),'computeUrl':config.get('publicComputeUrl'),
                'privateBulkUrl':config.get('privateComputeUrl'),'serverInstanceId':config.get('serverInstanceId')},indent=2))
            return
        config=defaults(config,args)
        check_named(config)
        if config.get('deploymentMode')!='agent':
            raise RuntimeError('Local deployment requires agent mode')
        database=Path(config['productStateDirectory'])/'product.sqlite'
        with held_while_idle(database,allow_busy=args.action=='boot') as plan:
            return operate(args,root,config,plan)


def operate(args,root,config,plan):
    tunnels=tunnel_names(config);servers=['public-entry','cpu-server'];names=tunnels+servers
    if args.action!='stop':
        check_storage(config)
    if args.action!='boot':
        idle(config)          # a boot may find reservations from before the shutdown; the queue then stays held
    if args.action in ('stop','rotate','restart'):
        if args.action=='rotate' and config.get('namedTunnelConfig'):
            raise RuntimeError('A named tunnel has fixed addresses; there is nothing to rotate')
        selected=tunnels if args.action=='rotate' else servers if args.action=='restart' else names
        for name in selected:
            stop(root,name)
        if args.action!='restart' and not config.get('namedTunnelConfig'):
            config.pop('publicWebUrl',None);config.pop('publicComputeUrl',None)
        save_private(args.private/'config.json',config)
        if args.action=='stop':
            print('Owned CPU service and tunnels stopped.');return
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
    if config.get('namedTunnelConfig'):
        # Fixed host names come from the owner's tunnel configuration.
        named(root,'named-tunnel',config['namedTunnelConfig'],args.cloudflared,environment)
    else:
        (root/'quick-config.yml').write_text('{}\n');(root/'quick-config.yml').chmod(0o600)
        config['publicWebUrl']=quick(root,'web-quick',config.get('webEntryPort',8080),args.cloudflared,environment)
        config['publicComputeUrl']=quick(root,'compute-quick',config.get('computeEntryPort',8081),args.cloudflared,environment)
    save_private(args.private/'config.json',config)
    print(json.dumps({'webUrl':config['publicWebUrl'],'computeUrl':config['publicComputeUrl'],
        'privateBulkUrl':config['privateComputeUrl'],'computeStarted':False,
        'queue':'reopens when this action ends' if plan['reopen'] else
                ('held: a run or GPU reservation was live, an administrator must confirm in Operations' if plan['busy'] else 'held')},indent=2))


if __name__=='__main__':
    try:
        main()
    except Exception as error:
        # Validation errors may quote configuration, so only this script's own RuntimeErrors are shown.
        detail=f': {error}' if type(error) is RuntimeError else ''
        print(f'Local deployment failed ({type(error).__name__}{detail}). Check private logs/configuration.',file=sys.stderr)
        raise SystemExit(1)
