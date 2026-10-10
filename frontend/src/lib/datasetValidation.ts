import { TASK_FIELDS, type DatasetTask } from "../types/dataset";

// Structural validation only. No scoring or inspection of answer correctness.
function csvRows(content: string): string[][] {
  const rows: string[][] = []; let row: string[] = []; let cell = "";
  let quoted = false; let closed = false;
  const push = () => { row.push(cell); cell = ""; closed = false; };
  for (let i = 0; i < content.length; i++) {
    const c = content[i];
    if (quoted) {
      if (c === '"' && content[i + 1] === '"') { cell += '"'; i++; }
      else if (c === '"') { quoted = false; closed = true; }
      else cell += c;
    } else if (c === ',') push();
    else if (c === '\n' || c === '\r') {
      if (c === '\r' && content[i + 1] === '\n') i++;
      push(); if (row.length > 1 || row.some((v) => v.length)) rows.push(row); row = [];
    } else if (c === '"') {
      if (cell || closed) throw new Error("CSV: unexpected quote.");
      quoted = true;
    } else {
      if (closed) throw new Error("CSV: unexpected characters after closing quote.");
      cell += c;
    }
  }
  if (quoted) throw new Error("CSV: unterminated quoted field.");
  if (cell || row.length || closed) { push(); rows.push(row); }
  return rows;
}
export function validateDataset(name: string, raw: string, task: DatasetTask) {
  const sizeBytes = new TextEncoder().encode(raw).length;
  if (sizeBytes > 5 * 1024 * 1024) throw new Error("Local demo accepts files up to 5 MiB.");
  const content = raw.replace(/^\uFEFF/, "");
  const extension = name.split(".").pop()?.toLowerCase();
  let records: unknown[];
  if (extension === "json") {
    const parsed: unknown = JSON.parse(content);
    if (!Array.isArray(parsed)) throw new Error("JSON must contain an array of records.");
    records = parsed;
  } else if (extension === "jsonl") {
    records = content.split(/\r?\n/).flatMap((line, i) => {
      if (!line.trim()) return [];
      try { return [JSON.parse(line) as unknown]; }
      catch { throw new Error(`Line ${i + 1}: invalid JSON.`); }
    });
  } else if (extension === "csv") {
    const [headers, ...rows] = csvRows(content);
    if (!headers || new Set(headers).size !== headers.length) throw new Error("CSV requires unique column names.");
    records = rows.map((row, i) => {
      if (row.length !== headers.length) throw new Error(`CSV record ${i + 1}: incorrect column count.`);
      return Object.fromEntries(headers.map((key, j) => [key, row[j]]));
    });
  } else throw new Error("Choose JSON, JSONL or CSV.");
  if (!records.length) throw new Error("Dataset must contain at least one record.");
  const fields = [...TASK_FIELDS[task]];
  records.forEach((record, i) => {
    if (!record || typeof record !== "object" || Array.isArray(record)) throw new Error(`Record ${i + 1}: expected an object.`);
    const object = record as Record<string, unknown>;
    if (Object.keys(object).length !== fields.length || fields.some((field) => !Object.hasOwn(object, field) || typeof object[field] !== "string"))
      throw new Error(`Record ${i + 1}: requires exactly ${fields.join(", ")} as strings.`);
  });
  return { format: extension as "json" | "jsonl" | "csv", sizeBytes, recordCount: records.length, fields, preview: records.slice(0, 10) as Record<string, string>[] };
}
