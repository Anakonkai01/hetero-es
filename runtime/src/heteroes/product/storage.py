"""Owner-configured large data; live ledgers and process records stay on ext4."""
import os
from pathlib import Path
import re
import subprocess
import hashlib
from .files import read_json


def checked_directory(directory, volume_uuid=None):
    path=Path(directory)
    if not path.is_absolute():raise ValueError('Large-data directory must be absolute')
    path=path.resolve()
    if path==Path('/mnt/sekai') or Path('/mnt/sekai') in path.parents:
        raise ValueError('Sekai is not authorized for large data')
    if volume_uuid:
        if os.name=='nt' or not re.fullmatch('[a-fA-F0-9-]+',volume_uuid):
            raise ValueError('Unsupported storage volume identity')
        ancestor=path
        while not ancestor.exists():ancestor=ancestor.parent
        source=subprocess.run(['findmnt','-rn','-T',str(ancestor),'-o','SOURCE'],
            check=True,capture_output=True,text=True,timeout=5).stdout.strip()
        expected=Path('/dev/disk/by-uuid')/volume_uuid
        if not expected.exists() or Path(source).resolve()!=expected.resolve():
            raise ValueError('Selected large-data volume is unavailable')
    return path


def data_root(root):
    root=Path(root)
    setting=read_json(root/'large-data.json')
    if setting is None:return root
    path=checked_directory(setting['directory'],setting.get('volumeUUID'))
    return path


def worker_cache(directory,config):
    if not config.get('largeDataDirectory'):return Path(directory)/'cache'
    base=checked_directory(config['largeDataDirectory'],config.get('storageVolumeUUID'))
    owner=hashlib.sha256(str(Path(config['stateDirectory']).resolve()).encode()).hexdigest()[:16]
    path=base/'worker-cache'/owner/Path(directory).parent.name/Path(directory).name
    path.mkdir(parents=True,exist_ok=True,mode=0o700)
    return path
