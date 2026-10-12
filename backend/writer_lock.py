"""Kernel lifetime lock for one production management writer per database."""
import os
from pathlib import Path
import sys


def acquire_writer(database):
    database=Path(database).resolve()
    database.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    stream=open(database.with_name(database.name+'.writer.lock'),'a+b')
    try:
        if sys.platform=='win32':
            import msvcrt
            stream.seek(0,2)
            if stream.tell()==0:stream.write(b'0');stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(stream,fcntl.LOCK_EX | fcntl.LOCK_NB)
        os.chmod(stream.name,0o600)
        return stream
    except (OSError,BlockingIOError):
        stream.close()
        raise RuntimeError('A Lab Server already owns this database') from None
