"""Move the already extracted queue projection to the experiment domain without changing its AST."""
import ast
import copy
import json
from pathlib import Path

root=Path('/home/pc5070ti/projects/heteroes')
files={n:(root/n).read_text() for n in ['backend/services/workspaces.py','backend/services/experiments.py','backend/api/workspaces.py','backend/api/experiments.py','backend/repositories/workspaces.py','backend/repositories/experiments.py']}
trees={n:ast.parse(s) for n,s in files.items()}
def factory(t,name):return next(n for n in t.body if isinstance(n,ast.FunctionDef) and n.name==name)
def fn(t,name):return next(n for n in t.body if isinstance(n,ast.FunctionDef) and n.name==name)
def start(n):return min([n.lineno]+[d.lineno for d in getattr(n,'decorator_list',[])])-1
def render(n,indent=4):return '\n'.join(' '*indent+line for line in ast.unparse(ast.fix_missing_locations(n)).splitlines())+'\n'
def edits(text,changes):
 lines=text.splitlines(keepends=True)
 for a,b,new in sorted(changes,reverse=True):lines[a:b]=[new]
 return ''.join(lines)
ws='backend/services/workspaces.py';es='backend/services/experiments.py'
w=factory(trees[ws],'operations');e=factory(trees[es],'operations');queue=fn(w,'queue')
wreturn=w.body[-1];ereturn=e.body[-1]
assert isinstance(wreturn,ast.Return) and isinstance(ereturn,ast.Return)
wnew=copy.deepcopy(wreturn);wnew.value.keywords=[k for k in wnew.value.keywords if k.arg!='queue']
enew=copy.deepcopy(ereturn);assert all(k.arg!='queue' for k in enew.value.keywords);enew.value.keywords.append(ast.keyword(arg='queue',value=ast.Name(id='queue',ctx=ast.Load())))
files[ws]=edits(files[ws],[(start(queue),queue.end_lineno,''),(start(wreturn),wreturn.end_lineno,render(wnew))])
files[es]=edits(files[es],[(start(ereturn),ereturn.end_lineno,render(copy.deepcopy(queue))+'\n'+render(enew))])
wa='backend/api/workspaces.py';ea='backend/api/experiments.py'
w=factory(trees[wa],'install_routes');e=factory(trees[ea],'install_routes');http_queue=fn(w,'queue');include=e.body[-1]
files[wa]=edits(files[wa],[(start(http_queue),http_queue.end_lineno,'')])
files[ea]=edits(files[ea],[(start(include),include.end_lineno,render(copy.deepcopy(http_queue))+'\n'+render(copy.deepcopy(include)))])
wr='backend/repositories/workspaces.py';er='backend/repositories/experiments.py'
w=next(n for n in trees[wr].body if isinstance(n,ast.ClassDef));names={'queue_select_queue','queue_select_experiments'}
queries=[n for n in w.body if isinstance(n,ast.FunctionDef) and n.name in names];assert len(queries)==2
files[wr]=edits(files[wr],[(start(n),n.end_lineno,'') for n in queries])
for n in queries:files[er]+='\n'+render(copy.deepcopy(n))
for path,text in files.items():ast.parse(text)
new_queue=fn(factory(ast.parse(files[es]),'operations'),'queue');new_http=fn(factory(ast.parse(files[ea]),'install_routes'),'queue')
assert ast.dump(new_queue,include_attributes=False)==ast.dump(queue,include_attributes=False)
assert ast.dump(new_http,include_attributes=False)==ast.dump(http_queue,include_attributes=False)
new_repo=next(n for n in ast.parse(files[er]).body if isinstance(n,ast.ClassDef))
for q in queries:
 actual=fn(new_repo,q.name);assert ast.dump(actual,include_attributes=False)==ast.dump(q,include_attributes=False)
for path,text in files.items():(root/path).write_text(text)
(root/'.scratch/review-2026-11/B2/queue-move-ast-proof.json').write_text(json.dumps({'serviceFunctionAST':'identical','httpFunctionAST':'identical','repositoryMethodAST':'identical','movedQueries':sorted(names),'from':'workspaces','to':'experiments'},indent=2)+'\n')
print('Queue business function, HTTP adapter and both queries moved with identical AST')
