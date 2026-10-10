import type { Attempt } from "../../types/attempt";
import type { Candidate, CandidateStatus } from "../../types/candidate";
import { mockExperiments } from "./experiments";
import { generationSpecs, mockGenerations } from "./generations";
import { hx, minutesAgo, minutesFromNow } from "./helpers";

const workerCycle = [
  "wk-5070ti-a1",
  "wk-1660s-b1",
  "wk-5070ti-a1",
  "wk-5070ti-a1",
  "wk-1660s-b1",
  "wk-5070ti-a1",
  "wk-1660s-b1",
  "wk-5070ti-a1",
];

const allCommitted: CandidateStatus[] = Array(8).fill("COMMITTED");

/** Candidate statuses of generations that are not fully committed, keyed by "<experimentKey>:<index>". */
const statusOverrides: Record<string, CandidateStatus[]> = {
  "1:3": ["COMMITTED", "COMMITTED", "COMMITTED", "RUNNING", "RUNNING", "LEASED", "PENDING", "PENDING"],
  "3:1": ["COMMITTED", "RUNNING", "LEASED", "PENDING", "PENDING", "PENDING", "PENDING", "PENDING"],
};

export const mockCandidates: Candidate[] = [];
export const mockAttempts: Attempt[] = [];

mockExperiments.forEach((experiment, experimentIndex) => {
  const key = String(experimentIndex + 1);
  const generations = mockGenerations.filter(
    (generation) => generation.experimentId === experiment.experimentId,
  );

  generations.forEach((generation, index) => {
    const spec = generationSpecs[key][index];
    const statuses = statusOverrides[`${key}:${index}`] ?? allCommitted;

    statuses.forEach((status, j) => {
      const candidateId = `cnd-${hx(generation.generationId + j, 12)}`;
      const workerId = status === "PENDING" ? undefined : workerCycle[j];
      const attemptId = `att-${hx(candidateId, 12)}`;
      const hasLease = status === "LEASED" || status === "RUNNING";
      let reward: number | undefined;
      let attempt: (Partial<Attempt> & Pick<Attempt, "status">) | undefined;

      if (status === "COMMITTED") {
        const base = spec.mean ?? 0.2;
        const jitter =
          (parseInt(hx(`${generation.generationId}r${j}`, 3), 16) % 90) - 40;

        reward = Number(Math.max(0.02, base + jitter / 1000).toFixed(3));
        attempt = {
          status: "SUCCEEDED",
          startedAt: minutesAgo(spec.startMin - (1 + j), 10 + j * 3),
          completedAt: minutesAgo(spec.startMin - (3 + j), 20 + j * 4),
        };
      } else if (status === "RUNNING") {
        attempt = { status: "RUNNING", startedAt: minutesAgo(3, j * 5) };
      }

      // The 7th candidate of the first experiment's current generation is waiting
      // to be reassigned after its latest attempt failed with an out-of-memory error.
      const failed = key === "1" && index === 3 && j === 6;

      if (failed) {
        attempt = {
          status: "FAILED",
          startedAt: minutesAgo(4, 39),
          completedAt: minutesAgo(3, 8),
          errorType: "CUDA_OUT_OF_MEMORY",
        };
      }

      if (attempt) {
        mockAttempts.push({
          ...attempt,
          experimentId: experiment.experimentId,
          generationId: generation.generationId,
          candidateId,
          attemptId,
          workerId: failed ? "wk-1660s-b1" : (workerId as string),
          modelVersion: generation.modelVersion,
          leaseToken: `lease-${hx(candidateId, 8)}`,
        });
      }

      mockCandidates.push({
        experimentId: experiment.experimentId,
        generationId: generation.generationId,
        candidateId,
        attemptId: attempt ? attemptId : undefined,
        modelVersion: generation.modelVersion,
        seed: parseInt(hx(`${generation.generationId}s${j}`, 7), 16),
        noiseRecipeHash: `noise-${hx(`${generation.generationId}n${j}`, 8)}`,
        batchIds: [`b-${4100 + j * 2}`, `b-${4101 + j * 2}`],
        generationConfigHash: `sha256:${hx(`${generation.generationId}h${j}`, 14)}…`,
        leaseToken: hasLease ? `lease-${hx(candidateId, 8)}` : undefined,
        leaseDeadline: hasLease ? minutesFromNow(4) : undefined,
        workerId,
        status,
        reward,
      });
    });

    generation.committedCandidateCount = statuses.filter(
      (status) => status === "COMMITTED",
    ).length;
  });
});
