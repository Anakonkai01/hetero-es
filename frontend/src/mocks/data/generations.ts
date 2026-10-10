import type { Generation, GenerationStatus } from "../../types/generation";
import { generationIdFor, mockExperiments } from "./experiments";
import { hx, minutesAgo } from "./helpers";

interface GenerationSpec {
  status: GenerationStatus;
  startMin: number;
  endMin?: number;
  mean?: number;
  best?: number;
}

/** Keyed by the experiment's seed key ("1", "2", "3"). */
export const generationSpecs: Record<string, GenerationSpec[]> = {
  "1": [
    { status: "COMPLETED", mean: 0.08, best: 0.21, startMin: 387, endMin: 309 },
    { status: "COMPLETED", mean: 0.14, best: 0.29, startMin: 308, endMin: 201 },
    { status: "COMPLETED", mean: 0.19, best: 0.34, startMin: 200, endMin: 12 },
    { status: "RUNNING", startMin: 11 },
  ],
  "2": [
    { status: "COMPLETED", mean: 0.1, best: 0.24, startMin: 1176, endMin: 1111 },
    { status: "COMPLETED", mean: 0.17, best: 0.31, startMin: 1110, endMin: 1041 },
    { status: "COMPLETED", mean: 0.22, best: 0.36, startMin: 1040, endMin: 971 },
    { status: "COMPLETED", mean: 0.27, best: 0.41, startMin: 970, endMin: 901 },
    { status: "COMPLETED", mean: 0.3, best: 0.44, startMin: 900, endMin: 833 },
  ],
  "3": [
    { status: "COMPLETED", mean: 0.09, best: 0.2, startMin: 152, endMin: 71 },
    { status: "RUNNING", startMin: 70 },
  ],
};

export const generationCandidateCount = 8;

export const mockGenerations: Generation[] = mockExperiments.flatMap(
  (experiment, experimentIndex) => {
    const key = String(experimentIndex + 1);

    return (generationSpecs[key] ?? []).map((spec, index) => ({
      experimentId: experiment.experimentId,
      generationId: generationIdFor(key, index),
      modelVersion: `mv-${hx(`${key}v${index}`, 4)}`,
      status: spec.status,
      candidateCount: generationCandidateCount,
      committedCandidateCount: 0,
      rewardMean: spec.mean,
      rewardBest: spec.best,
      startedAt: minutesAgo(spec.startMin),
      completedAt: spec.endMin === undefined ? undefined : minutesAgo(spec.endMin),
    }));
  },
);
