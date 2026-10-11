"""Private S3-compatible recovery storage. Manifest publication is the commit."""
import hashlib
import json
import math
import re
import threading
import time
import uuid
from urllib.parse import urlparse

HEX=re.compile(r'[a-f0-9]{64}')
UUID=re.compile(r'[a-f0-9]{32}')
PART_BYTES=64*1024*1024


class QuotaExceeded(RuntimeError):pass


class S3Backend:
    """Keys remain on the control host; device uploads use scoped presigned URLs."""
    def __init__(self,config):
        import boto3
        from botocore.config import Config
        if not config.get('exclusiveAccountConfirmed'):
            raise ValueError('Confirm account-wide R2 free allowances before enabling uploads')
        endpoint=urlparse(config['endpointUrl'])
        if endpoint.scheme!='https' or not endpoint.hostname:raise ValueError('Storage endpoint requires HTTPS')
        self.bucket=config['bucket']
        self.client=boto3.client('s3',endpoint_url=config['endpointUrl'],region_name=config.get('region','auto'),
            aws_access_key_id=config['accessKeyId'],aws_secret_access_key=config['secretAccessKey'],
            config=Config(signature_version='s3v4',request_checksum_calculation='when_required',response_checksum_validation='when_required'))

    def inventory(self,before_request=None):
        def pages(operation,**params):
            iterator=iter(self.client.get_paginator(operation).paginate(**params))
            while True:
                # Reserve before advancing each page, including a conservative
                # final iterator check; large inventories cannot evade caps.
                if before_request:before_request()
                try:page=next(iterator)
                except StopIteration:return
                yield page
        total=0
        for page in pages('list_objects_v2',Bucket=self.bucket):
            total+=sum(o['Size'] for o in page.get('Contents',[]))
        # Include uploads from this bucket, not only our metadata reservation.
        for page in pages('list_multipart_uploads',Bucket=self.bucket):
            for upload in page.get('Uploads',[]):
                for parts in pages('list_parts',Bucket=self.bucket,Key=upload['Key'],UploadId=upload['UploadId']):
                    total+=sum(p['Size'] for p in parts.get('Parts',[]))
        return total

    def get(self,key):
        response=self.client.get_object(Bucket=self.bucket,Key=key)
        try:yield from response['Body'].iter_chunks(1024*1024)
        finally:response['Body'].close()

    def read_version(self,key):
        response=self.client.get_object(Bucket=self.bucket,Key=key)
        def chunks():
            try:yield from response['Body'].iter_chunks(1024*1024)
            finally:response['Body'].close()
        return response['ETag'],chunks()

    def publish_upload(self,source,destination,etag):
        self.client.copy_object(Bucket=self.bucket,Key=destination,
            CopySource={'Bucket':self.bucket,'Key':source},CopySourceIfMatch=etag)
        self.delete(source)

    def put(self,key,data):self.client.put_object(Bucket=self.bucket,Key=key,Body=data)
    def delete(self,key):self.client.delete_object(Bucket=self.bucket,Key=key)

    def upload_plan(self,key,size):
        if size<=PART_BYTES:
            return {'mode':'single','key':key,'url':self.client.generate_presigned_url('put_object',Params={
                'Bucket':self.bucket,'Key':key,'ContentLength':size},ExpiresIn=900),'headers':{'Content-Length':str(size)}}
        upload=self.client.create_multipart_upload(Bucket=self.bucket,Key=key)['UploadId']
        parts=[]
        for number in range(1,math.ceil(size/PART_BYTES)+1):
            length=min(PART_BYTES,size-(number-1)*PART_BYTES)
            url=self.client.generate_presigned_url('upload_part',Params={'Bucket':self.bucket,'Key':key,
                'UploadId':upload,'PartNumber':number,'ContentLength':length},ExpiresIn=900)
            parts.append({'number':number,'offset':(number-1)*PART_BYTES,'sizeBytes':length,'url':url})
        return {'mode':'multipart','key':key,'uploadId':upload,'parts':parts}

    def complete(self,key,upload_id,parts):
        self.client.complete_multipart_upload(Bucket=self.bucket,Key=key,UploadId=upload_id,MultipartUpload={'Parts':parts})

    def abort(self,key,upload_id):
        from botocore.exceptions import ClientError
        try:self.client.abort_multipart_upload(Bucket=self.bucket,Key=key,UploadId=upload_id)
        except ClientError as error:
            if error.response['Error']['Code']!='NoSuchUpload':raise

    def download_url(self,key):
        return self.client.generate_presigned_url('get_object',Params={'Bucket':self.bucket,'Key':key},ExpiresIn=60)


