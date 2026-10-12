"""Prepare immutable dataset/model files through private assignment grants."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import urllib.request
from urllib.parse import urlsplit
from .data import verify as verify_data,sha
from .models import verify as verify_model


def transfer(agent,assignment,digest,target,limit):
    target=Path(target)
    if target.is_file():
        with target.open('rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest()==digest:return target
        raise ValueError('Cached study file checksum mismatch')
    grant=agent.call('/api/v1/device/study-transfer',{'assignmentId':assignment['assignmentId'],'epoch':assignment['epoch'],'sha256':digest})
    parsed=urlsplit(grant['url'])
    origin=f'{parsed.scheme}://{parsed.netloc}'
    # Reuse transport validation; never route a large file through public URLs.
    from heteroes.http_transport import HttpClient
    HttpClient(origin,bulk_url=origin)
    target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd,name=tempfile.mkstemp(prefix='.pending-',dir=target.parent)
    temporary=Path(name)
    try:
        hasher=hashlib.sha256();total=0
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(grant['url'],timeout=120) as response,os.fdopen(fd,'wb') as out:
            while chunk:=response.read(1024**2):
                total+=len(chunk)
                if total>limit:raise ValueError('Study transfer exceeds its bound')
                hasher.update(chunk);out.write(chunk)
            out.flush();os.fsync(out.fileno())
        if hasher.hexdigest()!=digest:raise ValueError('Study transfer checksum mismatch')
        os.replace(temporary,target)
    finally:temporary.unlink(missing_ok=True)
    return target


def prepare(agent,assignment,config,directory):
    from heteroes.product.storage import checked_directory
    cache=checked_directory(agent.config.get('largeDataDirectory',str(agent.root/'study-cache')),agent.config.get('storageVolumeUUID'))/'study'
    data_path=transfer(agent,assignment,config['datasetObjectSha256'],cache/'datasets'/f"{config['datasetObjectSha256']}.json",10_000_000)
    data=verify_data(json.loads(data_path.read_text()))
    if {k:data[k] for k in ('contentHash','splitHashes')}!=config['datasetIdentity']:raise ValueError('Frozen dataset identity mismatch')
    manifest=config['modelManifest']
    # Operator paths are private configuration, never browser-supplied paths.
    model_path=agent.config.get('modelPaths',{}).get(sha(manifest))
    if not model_path and manifest['modelId']=='Qwen/Qwen2.5-0.5B-Instruct' and manifest['revision']=='7ae557604adf67be50417f59c2c2f167def9a775':
        model_path=agent.config['modelPath']
    if not model_path:
        model_path=cache/'models'/sha(manifest)
        for name,digest in manifest['files'].items():
            target=Path(model_path)/name
            if config['modelSource']=='UPLOAD':transfer(agent,assignment,digest,target,5_000_000_000)
            else:
                from huggingface_hub import hf_hub_download
                hf_hub_download(manifest['modelId'],name,revision=manifest['revision'],local_dir=model_path)
    verify_model(model_path,manifest)
    from heteroes.product.files import write_json
    directory=Path(directory)
    write_json(directory/'model-manifest.json',manifest)
    return {'modelPath':str(model_path),'datasetPath':str(data_path),'modelManifestPath':str(directory/'model-manifest.json')}
