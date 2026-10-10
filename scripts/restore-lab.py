#!/usr/bin/env python3
"""Verify a lab bundle and restore into a new, inactive deployment directory."""
import argparse
import json
import os
from pathlib import Path
import sys
import secrets
import tarfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.backup import restore_bundle

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle',type=Path)
    parser.add_argument('destination',type=Path)
    parser.add_argument('--source-config',type=Path,help='Bind new private configuration using these existing host/interpreter settings')
    args=parser.parse_args()
    try:
        result=restore_bundle(args.bundle,args.destination)
        if args.source_config:
            cfg=json.loads(args.source_config.read_text())
            root=Path(result['deploymentDirectory']);private=root/'private';private.mkdir(mode=0o700)
            cfg.update(stateDirectory=str(root/'runs'),productStateDirectory=str(root/'product'),
                       processDirectory=str(root/'services'),credentialsFile=str(private/'credentials.json'))
            suffix='restore-'+secrets.token_hex(8)
            for worker in cfg['workers']:
                worker['stateDirectory']=str(Path(worker['stateDirectory'])/suffix)
            for name,value in [('config.json',cfg),('credentials.json',{'runtime_token':secrets.token_urlsafe(32),'users':{}})]:
                file=private/name;file.write_text(json.dumps(value,indent=2));os.chmod(file,0o600)
    except (ValueError,OSError,tarfile.TarError) as error:
        parser.exit(1,str(error)+'\n')
    print(result['deploymentDirectory'])
    print('Sessions revoked; queue held. Bind a NEW private config and process/worker directories before starting services.')
