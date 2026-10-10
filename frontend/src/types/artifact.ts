export type ArtifactType =
  | "CONFIG"
  | "CHECKPOINT"
  | "MANIFEST"
  | "EVALUATION_RESULTS";

export type ArtifactStatus =
  | "READY"
  | "PENDING"
  | "MISSING"
  | "NO_DOWNLOAD_URL";

export interface Artifact {
  artifactId: string;

  experimentId: string;

  type: ArtifactType;
  name: string;

  path: string;

  status: ArtifactStatus;

  createdAt?: string;

  sizeBytes?: number;
}
