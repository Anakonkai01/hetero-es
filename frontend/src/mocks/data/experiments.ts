import type { Experiment } from "../../types/experiment";
import { hx, minutesAgo } from "./helpers";

function experimentId(key: string): string {
  return `exp-${hx(`exp${key}`, 12)}`;
}

function generationIdFor(key: string, index: number): string {
  return `gen-${hx(`${key}g${index}`, 12)}`;
}

const base = {
  modelName: "Qwen2.5-0.5B-Instruct",
  task: "Countdown",
  candidatesPerGeneration: 8,
  cancelRequested: false,
};

/** Experiments are mutable so that the create and cancel endpoints can change them. */
export const mockExperiments: Experiment[] = [
  {
    ...base,
    experimentId: experimentId("1"),
    name: "Countdown · Qwen2.5-0.5B (run 2)",
    status: "RUNNING",
    modelVersion: `mv-${hx("mv1", 4)}`,
    schedulerPolicy: "capacity-weighted",
    syncMode: "synchronous",
    baseSeed: 91210,
    configHash: `sha256:${hx(`cfg${experimentId("1")}`, 14)}…`,
    currentGenerationId: generationIdFor("1", 3),
    createdAt: minutesAgo(389),
    startedAt: minutesAgo(387),
  },
  {
    ...base,
    experimentId: experimentId("2"),
    name: "Countdown · Qwen2.5-0.5B (run 1)",
    status: "COMPLETED",
    modelVersion: `mv-${hx("mv2", 4)}`,
    schedulerPolicy: "capacity-weighted",
    syncMode: "synchronous",
    baseSeed: 21958,
    configHash: `sha256:${hx(`cfg${experimentId("2")}`, 14)}…`,
    createdAt: minutesAgo(1183),
    startedAt: minutesAgo(1176),
    completedAt: minutesAgo(833),
  },
  {
    ...base,
    experimentId: experimentId("3"),
    name: "LAN sync trial",
    status: "RUNNING",
    modelVersion: `mv-${hx("mv3", 4)}`,
    schedulerPolicy: "round-robin",
    syncMode: "asynchronous",
    baseSeed: 91305,
    configHash: `sha256:${hx(`cfg${experimentId("3")}`, 14)}…`,
    currentGenerationId: generationIdFor("3", 1),
    createdAt: minutesAgo(156),
    startedAt: minutesAgo(152),
  },
];

export { generationIdFor };
