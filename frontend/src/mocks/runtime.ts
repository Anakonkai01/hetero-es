import type { Experiment } from "../types/experiment";
import type { Candidate } from "../types/candidate";
import type { Generation } from "../types/generation";
import { demoStore as db, finalizeReleases, now, persist, newId } from "./accessStore";

/** UI simulation only: no model, reward evaluator or GPU computation. */
export function advanceRuntime() {
  for (const e of db.experiments) {
    if (!e.maxGenerations || !["RUNNING", "PAUSING"].includes(e.status) || e.cancelRequested) continue;
    const tick = Date.now();
    if (tick - (e.mockTickAt ?? tick) < 1000) continue;
    e.mockTickAt = tick;
    e.mockCandidateProgress = (e.mockCandidateProgress ?? 0) + 1;
    if (e.mockCandidateProgress < e.candidatesPerGeneration) continue;
    e.completedGenerations = (e.completedGenerations ?? 0) + 1;
    e.mockCandidateProgress = 0;
    e.currentGenerationId = `${e.experimentId}-g${e.completedGenerations + 1}`;
    e.modelVersion = `demo-v${e.completedGenerations}`;
    e.validationScore = Math.min(0.9, 0.4 + e.completedGenerations * 0.025);
    e.checkpointSavedAt = now();
    db.runtimeEvents.push({ eventId: newId("event"), timestamp: now(), severity: "INFO", eventType: "DEMO_GENERATION_COMPLETED", message: `Simulated generation ${e.completedGenerations} completed; demo state saved.`, experimentId: e.experimentId, generationId: `${e.experimentId}-g${e.completedGenerations}` });
    if (e.completedGenerations >= e.maxGenerations) {
      e.status = "COMPLETED"; e.completedAt = now(); e.testScore = Math.max(0, e.validationScore - 0.02);
    } else if (e.status === "PAUSING") e.status = "PAUSED";
  }
  finalizeReleases(); persist();
}
export function simulatedGenerations(e: Experiment): Generation[] {
  const completed = e.completedGenerations ?? 0;
  const running = ["RUNNING", "PAUSING"].includes(e.status);
  return Array.from({ length: completed + (running ? 1 : 0) }, (_, i) => ({
    experimentId: e.experimentId, generationId: `${e.experimentId}-g${i + 1}`,
    modelVersion: `demo-v${i}`, status: i < completed ? "COMPLETED" : "RUNNING",
    candidateCount: e.candidatesPerGeneration,
    committedCandidateCount: i < completed ? e.candidatesPerGeneration : e.mockCandidateProgress ?? 0,
    rewardMean: i < completed ? Math.min(0.85, 0.4 + (i + 1) * 0.025) : undefined,
    rewardBest: i < completed ? Math.min(0.9, 0.45 + (i + 1) * 0.025) : undefined,
    startedAt: e.startedAt,
  }));
}
export function workerTelemetry<T extends { workerId: string; status: string; profile: { vramTotalMb: number }; ownerUserId?: string }>(w: T) {
  const e = db.experiments.find((e) => ["RUNNING", "QUEUED", "PAUSING"].includes(e.status) && e.workerIds?.includes(w.workerId));
  const pulse = Math.floor(Date.now() / 2500) % 6;
  const online = w.status === "ONLINE";
  return { ...w, temperatureC: online ? (e ? 62 : 36) + pulse : undefined,
    utilizationPercent: online ? (e ? 70 + pulse * 3 : pulse) : 0,
    profile: { ...w.profile, vramFreeMb: online ? Math.round(w.profile.vramTotalMb * (e ? 0.25 : 0.9)) : undefined },
    activeExperimentName: e?.name,
    allocatedTo: db.grants.find((g) => g.status !== "RELEASED" && g.workerIds.includes(w.workerId))?.userId,
    lastHeartbeatAt: online ? now() : undefined,
  };
}

export function simulatedCandidates(e: Experiment): Candidate[] {
  return simulatedGenerations(e).flatMap((g, generationIndex) => Array.from({ length: g.candidateCount }, (_, i) => ({
    experimentId: e.experimentId, generationId: g.generationId, candidateId: `${g.generationId}-c${i + 1}`,
    modelVersion: g.modelVersion, seed: (e.baseSeed ?? 0) + generationIndex * g.candidateCount + i,
    noiseRecipeHash: "demo-noise", batchIds: e.datasetIds?.slice(0, 1) ?? [], generationConfigHash: e.configHash,
    status: i < g.committedCandidateCount ? "COMMITTED" : i < g.committedCandidateCount + (e.workerIds?.length ?? 0) ? "RUNNING" : "PENDING",
    workerId: e.workerIds?.[i % (e.workerIds.length || 1)],
    reward: i < g.committedCandidateCount ? Math.min(0.9, 0.4 + (generationIndex + 1) * 0.025 + i * 0.002) : undefined,
  })));
}
