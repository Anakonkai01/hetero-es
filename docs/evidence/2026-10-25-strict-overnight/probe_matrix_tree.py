"""Finite scratch common matrix tile sweep."""
from pathlib import Path
script=Path(__file__).with_name('probe_tiled_linear.py').read_text()
script=script.replace('from tiled_linear import prepare','from matrix_tree import prepare')
script=script.replace("with_name('tiled_linear.py')", "with_name('matrix_tree.py')")
script=script.replace('for per,tile,groups in ((4,8,4),(8,8,4),(8,16,4),(8,32,4),(16,8,2),(16,16,2)):',
                      'for per,tile,groups in ((32,2,128),(32,4,128),(64,2,128),(64,4,128),(64,8,128),(128,4,64)):')
script=script.replace('prepare(x,w,tile=tile,per=per,groups=groups)',
                      'prepare(x,w,tile=tile,kt=per,outputs_per_block=groups)')
exec(compile(script, str(Path(__file__).with_name('probe_tiled_linear.py')), 'exec'))
