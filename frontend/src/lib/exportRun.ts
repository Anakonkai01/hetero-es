// Exports of one run for a report: a CSV of its generations and a Markdown summary. Pure text in, text out.
import type { Experiment } from "../types/experiment";
import type { Generation } from "../types/generation";

/** One CSV cell: quoted when needed, and a leading = + @ (or non-numeric -) is defused so a spreadsheet never runs it as a formula. */
export function csvCell(value: unknown): string {
  if (value === null || value === undefined) return "";
  let text = String(value);
  if (/^[=+@]/.test(text) || (/^-/.test(text) && !/^-?\d+(\.\d+)?$/.test(text))) text = "'" + text;
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function generationsCsv(_experiment: Experiment, generations: Generation[]): string {
  const header = "generation,status,candidates,committed,reward_mean,reward_best,started,completed";
  const rows = generations.map((g, index) => [index + 1, g.status, g.candidateCount, g.committedCandidateCount, g.rewardMean, g.rewardBest, g.startedAt, g.completedAt].map(csvCell).join(","));
  return [header, ...rows].join("\n") + "\n";
}

const number = (value: number | undefined, digits: number) => value === undefined || !Number.isFinite(value) ? "—" : value.toFixed(digits);

export function summaryMarkdown(experiment: Experiment, generations: Generation[]): string {
  const rewarded = generations.map((g, index) => ({ g, index })).filter(({ g }) => g.rewardMean !== undefined);
  const setup: [string, unknown][] = [["Workload", experiment.task], ["Model", experiment.modelName], ["Status", experiment.status], ["GPUs", experiment.workerIds?.join(", ")], ["Generations", experiment.maxGenerations],
    ["Candidates per generation", experiment.candidatesPerGeneration], ["Scheduling", experiment.schedulerPolicy], ["Synchronization", experiment.syncMode], ["Alpha", experiment.alpha], ["Sigma", experiment.sigma], ["Decoder", experiment.decodeEngine],
    ["Started", experiment.startedAt], ["Ended", experiment.completedAt]];
  const lines = [`# ${experiment.name}`, "", "| Setting | Value |", "| --- | --- |", ...setup.filter(([, value]) => value !== undefined && value !== "").map(([label, value]) => `| ${label} | ${String(value)} |`), "", "## Reward by generation", ""];
  if (rewarded.length) {
    lines.push("| Generation | Mean reward | Best reward |", "| --- | --- | --- |", ...rewarded.map(({ g, index }) => `| ${index + 1} | ${number(g.rewardMean, 4)} | ${number(g.rewardBest, 4)} |`));
  } else lines.push("No generation has a reward yet.");
  lines.push("", "Reward is a task score for this workload, not accuracy or a percentage. Numbers are as recorded by the lab; nothing here is rounded for presentation beyond four decimals.", "");
  return lines.join("\n");
}
