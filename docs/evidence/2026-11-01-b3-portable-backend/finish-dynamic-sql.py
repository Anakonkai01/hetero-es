import ast
from pathlib import Path
bodies={
('history.py','event_list_select_monitoring_events'):'''return execute(db,
    f"SELECT a.run_id,m.sequence,m.body FROM monitoring_events m JOIN assignments a ON a.id=m.assignment_id WHERE a.run_id IN ({bind_list(runs)}) AND {json_text(db, 'm.body', 'event')} IN (:p{len(runs)},:p{len(runs)+1}) ORDER BY m.sequence", parameters)''',
('history.py','event_list_select_experiments'):'''return execute(db, f"SELECT id,snapshot FROM experiments WHERE id IN ({bind_list(runs)})", parameters)''',
('notifications.py','mark_read_update_notifications_2'):'''return execute(db, f"UPDATE notifications SET read_at=:p0 WHERE user_id=:p1 AND read_at IS NULL AND id IN ({bind_list(numbers, start=2)})" if numbers else "SELECT 1", parameters)''',
('notifications.py','catch_up_select_sqlite_master'):'''return execute(db, "SELECT 1 FROM pg_tables WHERE schemaname=current_schema() AND tablename='devices'" if getattr(db, 'dialect', 'sqlite') == 'postgresql' else "SELECT 1 FROM sqlite_master WHERE name='devices'", parameters)''',
('experiments.py','state_eligibility_select_devices_2'):'''return execute(db, "SELECT owner,status FROM devices WHERE worker_id IN (" + bind_list(workers) + ")", parameters)''',
('model_qualification.py','effective_profile_select_value'):'''return execute(db, f"SELECT q.manifest_hash,{engine_column} FROM {table} q JOIN {references} r ON r.workspace_id=q.workspace_id AND r.manifest_hash=q.manifest_hash AND r.reference_hash=q.reference_hash" + engine_clause + " WHERE q.device_id=:p0 AND q.workspace_id=:p1 AND q.profile_hash=:p2", parameters)''',
('workspaces.py','remove_delete_value'):'''return execute(db, f"DELETE FROM {table} WHERE device_id=:p0", parameters)''',
('agent_polling.py','_refresh_observation_delete_device_telemetry_history'):'''return execute(db, "DELETE FROM device_telemetry_history WHERE device_id=:p0 AND (device_id,boot_id,sampled_at) NOT IN (SELECT device_id,boot_id,sampled_at FROM device_telemetry_history WHERE device_id=:p1 ORDER BY received_at DESC LIMIT 180)", parameters)''',
}
for path in Path('backend/repositories').glob('*.py'):
 tree=ast.parse(path.read_text());changed=False
 for node in ast.walk(tree):
  if isinstance(node,ast.FunctionDef) and (path.name,node.name) in bodies:
   node.body=ast.parse(bodies[path.name,node.name]).body;changed=True
 if path.name in {'history.py','notifications.py','experiments.py'}:
  imports=['bind_list']+(['json_text'] if path.name=='history.py' else [])
  tree.body.insert(1,ast.ImportFrom(module='db.dialect',names=[ast.alias(name=n) for n in imports],level=2));changed=True
 if changed:ast.fix_missing_locations(tree);path.write_text(ast.unparse(tree)+'\n')
