import type { ArtifactStatus, ArtifactType } from "../types/artifact";
import type { AttemptStatus } from "../types/attempt";
import type { CandidateStatus } from "../types/candidate";
import type { EventSeverity } from "../types/event";
import type { ExperimentStatus } from "../types/experiment";
import type { AdmissionStatus } from "../types/worker";

export type Tone = "run" | "ok" | "warn" | "err" | "info" | "neutral";

export interface BadgeInfo {
  tone: Tone;
  label: string;
  title?: string;
}

export const EXPERIMENT_STATUS: Record<ExperimentStatus, BadgeInfo> = {
  PAUSING: { tone: "warn", label: "PAUSING" },
  PAUSED: { tone: "neutral", label: "PAUSED" },
  DRAFT: { tone: "neutral", label: "DRAFT", title: "Saved configuration; not submitted to the Coordinator" },
  RUNNING: { tone: "run", label: "RUNNING", title: "The experiment is being executed" },
  COMPLETED: { tone: "ok", label: "COMPLETED", title: "The experiment has completed" },
  QUEUED: {
    tone: "info",
    label: "QUEUED",
    title: "Request received; the coordinator has not confirmed the start yet",
  },
  CANCELLED: {
    tone: "neutral",
    label: "CANCELLED",
    title: "The experiment was cancelled, as confirmed by the coordinator",
  },
};

export const CANDIDATE_STATUS: Record<CandidateStatus, BadgeInfo> = {
  PENDING: { tone: "neutral", label: "PENDING", title: "Waiting to be assigned to a worker" },
  LEASED: { tone: "info", label: "LEASED", title: "Granted permission to run within a deadline" },
  RUNNING: { tone: "run", label: "RUNNING", title: "Being executed on a worker" },
  COMMITTED: { tone: "ok", label: "COMMITTED", title: "The result has been accepted by the system" },
};

export const CANDIDATE_LEGEND: Record<CandidateStatus, string> = {
  PENDING: "Waiting to be assigned to a worker.",
  LEASED:
    "Granted permission to run within a deadline (lease deadline); it may not have started yet.",
  RUNNING: "Being executed on a worker.",
  COMMITTED:
    "The result has been accepted by the system. A worker finishing its computation is not the same as COMMITTED.",
};

export const ATTEMPT_STATUS: Record<AttemptStatus, BadgeInfo> = {
  RUNNING: { tone: "run", label: "RUNNING", title: "The attempt is running" },
  SUCCEEDED: { tone: "ok", label: "SUCCEEDED", title: "The attempt finished successfully" },
  FAILED: { tone: "err", label: "FAILED", title: "The attempt ended with an error" },
};

export const EVENT_SEVERITY: Record<EventSeverity, BadgeInfo> = {
  INFO: { tone: "info", label: "INFO" },
  WARNING: { tone: "warn", label: "WARNING" },
  ERROR: { tone: "err", label: "ERROR" },
};

export const ADMISSION_STATUS: Record<AdmissionStatus, BadgeInfo> = {
  ADMITTED: { tone: "ok", label: "Full", title: "Admitted with full participation" },
  ADMITTED_LIMITED: { tone: "warn", label: "Limited", title: "Admitted with limits" },
  ELIGIBLE_BUT_NOT_BENEFICIAL: {
    tone: "info",
    label: "Not beneficial",
    title: "Eligible but not beneficial",
  },
  INELIGIBLE: { tone: "neutral", label: "Ineligible", title: "Not eligible to participate" },
};

/** Ordered from the most restrictive to the most permissive outcome. */
export const ADMISSION_LEGEND: { status: AdmissionStatus; text: string }[] = [
  {
    status: "INELIGIBLE",
    text: "Ineligible: a minimum technical requirement (such as VRAM) is not met.",
  },
  {
    status: "ELIGIBLE_BUT_NOT_BENEFICIAL",
    text: "Eligible but not beneficial: joining would not improve overall throughput.",
  },
  {
    status: "ADMITTED_LIMITED",
    text: "Admitted with limits: receives less work than the maximum.",
  },
  {
    status: "ADMITTED",
    text: "Admitted fully: receives work in line with its capacity.",
  },
];

export const ARTIFACT_STATUS: Record<ArtifactStatus, BadgeInfo> = {
  READY: { tone: "ok", label: "Ready" },
  PENDING: { tone: "info", label: "Not ready" },
  MISSING: { tone: "err", label: "Missing" },
  NO_DOWNLOAD_URL: { tone: "warn", label: "No download link" },
};

export const ARTIFACT_NOTE: Record<
  ArtifactStatus,
  { tone: "" | "warn" | "err"; text: string }
> = {
  READY: { tone: "", text: "The file is ready. This prototype simulates the download." },
  PENDING: {
    tone: "",
    text: "The file is not ready: the system is still producing it. Try again after the generation completes.",
  },
  MISSING: {
    tone: "err",
    text: "The file no longer exists in storage, so it cannot be downloaded.",
  },
  NO_DOWNLOAD_URL: {
    tone: "warn",
    text: "The system only has an internal storage location and has not provided a valid download link. The file cannot be downloaded from the interface.",
  },
};

export const ARTIFACT_TYPE_LABEL: Record<ArtifactType, string> = {
  CONFIG: "Config",
  CHECKPOINT: "Checkpoint",
  MANIFEST: "Manifest",
  EVALUATION_RESULTS: "Evaluation results",
};

export const POLICY_HINT = {
  "capacity-weighted": "Splits candidates by the estimated capacity of each admitted worker.",
  "round-robin": "Hands candidates to admitted workers in turn, ignoring capacity.",
} as const;

export const SYNC_HINT = {
  synchronous: "Waits for all candidates of a generation before updating the model.",
  asynchronous:
    "Allows updates before every candidate has finished (a prototype assumption).",
} as const;