class CloudStorage:
    def __init__(self,store,backend,quota_bytes=8_000_000_000):
        self.store=store;self.backend=backend;self.quota=quota_bytes;self.lock=threading.RLock()
        with store.db() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS cloud_objects(sha TEXT PRIMARY KEY,size INTEGER NOT NULL,status TEXT NOT NULL,upload_plan TEXT,expires REAL);
                CREATE TABLE IF NOT EXISTS recovery_points(id TEXT PRIMARY KEY,run_id TEXT NOT NULL,generation INTEGER NOT NULL,final INTEGER NOT NULL,status TEXT NOT NULL,manifest TEXT NOT NULL,error TEXT,created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS cloud_refs(point_id TEXT NOT NULL,sha TEXT NOT NULL,PRIMARY KEY(point_id,sha));
                CREATE TABLE IF NOT EXISTS cloud_requests(month TEXT PRIMARY KEY,class_a INTEGER NOT NULL,class_b INTEGER NOT NULL);''')
        self.pending=set()

    def _requests(self,a=0,b=0):
        if getattr(self.backend,'cloud_free_tier',True) is False:
            return
        # Conservative project caps below the free request allowances. Direct
        # upload part requests are reserved before their URLs leave the server.
        month=time.strftime('%Y-%m',time.gmtime())
        with self.store.db() as db:
            row=db.execute('SELECT class_a,class_b FROM cloud_requests WHERE month=?',(month,)).fetchone()
            used_a,used_b=tuple(row) if row else (0,0)
            if used_a+a>200000 or used_b+b>2000000:raise QuotaExceeded('Project request quota reached')
            db.execute('INSERT OR REPLACE INTO cloud_requests VALUES (?,?,?)',(month,used_a+a,used_b+b))

    def validate_manifest(self,m):
        if not isinstance(m,dict) or m.get('formatVersion')!=1 or any(not isinstance(m.get(k),str) or not UUID.fullmatch(m[k]) for k in ('pointId','runId')):
            raise ValueError('Invalid recovery identity')
        if type(m.get('generation')) is not int or m['generation']<0 or type(m.get('final')) is not bool:raise ValueError('Invalid generation')
        policy=m.get('backupPolicy',{})
        if not isinstance(policy,dict) or set(policy)!={'interval','retain'} or any(type(v) is not int or not 1<=v<=1000 for v in policy.values()):raise ValueError('Invalid backup policy')
        files=m.get('files')
        if not isinstance(files,dict) or not {'ledger.sqlite','config.json','identity.json'}<=files.keys() or not 4<=len(files)<=5:
            raise ValueError('Incomplete recovery manifest')
        for name,meta in files.items():
            if name not in ('ledger.sqlite','config.json','identity.json') and not re.fullmatch(r'weights/[a-f0-9]{64}\.bin',name):raise ValueError('Unsafe recovery path')
            if not isinstance(meta,dict) or not isinstance(meta.get('sha256'),str) or not HEX.fullmatch(meta['sha256']) or type(meta.get('sizeBytes')) is not int or not 0<meta['sizeBytes']<=5_000_000_000:
                raise ValueError('Invalid recovery object')
            if name.startswith('weights/') and name[8:-4]!=meta['sha256']:raise ValueError('Weights name disagrees with checksum')
        for key in ('childWeightsSha256','parentWeightsSha256'):
            if not isinstance(m.get(key),str) or not HEX.fullmatch(m[key]) or 'weights/'+m[key]+'.bin' not in files:raise ValueError('Missing canonical weights')
        if len(json.dumps(m))>32768:raise ValueError('Manifest is too large')

    def usage(self):
        if isinstance(self.backend,S3Backend):observed=self.backend.inventory(lambda:self._requests(a=1))
        else:
            self._requests(a=1)
            observed=self.backend.inventory()
        with self.store.db() as db:
            reserved=2*db.execute('SELECT coalesce(sum(size),0) FROM cloud_objects WHERE status!="READY"').fetchone()[0]
        return {'quotaBytes':self.quota,'observedBytes':observed,'reservedBytes':reserved,
                'storageMode':getattr(self.backend,'mode','cloud'),
                'warning':observed+reserved>=self.quota*.8}

    def begin(self,m):
        self.validate_manifest(m)
        with self.lock:
            with self.store.db() as db:
                old=db.execute('SELECT manifest,status FROM recovery_points WHERE id=?',(m['pointId'],)).fetchone()
                if old and json.loads(old[0])!=m:raise ValueError('Frozen recovery manifest changed')
                if old and old['status']=='READY':return {'pointId':m['pointId'],'status':'READY','objects':[]}
                unique={}
                for meta in m['files'].values():
                    if meta['sha256'] in unique and unique[meta['sha256']]!=meta['sizeBytes']:raise ValueError('Hash/size mismatch')
                    unique[meta['sha256']]=meta['sizeBytes']
                existing={r['sha']:dict(r) for r in db.execute('SELECT * FROM cloud_objects')}
                if any(sha in existing and existing[sha]['size']!=size for sha,size in unique.items()):raise ValueError('Stored hash/size mismatch')
            usage=self.usage();new_bytes=2*sum(size for sha,size in unique.items() if sha not in existing)
            if usage['observedBytes']+usage['reservedBytes']+new_bytes+len(json.dumps(m))>self.quota:
                raise QuotaExceeded('Cloud storage quota reached; compute continues with local recovery points')
            plans=[]
            # Reserve before issuing any presigned upload rights.
            with self.store.db() as db:
                db.execute('INSERT OR IGNORE INTO recovery_points VALUES (?,?,?,?,?,?,NULL,?)',(m['pointId'],m['runId'],m['generation'],m['final'],'PENDING',json.dumps(m),time.time()))
                for sha,size in unique.items():
                    db.execute('INSERT OR IGNORE INTO cloud_objects VALUES (?,?,"PENDING",NULL,NULL)',(sha,size))
                    db.execute('INSERT OR IGNORE INTO cloud_refs VALUES (?,?)',(m['pointId'],sha))
            for sha,size in unique.items():
                entry=existing.get(sha)
                if entry and entry['status'] in ('READY','UPLOADED'):continue
                with self.store.db() as db:
                    row=db.execute('SELECT * FROM cloud_objects WHERE sha=?',(sha,)).fetchone()
                if row['upload_plan'] and (row['expires'] or 0)>time.time()+30:
                    plan=json.loads(row['upload_plan'])
                else:
                    if row['upload_plan']:
                        previous=json.loads(row['upload_plan'])
                        if previous.get('uploadId'):
                            self._requests(a=1);self.backend.abort(previous['key'],previous['uploadId'])
                    self._requests(a=math.ceil(size/PART_BYTES)+3)
                    plan=self.backend.upload_plan('uploads/'+sha+'/'+uuid.uuid4().hex,size)
                    with self.store.db() as db:
                        db.execute('UPDATE cloud_objects SET upload_plan=?,expires=? WHERE sha=?',(json.dumps(plan),time.time()+900,sha))
                plans.append({'sha256':sha,'sizeBytes':size,**plan})
            return {'pointId':m['pointId'],'status':'PENDING','objects':plans}

    def complete_object(self,point_id,sha,parts):
        with self.lock:
            with self.store.db() as db:
                row=db.execute('SELECT o.* FROM cloud_objects o JOIN cloud_refs r ON o.sha=r.sha WHERE r.point_id=? AND o.sha=?',(point_id,sha)).fetchone()
                if not row:raise ValueError('Object is not referenced by this point')
                if row['status'] in ('READY','UPLOADED'):return
                plan=json.loads(row['upload_plan'])
            if plan['mode']=='multipart':
                if len(parts)!=len(plan['parts']) or [p['PartNumber'] for p in parts]!=list(range(1,len(parts)+1)):
                    raise ValueError('Incomplete multipart upload')
                self._requests(a=1)
                self.backend.complete(plan['key'],plan['uploadId'],parts)
            with self.store.db() as db:db.execute('UPDATE cloud_objects SET status="UPLOADED" WHERE sha=?',(sha,))

    def verify(self,point_id):
        with self.lock:
            with self.store.db() as db:
                row=db.execute('SELECT * FROM recovery_points WHERE id=?',(point_id,)).fetchone()
                if not row:raise ValueError('Point not found')
                m=json.loads(row['manifest'])
            try:
                for sha in {meta['sha256'] for meta in m['files'].values()}:
                    with self.store.db() as db:obj=db.execute('SELECT * FROM cloud_objects WHERE sha=?',(sha,)).fetchone()
                    if obj['status']=='READY':continue
                    self._requests(b=1);hasher=hashlib.sha256();size=0
                    plan=json.loads(obj['upload_plan']);upload_key=plan['key']
                    if hasattr(self.backend,'read_version'):
                        etag,chunks=self.backend.read_version(upload_key)
                    else:
                        etag=None;chunks=self.backend.get(upload_key)
                    for chunk in chunks:
                        hasher.update(chunk);size+=len(chunk)
                        if size>obj['size']:raise ValueError('Object checksum/size mismatch')
                    if size!=obj['size'] or hasher.hexdigest()!=sha:raise ValueError('Object checksum/size mismatch')
                    self._requests(a=2)
                    self.backend.publish_upload(upload_key,'objects/'+sha,etag)
                    with self.store.db() as db:db.execute('UPDATE cloud_objects SET status="READY",upload_plan=NULL,expires=NULL WHERE sha=?',(sha,))
                self._requests(a=1)
                self.backend.put('manifests/'+point_id+'.json',json.dumps(m,sort_keys=True).encode())
                with self.store.db() as db:db.execute('UPDATE recovery_points SET status="READY",error=NULL WHERE id=?',(point_id,))
                self.retain(m['runId'],m['backupPolicy']['retain'])
                with self.store.db() as db:
                    body=self.store.get(m['runId'])
                    if body:
                        old=body.get('cloudSync',{})
                        if old.get('lastCloudGeneration',-1)<=m['generation']:
                            body['cloudSync']={'status':'READY','lastCloudGeneration':m['generation'],'pointId':point_id}
                            self.store.save(db,body)
            except Exception as error:
                if isinstance(error,ValueError):
                    with self.store.db() as db:
                        db.execute('UPDATE cloud_objects SET status="PENDING",upload_plan=NULL,expires=NULL WHERE sha=?',(sha,))
                with self.store.db() as db:db.execute('UPDATE recovery_points SET status=?,error=? WHERE id=?',('ERROR',type(error).__name__,point_id))
                raise

    def verify_background(self,point_id):
        with self.lock:
            if point_id in self.pending:return
            self.pending.add(point_id)
        def work():
            try:self.verify(point_id)
            except Exception:pass  # persisted typed error; no secret-bearing logs
            finally:
                with self.lock:self.pending.discard(point_id)
        threading.Thread(target=work,daemon=True).start()

    def points(self,run_id):
        with self.store.db() as db:
            return [{'pointId':r['id'],'generation':r['generation'],'final':bool(r['final']),'status':r['status'],'errorType':r['error']}
                for r in db.execute('SELECT * FROM recovery_points WHERE run_id=? ORDER BY generation DESC,created DESC',(run_id,))]

    def manifest(self,point_id):
        with self.store.db() as db:
            row=db.execute('SELECT manifest,status FROM recovery_points WHERE id=?',(point_id,)).fetchone()
            if not row or row['status']!='READY':raise ValueError('Verified recovery point unavailable')
            return json.loads(row['manifest'])

    def retain(self,run_id,count):
        points=[p for p in self.points(run_id) if p['status']=='READY' and not p['final']]
        for point in points[count:]:self.delete_point(point['pointId'])

    def delete_point(self,point_id):
        with self.lock:
            self._requests(a=1);self.backend.delete('manifests/'+point_id+'.json')
            with self.store.db() as db:
                db.execute('DELETE FROM cloud_refs WHERE point_id=?',(point_id,))
                db.execute('DELETE FROM recovery_points WHERE id=?',(point_id,))
                orphaned=[dict(r) for r in db.execute('SELECT * FROM cloud_objects o WHERE NOT EXISTS(SELECT 1 FROM cloud_refs r WHERE r.sha=o.sha)')]
            for obj in orphaned:
                plan=json.loads(obj['upload_plan']) if obj['upload_plan'] else {}
                if plan.get('uploadId'):
                    self._requests(a=1);self.backend.abort(plan['key'],plan['uploadId'])
                if plan.get('key'):
                    self._requests(a=1);self.backend.delete(plan['key'])
                self._requests(a=1);self.backend.delete('objects/'+obj['sha'])
                with self.store.db() as db:db.execute('DELETE FROM cloud_objects WHERE sha=?',(obj['sha'],))


def install_storage_routes(app,store,storage,device_auth,user,scoped,authorized):
    import secrets
    from fastapi import Depends,HTTPException,Request,Response
    from fastapi.responses import RedirectResponse
    from pydantic import BaseModel,ConfigDict,Field

    class Begin(BaseModel):
        model_config=ConfigDict(extra='forbid')
        assignmentId:str
        epoch:int
        manifest:dict

    class Finish(BaseModel):
        model_config=ConfigDict(extra='forbid')
        assignmentId:str
        epoch:int
        pointId:str
        sha256:str
        parts:list[dict]=Field(default_factory=list,max_length=10000)

    def grant(device,assignment_id,epoch,run_id):
        with store.db() as db:
            row=db.execute('SELECT coordinator,epoch,run_id FROM assignments WHERE id=?',(assignment_id,)).fetchone()
            if not row or (row['coordinator'],row['epoch'],row['run_id'])!=(device['id'],epoch,run_id):
                raise HTTPException(403,'Recovery upload is outside this assignment')

    def point_run(point_id):
        with store.db() as db:
            row=db.execute('SELECT run_id FROM recovery_points WHERE id=?',(point_id,)).fetchone()
            if not row:raise HTTPException(404,'Recovery point not found')
            return row[0]

    def cloud_error(error):
        raise HTTPException(409 if isinstance(error,QuotaExceeded) else 422,
            'Cloud quota reached; local computation continues' if isinstance(error,QuotaExceeded) else 'Recovery storage operation failed') from None

    @app.post('/api/v1/device/recovery-points')
    def begin(body:Begin,current=Depends(device_auth)):
        grant(current,body.assignmentId,body.epoch,body.manifest.get('runId'))
        try:return storage.begin(body.manifest)
        except (ValueError,QuotaExceeded) as error:cloud_error(error)

    @app.post('/api/v1/device/recovery-points/complete-object')
    def complete(body:Finish,current=Depends(device_auth)):
        grant(current,body.assignmentId,body.epoch,point_run(body.pointId))
        try:storage.complete_object(body.pointId,body.sha256,body.parts)
        except (ValueError,QuotaExceeded) as error:cloud_error(error)
        return {'ok':True}

    @app.post('/api/v1/device/recovery-points/{point_id}/verify')
    def verify(point_id:str,body:dict,current=Depends(device_auth)):
        grant(current,body.get('assignmentId'),body.get('epoch'),point_run(point_id))
        storage.verify_background(point_id)
        return {'status':'VERIFYING'}

    @app.get('/api/v1/device/recovery-points/{point_id}')
    def device_status(point_id:str,current=Depends(device_auth)):
        run_id=point_run(point_id)
        with store.db() as db:
            row=db.execute('SELECT coordinator FROM assignments WHERE run_id=?',(run_id,)).fetchone()
            if not row or row[0]!=current['id']:raise HTTPException(403,'Coordinator identity required')
        return next(p for p in storage.points(run_id) if p['pointId']==point_id)

    @app.delete('/api/v1/device/recovery-points/{point_id}')
    def abandon(point_id:str,body:dict,current=Depends(device_auth)):
        grant(current,body.get('assignmentId'),body.get('epoch'),point_run(point_id))
        with storage.lock:
            point=next(p for p in storage.points(point_run(point_id)) if p['pointId']==point_id)
            # Local retention must never remove the last good cloud point while
            # newer local generations are waiting for upload.
            if point['status']=='READY':return {'deleted':False,'retained':True}
            storage.delete_point(point_id)
        return {'deleted':True}

    def historical(run_id,current):
        body=authorized(run_id,current)
        if not current.get('platformAdmin') or body['status']!='COMPLETED':
            raise HTTPException(403,'Completed experiment and platform administrator required')
        with store.db() as db:
            if db.execute('SELECT 1 FROM assignments WHERE run_id=?',(run_id,)).fetchone():
                raise HTTPException(409,'Use the assigned coordinator for this experiment')
        return body

    @app.post('/api/v1/experiments/{run_id}/recovery-import')
    def import_begin(run_id:str,body:dict,current=Depends(scoped)):
        experiment=historical(run_id,current)
        if body.get('runId')!=run_id or body.get('final') is not True or body.get('childWeightsSha256')!=experiment.get('modelVersion'):
            raise HTTPException(422,'Imported point disagrees with the historical final checkpoint')
        try:result=storage.begin(body)
        except (ValueError,QuotaExceeded) as error:cloud_error(error)
        with store.db() as db:store.audit(db,current['userId'],'HISTORICAL_RECOVERY_IMPORT',body['pointId'],experiment['workspaceId'])
        return result

    @app.post('/api/v1/experiments/{run_id}/recovery-import/complete-object')
    def import_complete(run_id:str,body:dict,current=Depends(scoped)):
        historical(run_id,current)
        if point_run(body.get('pointId'))!=run_id:raise HTTPException(403,'Recovery point belongs to another experiment')
        try:storage.complete_object(body['pointId'],body['sha256'],body.get('parts',[]))
        except (ValueError,QuotaExceeded) as error:cloud_error(error)
        return {'ok':True}

    @app.post('/api/v1/experiments/{run_id}/recovery-import/{point_id}/verify')
    def import_verify(run_id:str,point_id:str,current=Depends(scoped)):
        historical(run_id,current)
        if point_run(point_id)!=run_id:raise HTTPException(403,'Recovery point belongs to another experiment')
        storage.verify_background(point_id)
        return {'status':'VERIFYING'}

    @app.get('/api/v1/experiments/{run_id}/recovery-points')
    def points(run_id:str,current=Depends(scoped)):
        authorized(run_id,current)
        return storage.points(run_id)

    @app.post('/api/v1/recovery-points/{point_id}/download-plan')
    def download_plan(point_id:str,current=Depends(scoped)):
        authorized(point_run(point_id),current)
        try:m=storage.manifest(point_id)
        except ValueError:raise HTTPException(409,'Recovery point is not verified') from None
        storage._requests(b=len(m['files']))
        return {'manifest':m,'objects':{name:storage.backend.download_url('objects/'+meta['sha256']) for name,meta in m['files'].items()}}

    @app.delete('/api/v1/recovery-points/{point_id}')
    def delete(point_id:str,current=Depends(scoped)):
        body=authorized(point_run(point_id),current)
        storage.delete_point(point_id)
        with store.db() as db:store.audit(db,current['userId'],'CLOUD_COPY_DELETED',point_id,body['workspaceId'])
        return {'deleted':True}

    @app.get('/api/v1/platform/storage')
    def usage(current=Depends(user)):
        fresh=store.profile(current['userId'])
        if fresh['accountStatus']!='ACTIVE' or not fresh.get('platformAdmin'):raise HTTPException(403,'Platform administrator required')
        return storage.usage()

    with store.db() as db:
        db.execute('CREATE TABLE IF NOT EXISTS cloud_downloads(digest TEXT PRIMARY KEY,user_id TEXT NOT NULL,session_digest TEXT NOT NULL,run_id TEXT NOT NULL,sha TEXT NOT NULL,expires REAL NOT NULL)')

    @app.post('/api/v1/artifacts/{artifact_id}/download-ticket')
    def ticket(artifact_id:str,response:Response,request:Request,current=Depends(scoped)):
        run_id,_,name=artifact_id.partition('.')
        authorized(run_id,current)
        if not re.fullmatch('[a-f0-9]{64}\\.bin',name):raise HTTPException(404,'Cloud checkpoint not found')
        sha=name[:-4]
        found=False
        for point in storage.points(run_id):
            if point['status']=='READY' and any(v['sha256']==sha for v in storage.manifest(point['pointId'])['files'].values()):found=True;break
        if not found:raise HTTPException(404,'Cloud checkpoint not ready')
        secret=secrets.token_urlsafe(32);td=hashlib.sha256(secret.encode()).hexdigest()
        session_digest=hashlib.sha256(request.headers.get('Authorization','')[7:].encode()).hexdigest()
        path='/api/v1/cloud-downloads/'+td
        with store.db() as db:db.execute('INSERT INTO cloud_downloads VALUES (?,?,?,?,?,?)',(td,current['userId'],session_digest,run_id,sha,time.time()+60))
        response.set_cookie('heteroes-cloud-download',secret,httponly=True,secure=request.url.scheme=='https',samesite='strict',path=path,max_age=60)
        return {'downloadUrl':path}

    @app.get('/api/v1/cloud-downloads/{ticket_digest}')
    def consume(ticket_digest:str,request:Request):
        secret=request.cookies.get('heteroes-cloud-download','')
        if hashlib.sha256(secret.encode()).hexdigest()!=ticket_digest:raise HTTPException(401,'Download ticket required')
        with store.db() as db:
            row=db.execute('SELECT * FROM cloud_downloads WHERE digest=? AND expires>?',(ticket_digest,time.time())).fetchone()
            if not row:raise HTTPException(401,'Download ticket expired')
            if not db.execute('SELECT 1 FROM sessions WHERE digest=? AND user_id=? AND expires>?',(row['session_digest'],row['user_id'],time.time())).fetchone():raise HTTPException(401,'Session revoked')
            body=store.get(row['run_id']);profile=store.profile(row['user_id'])
            membership=db.execute('SELECT role FROM memberships WHERE workspace_id=? AND user_id=?',(body['workspaceId'],row['user_id'])).fetchone()
            if profile['accountStatus']!='ACTIVE' or not membership or (membership[0]!='ADMIN' and body['ownerUserId']!=row['user_id']):raise HTTPException(403,'Experiment access revoked')
            db.execute('DELETE FROM cloud_downloads WHERE digest=?',(ticket_digest,))
        storage._requests(b=1)
        response=RedirectResponse(storage.backend.download_url('objects/'+row['sha']),status_code=303)
        response.delete_cookie('heteroes-cloud-download',path='/api/v1/cloud-downloads/'+ticket_digest)
        response.headers['Referrer-Policy']='no-referrer'
        return response
