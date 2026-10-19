"""Asynchronous recovery upload, using scoped URLs and no cloud master keys."""
import hashlib
import json
import shutil
import threading
import time
import urllib.request
from .files import read_json,write_json
from .recovery import verify_point
from .storage import data_root


class CloudSync:
    def __init__(self,agent):
        self.agent=agent;self.stop=threading.Event()
        self.thread=threading.Thread(target=self.run,daemon=True)

    def upload(self,point,assignment):
        manifest=verify_point(point)
        body={'assignmentId':assignment['assignmentId'],'epoch':assignment['epoch'],'manifest':manifest}
        plan=self.agent.call('/api/v1/device/recovery-points',body)
        write_json(point/'cloud-state.json',{'status':plan['status'],'remoteCreated':True,'t':time.time()})
        for obj in plan['objects']:
            source=next(point/name for name,meta in manifest['files'].items() if meta['sha256']==obj['sha256'])
            parts=[]
            with open(source,'rb') as stream:
                if obj['mode']=='single':
                    data=stream.read(obj['sizeBytes'])
                    request=urllib.request.Request(obj['url'],data=data,method='PUT',headers=obj['headers'])
                    with urllib.request.urlopen(request,timeout=180) as response:response.read()
                else:
                    for part in obj['parts']:
                        stream.seek(part['offset']);data=stream.read(part['sizeBytes'])
                        if len(data)!=part['sizeBytes']:raise ValueError('Local recovery point changed')
                        request=urllib.request.Request(part['url'],data=data,method='PUT',headers={'Content-Length':str(len(data))})
                        with urllib.request.urlopen(request,timeout=180) as response:
                            etag=response.headers['ETag'];response.read()
                        parts.append({'PartNumber':part['number'],'ETag':etag})
            self.agent.call('/api/v1/device/recovery-points/complete-object',{
                'assignmentId':assignment['assignmentId'],'epoch':assignment['epoch'],
                'pointId':manifest['pointId'],'sha256':obj['sha256'],'parts':parts})
        self.agent.call('/api/v1/device/recovery-points/'+manifest['pointId']+'/verify',{
            'assignmentId':assignment['assignmentId'],'epoch':assignment['epoch']})
        return manifest

    def cycle(self):
        for root in self.agent.manager.root.iterdir():
            if not root.is_dir():continue
            assignment=read_json(root/'assignment.json')
            if not assignment:continue
            cleanup=read_json(root/'cloud-cleanup.json',[])
            remaining=[]
            for point_id in cleanup:
                try:
                    self.agent.call('/api/v1/device/recovery-points/'+point_id,
                        {'assignmentId':assignment['assignmentId'],'epoch':assignment['epoch']},method='DELETE')
                except urllib.error.HTTPError as error:
                    if error.code!=404:remaining.append(point_id)
                except Exception:remaining.append(point_id)
            write_json(root/'cloud-cleanup.json',remaining)
            points=[p for p in (data_root(root)/'recovery-points').glob('*') if p.is_dir() and (p/'manifest.json').exists()]
            points.sort(key=lambda p:(read_json(p/'manifest.json')['generation'],p.stat().st_mtime),reverse=True)
            for point in points:
                status=read_json(point/'cloud-state.json',{})
                if status.get('status')=='READY':continue
                try:
                    if status.get('status')=='VERIFYING':
                        result=self.agent.call('/api/v1/device/recovery-points/'+point.name,None)
                        if result['status']=='READY':
                            write_json(point/'cloud-state.json',{'status':'READY','t':time.time()})
                            write_json(root/'cloud-sync.json',{'status':'READY','lastCloudGeneration':read_json(point/'manifest.json')['generation'],'pointId':point.name,'t':time.time()})
                            continue
                        if result['status']!='ERROR':continue
                    self.upload(point,assignment)
                    write_json(point/'cloud-state.json',{'status':'VERIFYING','t':time.time()})
                except Exception as error:
                    write_json(root/'cloud-sync.json',{'status':'PENDING','errorType':type(error).__name__,'t':time.time()})
                    break
            # Bound local unuploaded points without deleting the current upload.
            # This cycle is single-threaded; a newly created point is included next.
            retain=read_json(points[0]/'manifest.json')['backupPolicy']['retain'] if points else assignment['config'].get('backupPolicy',{'retain':3})['retain']
            ordinary=[p for p in points if not read_json(p/'manifest.json')['final']]
            for point in ordinary[retain:]:
                if read_json(point/'cloud-state.json',{}).get('remoteCreated'):
                    remaining.append(point.name)
                    # Persist the cleanup intent before removing the local bytes.
                    write_json(root/'cloud-cleanup.json',list(dict.fromkeys(remaining)))
                shutil.rmtree(point)

    def run(self):
        while not self.stop.is_set():
            try:self.cycle()
            except Exception as error:
                write_json(self.agent.root/'cloud-error.json',{'errorType':type(error).__name__,'t':time.time()})
            self.stop.wait(30)
