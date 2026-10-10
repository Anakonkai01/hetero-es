export const TASK_FIELDS = {
  sentiment: ["text", "label"],
  qa: ["context", "question", "answer"],
  summarization: ["text", "summary"],
} as const;
export type DatasetTask = keyof typeof TASK_FIELDS;
export type DatasetSplit = "train" | "validation" | "test";
export interface Dataset {
  datasetId: string; ownerUserId: string; workspaceId: string;
  name: string; task: DatasetTask; split: DatasetSplit;
  format: "json" | "jsonl" | "csv"; sizeBytes: number;
  recordCount: number; fields: string[]; preview: Record<string, string>[];
}
export interface DatasetUpload { name: string; content: string; task: DatasetTask; split: DatasetSplit }
