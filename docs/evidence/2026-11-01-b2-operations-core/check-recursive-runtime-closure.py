"""Exercise the unchanged dependency-closure assertions with recursive backend traversal in scratch."""
import hashlib
import json
from pathlib import Path

root=Path('/home/pc5070ti/projects/heteroes')
p=root/'backend/tests/test_shared_runtime.py';source=p.read_text();needle='.glob("*.py")'
assert source.count(needle)==1
recursive=source.replace(needle,'.rglob("*.py")')
loop='    for path in (repo / "backend").rglob("*.py"):\n'
assert recursive.count(loop)==1
recursive=recursive.replace(loop,loop+'        if "tests" in path.relative_to(repo / "backend").parts:\n            continue\n')
recursive=recursive.replace('        relative = Path(*module.split(".")[1:])','        if module == "heteroes":\n            return "__init__.py"\n        relative = Path(*module.split(".")[1:])')
scope={'__file__':str(p),'__name__':'recursive_runtime_closure_check'}
exec(compile(recursive,str(p),'exec'),scope)
scope['test_the_shared_runtime_subset_holds_every_runtime_module_the_backend_needs']()
receipt={'originalFile':str(p.relative_to(root)),'originalSha256':hashlib.sha256(source.encode()).hexdigest(),'originalUnmodified':p.read_text()==source,'scratchTransform':'recursive production backend traversal, tests excluded as in packaging; bare-package resolver added; every original assertion preserved','result':'PASS'}
(root/'.scratch/review-2026-11/B2/recursive-runtime-closure.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt,indent=2))
