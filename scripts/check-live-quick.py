#!/usr/bin/env python3
"""Verify live TLS controls and private bulk isolation; starts no GPU workload."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import socket
import sys
import tempfile
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private',type=Path,required=True)
    parser.add_argument('--runtime-source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise FileExistsError('Acceptance receipts are immutable')
    sys.path.insert(0,str(args.runtime_source/'src'))
    from heteroes.http_transport import CoordinatorServer,HttpClient,UnauthorizedError,TransportError
    def probe_call(call):
        for attempt in range(3):
            try:return call()
            except UnauthorizedError:raise
            except (TransportError,urllib.error.URLError,TimeoutError):
                if attempt==2:raise
                time.sleep(.5)
    c=json.loads((args.private/'config.json').read_text())
    parsed=urlsplit(c['privateComputeUrl'])
    with socket.socket() as probe:
        if probe.connect_ex((parsed.hostname,parsed.port))==0:raise RuntimeError('Compute port already occupied; no process was stopped')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    class API:
        def handle(self,operation,payload,authenticated_worker_id=None):
            if payload.get('worker_id')!=authenticated_worker_id:return {'ok':False,'error':{'code':'forbidden'}}
            return {'ok':True,'generation_state':'OPEN','work':None}
    token=secrets.token_urlsafe(32)
    with tempfile.TemporaryDirectory(prefix='heteroes-quick-proof-') as directory:
        payload=b'private-transfer-proof\n'*100000;sha=hashlib.sha256(payload).hexdigest()
        weights=Path(directory);(weights/(sha+'.bin')).write_bytes(payload)
        server=CoordinatorServer(API(),job={'state':'PREPARING'},models_dir=weights,host=parsed.hostname,port=parsed.port,device_tokens={'probe':token})
        server.start()
        try:
            client=HttpClient(c['publicComputeUrl'],token=token,bulk_url=c['privateComputeUrl'],timeout=10)
            assert probe_call(lambda:client.get_json('/v1/health'))['ok'] is True
            assert probe_call(lambda:client.get_json('/v1/job'))['job']['state']=='PREPARING'
            assert client('lease',{'worker_id':'probe','request_id':'test'})['ok'] is True
            assert client('lease',{'worker_id':'other','request_id':'test'})['ok'] is False
            try:probe_call(lambda:HttpClient(c['publicComputeUrl'],bulk_url=c['privateComputeUrl'],timeout=10).get_json('/v1/health'))
            except UnauthorizedError:pass
            else:raise AssertionError('Missing credential was accepted')
            with client.open_stream('/v1/models/'+sha,start=19) as response:
                assert response.status==206 and response.read()==payload[19:]
            for base,path in [(c['publicComputeUrl'],'/v1/models/'+sha),(c['publicWebUrl'],'/api/v1/local-storage/test'),(c['publicWebUrl'],'/downloads/test.exe'),(c['publicWebUrl'],'/api/v1/datasets/import')]:
                try:opener.open(base+path,timeout=20)
                except urllib.error.HTTPError as error:assert error.code==403
                else:raise AssertionError('Public bulk route was accepted')
            with opener.open(c['publicWebUrl']+'/api/v1/health',timeout=20) as response:
                health=json.load(response)
            assert health['serverInstanceId']==c['serverInstanceId'] and health['privateLabUrl']==c['bulkApiUrl']
            result={'liveWebHttps':True,'liveComputeHttps':True,'missingCredentialRejected':True,'workerIdentityBound':True,
                'publicBulkDenied':True,'privateRangeTransferVerified':True,'bulkBytes':len(payload),'bulkSha256':sha,
                'serverInstanceId':c['serverInstanceId'],'webUrl':c['publicWebUrl'],'computeUrl':c['publicComputeUrl'],'gpuWork':False}
            args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
            print('PASS live Quick Web/API, authenticated compute HTTPS and private Range transfer')
        finally:server.stop()

if __name__=='__main__':main()
