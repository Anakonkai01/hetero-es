"""Adjust SQL syntax in test fixtures without changing their expectations or control flow."""
import ast,json,re
from pathlib import Path
changes=[]
for path in sorted(Path('backend/tests').glob('test_*.py')):
 if path.name == 'test_database_protocol.py':continue  # Intentional quoted identifiers exercise the SQL lexer.
 source=path.read_text();lines=source.splitlines(keepends=True);starts=[0]
 for line in lines:starts.append(starts[-1]+len(line))
 edits=[]
 for node in ast.walk(ast.parse(source)):
  if not isinstance(node,ast.Constant) or not isinstance(node.value,str):continue
  sql=node.value
  if not re.match(r'^\s*(SELECT|INSERT|DELETE|UPDATE|CREATE|ALTER)\b',sql,re.I) or '"' not in sql:continue
  portable=re.sub(r'"([^"\n]*)"',lambda m:"'"+m[1].replace("'","''")+"'",sql)
  if portable==sql:continue
  # AST columns are byte offsets; current SQL literals before these boundaries are ASCII.
  start=starts[node.lineno-1]+len(lines[node.lineno-1].encode()[:node.col_offset].decode())
  end=starts[node.end_lineno-1]+len(lines[node.end_lineno-1].encode()[:node.end_col_offset].decode())
  edits.append((start,end,repr(portable)))
 if edits:
  for start,end,value in sorted(edits,reverse=True):source=source[:start]+value+source[end:]
  path.write_text(source);changes.append({'file':str(path),'SQL_literals':len(edits)})
Path('.scratch/review-2026-11/B3/test-sql-rewrite.json').write_text(json.dumps(changes,indent=2)+'\n')
print('Updated',sum(c['SQL_literals'] for c in changes),'SQL literals in',len(changes),'test files')
