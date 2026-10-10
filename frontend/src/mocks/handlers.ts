import { simulatedGenerations, simulatedCandidates } from "./runtime";
import type { SystemEvent } from "../types/event";
import { delay, http, HttpResponse } from "msw";
import { mockArtifacts } from "./data/artifacts";
import { mockAttempts, mockCandidates } from "./data/candidates";
import { mockEvents } from "./data/events";
import { mockGenerations } from "./data/generations";
import { getScenario } from "./scenario";
import { accessHandlers, canReadExperiment, demoResolver, readableExperimentIds, visibleWorkers } from "./accessHandlers";
import { demoStore } from "./accessStore";

const NETWORK_DELAY_MS = 250;
const allGenerations = () => [...mockGenerations, ...demoStore.experiments.filter((e) => e.maxGenerations).flatMap(simulatedGenerations)];
const allCandidates = () => [...mockCandidates, ...demoStore.experiments.filter((e) => e.maxGenerations).flatMap(simulatedCandidates)];

type Kind = "list" | "detail" | "events" | "attempt";

/**
 * Applies the scenario chosen in the "Simulate state" selector.
 * Returns a response when the scenario overrides the normal one.
 */
function scenarioOverride(kind: Kind): Response | undefined {
  const scenario = getScenario();

  if (scenario === "stale") {
    return HttpResponse.error();
  }

  if (scenario === "empty" && (kind === "list" || kind === "events")) {
    return HttpResponse.json([]);
  }

  if (scenario === "error" && (kind === "events" || kind === "attempt")) {
    return HttpResponse.json({ message: "Internal error" }, { status: 500 });
  }

  if (scenario === "notfound" && kind === "detail") {
    return HttpResponse.json({ message: "Not found" }, { status: 404 });
  }

  return undefined;
}

async function respond<T>(
  kind: Kind,
  build: () => T | undefined,
  notFoundMessage = "Not found",
): Promise<Response> {
  await delay(NETWORK_DELAY_MS);

  const override = scenarioOverride(kind);

  if (override) {
    return override;
  }

  const body = build();

  if (body === undefined) {
    return HttpResponse.json({ message: notFoundMessage }, { status: 404 });
  }

  return HttpResponse.json(body);
}

function newestFirst<T extends { createdAt?: string; timestamp?: string }>(
  items: T[],
): T[] {
  const key = (item: T) => item.createdAt ?? item.timestamp ?? "";

  return items.slice().sort((a, b) => key(b).localeCompare(key(a)));
}

export const handlers = [
  ...accessHandlers,
  http.get("/api/v1/workers", demoResolver((request) =>
    respond("list", () => visibleWorkers(request)),
  )),
  http.get("/api/v1/workers/:workerId", demoResolver((request, params) =>
    respond("detail", () => visibleWorkers(request).find((worker) => worker.workerId === params.workerId), "Worker not found"),
  )),
  http.get("/api/v1/experiments", demoResolver((request) => {
    const ids = readableExperimentIds(request);
    return respond("list", () => demoStore.experiments.filter((experiment) => ids.has(experiment.experimentId)));
  })),
  http.get("/api/v1/experiments/:experimentId", demoResolver((request, params) =>
    respond("detail", () => canReadExperiment(request, String(params.experimentId)), "Experiment not found"),
  )),
  http.get("/api/v1/experiments/:experimentId/generations", demoResolver((request, params) => {
    if (!canReadExperiment(request, String(params.experimentId))) return HttpResponse.json({ message: "Experiment not found" }, { status: 404 });
    return respond("list", () => (demoStore.experiments.find((e) => e.experimentId === params.experimentId)?.maxGenerations ? simulatedGenerations(demoStore.experiments.find((e) => e.experimentId === params.experimentId)!) : mockGenerations.filter((generation) => generation.experimentId === params.experimentId)));
  })),
  http.get("/api/v1/experiments/:experimentId/generations/:generationId", demoResolver((request, params) =>
    respond("detail", () => canReadExperiment(request, String(params.experimentId)) ? allGenerations().find((generation) => generation.experimentId === params.experimentId && generation.generationId === params.generationId) : undefined, "Generation not found"),
  )),
  http.get("/api/v1/generations/:generationId/candidates", demoResolver((request, params) => {
    const generation = allGenerations().find((item) => item.generationId === params.generationId);
    if (!generation || !canReadExperiment(request, generation.experimentId)) return HttpResponse.json({ message: "Generation not found" }, { status: 404 });
    return respond("list", () => allCandidates().filter((candidate) => candidate.generationId === params.generationId));
  })),
  http.get("/api/v1/candidates/:candidateId", demoResolver((request, params) =>
    respond("detail", () => {
      const candidate = allCandidates().find((item) => item.candidateId === params.candidateId);
      return candidate && canReadExperiment(request, candidate.experimentId) ? candidate : undefined;
    }, "Candidate not found"),
  )),
  http.get("/api/v1/attempts/:attemptId", demoResolver((request, params) =>
    respond("attempt", () => {
      const attempt = mockAttempts.find((item) => item.attemptId === params.attemptId);
      return attempt && canReadExperiment(request, attempt.experimentId) ? attempt : undefined;
    }, "Attempt not found"),
  )),
  http.get("/api/v1/events", demoResolver((request) => {
    const ids = readableExperimentIds(request);
    const workers = visibleWorkers(request).map((worker) => worker.workerId);
    return respond("events", () => newestFirst([...mockEvents, ...demoStore.runtimeEvents, ...demoStore.audit.filter((entry) => ids.has(entry.targetId)).map<SystemEvent>((entry) => ({ eventId: entry.auditId, timestamp: entry.createdAt, severity: "INFO" as const, eventType: entry.action, message: entry.action.replaceAll("_", " "), experimentId: entry.targetId }))].filter((event) => event.experimentId ? ids.has(event.experimentId) : event.workerId ? workers.includes(event.workerId) : false)));
  })),
  http.get("/api/v1/artifacts", demoResolver((request) => {
    const ids = readableExperimentIds(request);
    return respond("list", () => mockArtifacts.filter((artifact) => ids.has(artifact.experimentId)));
  })),
];
