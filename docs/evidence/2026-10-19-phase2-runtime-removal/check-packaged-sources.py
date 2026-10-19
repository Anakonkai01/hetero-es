"""Build source tarballs on a scratch copy and import them; no installer or lab write."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile


REPO = Path(__file__).resolve().parents[3]
RUNTIME_PYTHON = Path.home() / 'miniforge3/envs/heteroes-match/bin/python'


def run(argv, **kwargs):
    subprocess.run([str(arg) for arg in argv], check=True, **kwargs)


with tempfile.TemporaryDirectory(prefix='heteroes-source-packaging-') as temporary:
    scratch = Path(temporary)
    (scratch / 'scripts').mkdir()
    shutil.copytree(REPO / 'backend', scratch / 'backend',
                    ignore=shutil.ignore_patterns('tests', '__pycache__'))
    for app in ['worker', 'server']:
        resources = scratch / f'desktop/{app}/resources'
        resources.mkdir(parents=True)
        shutil.copyfile(REPO / f'desktop/{app}/resources/profile.json', resources / 'profile.json')
    electron = scratch / 'desktop/worker/electron'
    electron.mkdir()
    for name in ['setup.cjs', 'download.cjs']:
        shutil.copyfile(REPO / 'desktop/worker/electron' / name, electron / name)
    for name in ['refresh-worker-runtime.py', 'refresh-server-runtime.py']:
        shutil.copyfile(REPO / 'scripts' / name, scratch / 'scripts' / name)
    # Source packaging needs a web directory. The actual UI build is checked separately.
    (scratch / 'web/assets').mkdir(parents=True)
    (scratch / 'web/index.html').write_text('<html>Packaging fixture</html>')
    run([sys.executable, '-I', scratch / 'scripts/refresh-worker-runtime.py', '--track-a', REPO / 'runtime'])
    run([sys.executable, '-I', scratch / 'scripts/refresh-server-runtime.py', '--web', scratch / 'web'])
    for app in ['worker', 'server']:
        with tarfile.open(scratch / f'desktop/{app}/resources/runtime.tar.gz') as archive:
            names = archive.getnames()
            for retired in ['backend/runtime.py', 'src/heteroes/product/gateway.py', 'src/heteroes/product/backup.py']:
                assert retired not in names
            assert ('src/heteroes/product/run_supervisor.py' if app == 'worker' else 'backend/errors.py') in names
            extracted = scratch / f'extracted-{app}'
            archive.extractall(extracted, filter='data')
        if app == 'worker':
            code = ('from heteroes.product.agent import AgentManager; '
                    'from heteroes.product.run_supervisor import RunSupervisor; '
                    'import heteroes.product.runner; '
                    'assert issubclass(AgentManager, RunSupervisor)')
            source = extracted / 'src'
            python = RUNTIME_PYTHON
        else:
            code = 'from backend.app import create_app; from backend.errors import RuntimeRejected'
            source = extracted
            python = sys.executable
        # Isolated interpreters cannot fall back to the working tree or user site.
        code = ('import sys; sys.path.insert(0, sys.argv[1]); ' + code
                + '; assert "torch" not in sys.modules; print("PASS packaged ' + app + ' source imports")')
        run([python, '-I', '-c', code, source], cwd=scratch, env={**os.environ, 'CUDA_VISIBLE_DEVICES': ''})
        print(json.dumps({'app': app, 'archiveFiles': len(names), 'retiredModulesAbsent': True}))
