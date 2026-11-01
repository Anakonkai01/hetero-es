"""One-time mechanical source rewrite; manual dynamic-call cases are handled after this script."""
import ast,json,re
from pathlib import Path
baseline=json.loads(Path('.scratch/review-2026-11/B1/schema-before.json').read_text())
columns={name:[c['name'] for c in table['columns']] for name,table in baseline['tables'].items()}
pks={name:[c['name'] for c in sorted(table['columns'],key=lambda c:c['pk']) if c['pk']] for name,table in baseline['tables'].items()}
ordered={'users','devices','assignments','assignment_members','study_assets','study_uploads','workspaces','join_requests','experiments','model_probe_jobs'}
json_pattern=re.compile(r"json_extract\(([\w.]+),'\$\.([\w]+)'\)")
counts={'files':0,'SQL_literals':0}
class Convert(ast.NodeTransformer):
 def visit_Constant(self,node):
  if not isinstance(node.value,str):return node
  sql=node.value
  if not re.search(r'\b(SELECT|INSERT|DELETE|UPDATE)\b',sql,re.I):return node
  counts['SQL_literals']+=1
  sql=re.sub(r'"([^"\n]*)"',lambda m:"'"+m[1].replace("'","''")+"'",sql)
  insert=re.match(r'INSERT(?: OR (IGNORE|REPLACE))? INTO (\w+)(\s*)(?![\w(])',sql)
  if insert:
   action,table,_=insert.groups()
   sql=sql[:insert.start()]+f"INSERT INTO {table}({','.join(columns[table])}) "+sql[insert.end():]
   if action=='IGNORE':sql+=' ON CONFLICT DO NOTHING'
   elif action=='REPLACE':
    changed=[c for c in columns[table] if c not in pks[table]]
    sql+=' ON CONFLICT('+','.join(pks[table])+') DO UPDATE SET '+','.join(c+'=excluded.'+c for c in changed)
  else:
   sql=re.sub(r'^INSERT OR IGNORE INTO ','INSERT INTO ',sql)
   if node.value.startswith('INSERT OR IGNORE INTO '):sql+=' ON CONFLICT DO NOTHING'
  for table in ordered:
   sql=re.sub(r'(SELECT )\*( FROM '+table+r'\b)',lambda m:m[1]+','.join(columns[table])+m[2],sql)
   for alias in re.findall(r'(?:FROM|JOIN) '+table+r' (\w+)\b',sql):
    sql=sql.replace(alias+'.*',','.join(alias+'.'+c for c in columns[table]))
  sql=sql.replace('rowid','_insert_order')
  index=iter(range(sql.count('?')))
  sql=sql.replace('?', '{}').format(*(':p'+str(i) for i in index)) if '?' in sql else sql
  matches=list(json_pattern.finditer(sql))
  if not matches:return ast.copy_location(ast.Constant(sql),node)
  values=[];position=0
  for match in matches:
   if match.start()>position:values.append(ast.Constant(sql[position:match.start()]))
   values.append(ast.FormattedValue(ast.Call(ast.Name('json_text',ast.Load()),[ast.Name('db',ast.Load()),ast.Constant(match[1]),ast.Constant(match[2])],[]),conversion=-1))
   position=match.end()
  if position<len(sql):values.append(ast.Constant(sql[position:]))
  return ast.copy_location(ast.JoinedStr(values),node)
for path in sorted(Path('backend/repositories').glob('*.py')):
 if path.name=='base.py':continue
 old=path.read_text();tree=Convert().visit(ast.parse(old));ast.fix_missing_locations(tree)
 if any(isinstance(n,ast.Name) and n.id=='json_text' for n in ast.walk(tree)):
  tree.body.insert(1,ast.ImportFrom(module='db.dialect',names=[ast.alias(name='json_text')],level=2))
 path.write_text(ast.unparse(tree)+'\n');counts['files']+=1
Path('.scratch/review-2026-11/B3/repository-rewrite.json').write_text(json.dumps(counts,indent=2)+'\n')
print(counts)
