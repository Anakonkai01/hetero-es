import type {
  CreateExperimentRequest,
  Experiment,
} from "../types/experiment";
import { apiDelete, apiGet, apiPatch, apiPost } from "./client";

export function getExperiments(): Promise<Experiment[]> {
  return apiGet<Experiment[]>("/api/v1/experiments");
}

export function getExperiment(
  experimentId: string,
): Promise<Experiment> {
  return apiGet<Experiment>(
    `/api/v1/experiments/${experimentId}`,
  );
}

export function createExperiment(
  request: CreateExperimentRequest,
): Promise<Experiment> {
  return apiPost<Experiment>("/api/v1/experiments", request);
}

export function requestExperimentCancel(
  experimentId: string,
): Promise<Experiment> {
  return apiPost<Experiment>(
    `/api/v1/experiments/${experimentId}/cancel`,
  );
}

export const updateExperiment = (input: { experimentId: string; configuration: CreateExperimentRequest }) => apiPatch<Experiment>(`/api/v1/experiments/${input.experimentId}`, input.configuration);
export const archiveExperiment = (experimentId: string) => apiDelete(`/api/v1/experiments/${experimentId}`);
export const submitExperiment = (experimentId: string) => apiPost<Experiment>(`/api/v1/experiments/${experimentId}/submit`);
export const completeDemoExperiment = (experimentId: string) => apiPost<Experiment>(`/api/v1/demo/experiments/${experimentId}/complete`);
export const controlExperiment = (input: { experimentId: string; action: "PAUSE" | "RESUME" | "CHANGE_WORKERS"; workerIds?: string[] }) => apiPost<Experiment>(`/api/v1/experiments/${input.experimentId}/control`, input);
