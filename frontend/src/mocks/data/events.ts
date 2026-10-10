import type { SystemEvent } from "../../types/event";
import { mockExperiments } from "./experiments";
import { mockCandidates, mockAttempts } from "./candidates";
import { mockGenerations } from "./generations";
import { hx, minutesAgo } from "./helpers";

const [exp1, exp2, exp3] = mockExperiments;

const gensOf = (experimentId: string) =>
  mockGenerations.filter((generation) => generation.experimentId === experimentId);

const exp1Gens = gensOf(exp1.experimentId);
const exp3Gens = gensOf(exp3.experimentId);
const currentGen = exp1Gens[3];
const previousGen = exp1Gens[2];
const asyncGen = exp3Gens[1];

const currentCandidates = mockCandidates.filter(
  (candidate) => candidate.generationId === currentGen.generationId,
);
const failedCandidate = currentCandidates[6];
const failedAttempt = mockAttempts.find(
  (attempt) => attempt.candidateId === failedCandidate.candidateId,
)!;
const committedCandidate = currentCandidates[2];

function event(
  n: number,
  severity: SystemEvent["severity"],
  eventType: string,
  message: string,
  ago: [number, number],
  refs: Partial<SystemEvent>,
  details: Record<string, unknown>,
): SystemEvent {
  return {
    eventId: `evt-${hx(`ev${n}`, 8)}`,
    timestamp: minutesAgo(ago[0], ago[1]),
    severity,
    eventType,
    message,
    ...refs,
    details,
  };
}

export const mockEvents: SystemEvent[] = [
  event(
    1, "ERROR", "ATTEMPT_FAILED",
    "Attempt failed on wk-1660s-b1: CUDA out of memory while evaluating the candidate.",
    [3, 8],
    {
      experimentId: exp1.experimentId,
      generationId: currentGen.generationId,
      candidateId: failedCandidate.candidateId,
      attemptId: failedAttempt.attemptId,
      workerId: "wk-1660s-b1",
    },
    { error_kind: "CUDA_OUT_OF_MEMORY", requested_mib: 1240, free_mib: 812, chunk_size: 4 },
  ),
  event(
    2, "WARNING", "ADMISSION_CHANGED",
    "Safe chunk size of wk-1660s-b1 reduced from 4 to 2 candidates per round.",
    [2, 40],
    { workerId: "wk-1660s-b1" },
    { admission: "LIMITED", safe_chunk_before: 4, safe_chunk_after: 2, trigger: "ATTEMPT_FAILED" },
  ),
  event(
    3, "INFO", "CANDIDATE_COMMITTED",
    "The third candidate of the current generation was accepted (COMMITTED).",
    [5, 18],
    {
      experimentId: exp1.experimentId,
      generationId: currentGen.generationId,
      candidateId: committedCandidate.candidateId,
      workerId: committedCandidate.workerId,
    },
    { reward: committedCandidate.reward },
  ),
  event(
    4, "INFO", "GENERATION_STARTED",
    "New generation started with 8 candidates.",
    [11, 0],
    { experimentId: exp1.experimentId, generationId: currentGen.generationId },
    { candidates: 8, model_version: currentGen.modelVersion },
  ),
  event(
    5, "INFO", "GENERATION_COMPLETED",
    "Generation completed, mean reward 0.19.",
    [11, 30],
    { experimentId: exp1.experimentId, generationId: previousGen.generationId },
    { reward_mean: 0.19, reward_best: 0.34 },
  ),
  event(
    6, "ERROR", "SYNC_TIMEOUT",
    "Weight sync with wk-1660s-b2 exceeded the 30 s deadline.",
    [29, 11],
    { experimentId: exp3.experimentId, generationId: asyncGen.generationId, workerId: "wk-1660s-b2" },
    { deadline_s: 30, elapsed_s: 41, mode: "asynchronous" },
  ),
  event(
    7, "WARNING", "HEARTBEAT_DELAYED",
    "Heartbeat of wk-1660s-b2 was more than 20 s late.",
    [45, 49],
    { workerId: "wk-1660s-b2" },
    { expected_interval_s: 5, observed_gap_s: 23 },
  ),
  event(
    8, "INFO", "ADMISSION_EVALUATED",
    "wk-1660s-b2 is eligible but not beneficial under the current policy.",
    [51, 8],
    { workerId: "wk-1660s-b2" },
    { admission: "NOT_BENEFICIAL" },
  ),
  event(
    9, "INFO", "WORKER_REGISTERED",
    "wk-1050ti-c1 registered; ineligible because of 4 GB VRAM.",
    [80, 36],
    { workerId: "wk-1050ti-c1" },
    { admission: "INELIGIBLE", vram_gb: 4, required_gb: 5 },
  ),
  event(
    10, "INFO", "EXPERIMENT_STARTED",
    "Experiment started running.",
    [387, 17],
    { experimentId: exp1.experimentId },
    { policy: exp1.schedulerPolicy },
  ),
  event(
    11, "INFO", "EXPERIMENT_COMPLETED",
    "Experiment completed after 5 generations.",
    [832, 50],
    { experimentId: exp2.experimentId },
    { generations: 5 },
  ),
];
