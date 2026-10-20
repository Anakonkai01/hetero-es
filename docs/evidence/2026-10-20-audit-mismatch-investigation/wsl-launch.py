import os,sys
from heteroes.product.remote import worker_environment
env=worker_environment(os.environ['PYTHONPATH'],'offline-candidate-probe')
os.execve(sys.executable,[sys.executable,os.environ.get('HETEROES_PROBE_SCRIPT','/tmp/heteroes-audit-investigation/reproduce.py'),*sys.argv[1:]],env)
