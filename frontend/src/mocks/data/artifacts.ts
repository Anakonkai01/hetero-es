import type { Artifact } from "../../types/artifact";
import { mockExperiments } from "./experiments";
import { mockGenerations } from "./generations";
import { hx, minutesAgo } from "./helpers";

const [exp1, exp2, exp3] = mockExperiments;
const exp1Gens = mockGenerations.filter(
  (generation) => generation.experimentId === exp1.experimentId,
);

const checkpointName = (generationId: string) =>
  `checkpoint-${generationId.slice(4, 12)}.safetensors`;

const KB = 1024;
const MB = 1024 * 1024;

function artifact(
  n: number,
  name: string,
  type: Artifact["type"],
  experimentId: string,
  path: string,
  status: Artifact["status"],
  createdMinutesAgo?: number,
  sizeBytes?: number,
): Artifact {
  return {
    artifactId: `art-${hx(`art${n}`, 8)}`,
    name,
    type,
    experimentId,
    path: `store://experiments/${path}`,
    status,
    createdAt: createdMinutesAgo === undefined ? undefined : minutesAgo(createdMinutesAgo),
    sizeBytes,
  };
}

export const mockArtifacts: Artifact[] = [
  artifact(1, "config.json", "CONFIG", exp1.experimentId, "1/config.json", "READY", 389, 2.1 * KB),
  artifact(
    2, checkpointName(exp1Gens[2].generationId), "CHECKPOINT", exp1.experimentId,
    `1/ckpt/${exp1Gens[2].generationId}.safetensors`, "READY", 11, 988 * MB,
  ),
  artifact(3, "manifest.json", "MANIFEST", exp1.experimentId, "1/manifest.json", "READY", 11, 4.8 * KB),
  artifact(
    4, checkpointName(exp1Gens[3].generationId), "CHECKPOINT", exp1.experimentId,
    `1/ckpt/${exp1Gens[3].generationId}.safetensors`, "PENDING",
  ),
  artifact(
    5, "eval-results.json", "EVALUATION_RESULTS", exp2.experimentId,
    "2/eval-results.json", "READY", 833, 36 * KB,
  ),
  artifact(
    6, "checkpoint-final.safetensors", "CHECKPOINT", exp2.experimentId,
    "2/ckpt/final.safetensors", "MISSING", 833, 988 * MB,
  ),
  artifact(7, "config.json", "CONFIG", exp3.experimentId, "3/config.json", "NO_DOWNLOAD_URL", 156, 2.0 * KB),
];
