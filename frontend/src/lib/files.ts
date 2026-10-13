/** Long hash-named files (checkpoints) read as "953429cb…ac.bin"; ordinary names are left alone. */
export function friendlyFileName(name: string): string {
  const match = /^([0-9a-f]{32,})(\.[A-Za-z0-9]{1,8})?$/i.exec(name);
  return match ? `${match[1].slice(0, 8)}…${match[1].slice(-4)}${match[2] ?? ""}` : name;
}
