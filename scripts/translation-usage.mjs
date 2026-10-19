/** Conservative exact-string usage, including dynamic UI tables and backend status/action values. */
import fs from 'node:fs';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import ts from 'typescript';

export function translationKeysUsed(root) {
  const used = new Set();
  const pythonFiles = [];
  const roots = ['frontend/src','desktop/worker/src','desktop/server/src','packages/product-ui/src',
    'frontend/tests','packages/product-ui/tests','backend'];
  function walk(directory) {
    for (const item of fs.readdirSync(directory,{withFileTypes:true})) {
      if (['__pycache__','fixtures','node_modules','dist'].includes(item.name)) continue;
      const file = path.join(directory,item.name);
      if (item.isDirectory()) { walk(file); continue; }
      if (item.name==='translations.ts') continue;
      if (file.endsWith('.py')) { pythonFiles.push(file); continue; }
      if (!/\.(?:[cm]?js|tsx?)$/.test(file)) continue;
      const source = ts.createSourceFile(file,fs.readFileSync(file,'utf8'),ts.ScriptTarget.Latest,true,
        file.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
      function visit(node) {
        if (ts.isStringLiteral(node)||ts.isNoSubstitutionTemplateLiteral(node)) used.add(node.text);
        ts.forEachChild(node,visit);
      }
      visit(source);
    }
  }
  for (const name of roots) walk(path.join(root,name));
  const scan = spawnSync(process.env.PYTHON || 'python3',['-I','-c',
    'import ast,json,sys; from pathlib import Path; print(json.dumps(sorted({n.value for p in json.load(sys.stdin) for n in ast.walk(ast.parse(Path(p).read_text())) if isinstance(n,ast.Constant) and isinstance(n.value,str)})))'],
    {input:JSON.stringify(pythonFiles),encoding:'utf8'});
  if (scan.status!==0) throw Error('Cannot inspect backend translation values');
  for (const key of JSON.parse(scan.stdout)) used.add(key);
  return used;
}
