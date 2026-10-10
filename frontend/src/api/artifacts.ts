import type { Artifact } from "../types/artifact";
import { apiGet } from "./client";

export function getArtifacts(): Promise<Artifact[]> {
  return apiGet<Artifact[]>("/api/v1/artifacts");
}
