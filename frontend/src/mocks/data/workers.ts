import type { AdmissionStatus, Worker } from "../../types/worker";
import { minutesAgo } from "./helpers";

const admissionReasons: Record<AdmissionStatus, string> = {
  APPROVED: "Device approved by an administrator.",
  PENDING_VERIFICATION: "Runtime recipe verification has not completed.",
  ADMITTED:
    "Meets the model’s VRAM requirement (at least 6 GB) and adding this worker raises the cluster’s total throughput. It receives the maximum chunk size.",
  ADMITTED_LIMITED:
    "Enough VRAM, but only stable with small chunks. After the latest out-of-memory error, the coordinator limited the safe chunk size to 2 candidates per round.",
  ELIGIBLE_BUT_NOT_BENEFICIAL:
    "Technically eligible, but under the current capacity-weighted policy the sync overhead outweighs what this worker would contribute, so it is not given work.",
  INELIGIBLE:
    "Total VRAM of 4 GB is below the 5 GB minimum needed to load Qwen2.5-0.5B-Instruct together with the evaluation buffer.",
};

export const mockWorkers: Worker[] = [
  {
    workerId: "wk-5070ti-a1",
    status: "ONLINE",
    admissionStatus: "ADMITTED",
    admissionReason: admissionReasons.ADMITTED,
    profile: {
      gpuName: "NVIDIA GeForce RTX 5070 Ti",
      vramTotalMb: 16 * 1024,
      vramFreeMb: Math.round(9.8 * 1024),
      throughputTokensPerSecond: 2140,
      safeChunkSize: 8,
    },
    lastHeartbeatAt: minutesAgo(0, 8),
  },
  {
    workerId: "wk-1660s-b1",
    status: "ONLINE",
    admissionStatus: "ADMITTED_LIMITED",
    admissionReason: admissionReasons.ADMITTED_LIMITED,
    profile: {
      gpuName: "NVIDIA GeForce GTX 1660 Super",
      vramTotalMb: 6 * 1024,
      vramFreeMb: Math.round(2.1 * 1024),
      throughputTokensPerSecond: 690,
      safeChunkSize: 2,
    },
    lastHeartbeatAt: minutesAgo(0, 11),
  },
  {
    workerId: "wk-1660s-b2",
    status: "ONLINE",
    admissionStatus: "ELIGIBLE_BUT_NOT_BENEFICIAL",
    admissionReason: admissionReasons.ELIGIBLE_BUT_NOT_BENEFICIAL,
    profile: {
      gpuName: "NVIDIA GeForce GTX 1660 Super",
      vramTotalMb: 6 * 1024,
      vramFreeMb: Math.round(5.4 * 1024),
    },
    lastHeartbeatAt: minutesAgo(0, 22),
  },
  {
    workerId: "wk-1050ti-c1",
    status: "ONLINE",
    admissionStatus: "INELIGIBLE",
    admissionReason: admissionReasons.INELIGIBLE,
    profile: {
      gpuName: "NVIDIA GeForce GTX 1050 Ti",
      vramTotalMb: 4 * 1024,
      vramFreeMb: Math.round(3.6 * 1024),
    },
    lastHeartbeatAt: minutesAgo(0, 18),
  },
];
