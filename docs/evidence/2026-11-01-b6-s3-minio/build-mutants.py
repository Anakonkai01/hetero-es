import json
from pathlib import Path
configuration=[];io=[]
def add(group,name,file,old,new):
 assert Path(file).read_text().count(old)==1,(name,Path(file).read_text().count(old));group.append(dict(name=name,file=file,old=old,new=new))
p='backend/storage/s3_backend.py'
add(configuration,'public bulk endpoint accepted',p,'private = endpoint(config["deviceEndpointUrl"], private=True)','private = _internal_endpoint(config["deviceEndpointUrl"])')
add(configuration,'public HTTP or path-bearing internal endpoint accepted',p,'return endpoint(value)','return value.rstrip("/")')
add(configuration,'ambient credentials permitted',p,'not isinstance(config.get(name), str) or not config[name]','False')
add(configuration,'logical buckets share a namespace',p,'or len(set(buckets.values())) != 3','or False')
add(configuration,'old R2 account gate restored',p,'internal = _internal_endpoint(config["endpointUrl"])','''if not config.get("exclusiveAccountConfirmed"):
            raise ValueError("R2 confirmation required")
        internal = _internal_endpoint(config["endpointUrl"])''')
add(configuration,'SigV4 disabled',p,'signature_version="s3v4"','signature_version="s3"')
add(configuration,'path-style addressing disabled',p,'s3={"addressing_style": "path"}','s3={"addressing_style": "virtual"}')
add(configuration,'ambient proxy configuration enabled',p,'proxies={},','proxies=None,')
add(configuration,'unsafe storage keys accepted',p,'if not isinstance(key, str) or not KEY.fullmatch(key):','if False:')
add(io,'device URLs signed for internal hostname',p,'endpoint_url=private','endpoint_url=internal')
add(io,'incomplete multipart bytes excluded from quota',p,'total += sum(item["Size"] for item in parts.get("Parts", []))','total += 0')
add(io,'dataset and backup bytes excluded from shared quota',p,'''for bucket in self._buckets.values():
            for page in self.client.get_paginator("list_objects_v2")''','''for bucket in [self._buckets["recovery"]]:
            for page in self.client.get_paginator("list_objects_v2")''')
add(io,'changed upload may publish after verification',p,'            CopySourceIfMatch=etag,\n','')
add(io,'published staging upload remains visible',p,'        self.delete(source)','        pass')
add(io,'file publication ignores expected checksum',p,'if expected is not None:','if False:')
add(io,'metadata dumps go to recovery bucket',p,'return self._buckets["backups"]','return self._buckets["recovery"]')
add(io,'dataset view becomes recovery storage',p,'view._purpose = purpose','view._purpose = "recovery"')
add(io,'public capabilities lose bucket binding',p,'signer.secret = hmac.new(signer.secret, self._buckets[purpose].encode(), hashlib.sha256).digest()','pass')
add(io,'public upload length header ignored',p,'if content_length != str(grant["size"]):','if False:')
add(io,'public upload size cap ignored at consumption',p,'or not 0 < grant["size"] <= PUBLIC_STUDY_MAX_BYTES','or False')
add(io,'oversized dataset public URLs minted',p,'if size > PUBLIC_STUDY_MAX_BYTES:','if False:')
add(io,'oversized public download is relayed',p,'if response["ContentLength"] > PUBLIC_STUDY_MAX_BYTES:','if False:')
add(io,'public proxy temporary files retained','backend/api/s3_storage.py','await run_in_threadpool(shutil.rmtree, work, True)','pass')
add(io,'reserved bulk API relays are exposed','backend/api/s3_storage.py','raise HTTPException(403, "Private LAN/Tailscale transfer required")','return {"relayed": True}')
add(io,'S3 clients left open on app shutdown','backend/apps/factory.py','if hasattr(storage_backend, "close"):','if False:')
p='backend/services/study_registry.py'
add(io,'inline dataset goes to model bucket',p,'store_backend = backend("datasets")','store_backend = backend()')
add(io,'dataset upload plan goes to model bucket',p,'b = backend("datasets")','b = backend()')
add(io,'built dataset goes to model bucket',p,'limits, b = dataset_limits(registry.store), backend("datasets")','limits, b = dataset_limits(registry.store), backend()')
add(io,'frozen dataset transfers use recovery bucket',p,'selected = backend("datasets" if sha in datasets else "recovery")','selected = backend()')
add(io,'local storage rejects PostgreSQL metadata','backend/storage/local_backend.py','product\\.(?:sqlite|pgdump)','product\\.sqlite')
Path('.scratch/review-2026-11/B6/config-mutants-initial.json').write_text(json.dumps(configuration,indent=2)+'\n')
equivalent=configuration.pop(0)
equivalent['equivalence']='The initial private endpoint check is independently enforced by LocalBackend via Enrollment.private_compute in _signer_for, before S3 clients/presigner creation. Removing only the initial check still rejects public device origins.'
Path('.scratch/review-2026-11/B6/equivalent-mutants.json').write_text(json.dumps([equivalent],indent=2)+'\n')
for name,items in [('config-mutants.json',configuration),('io-mutants.json',io)]:
 Path('.scratch/review-2026-11/B6',name).write_text(json.dumps(items,indent=2)+'\n')
print('Configuration',len(configuration),'I/O',len(io),'mutants')
