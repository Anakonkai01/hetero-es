import type { WorkerStatus } from "../../types/worker";
import { Badge } from "./Badge";

export function WorkerActivityBadge({ status }: { status: WorkerStatus }) {
  return status === "ONLINE" ? (
    <Badge
      tone="ok"
      label="Online"
      title="The worker is sending heartbeats to the coordinator"
    />
  ) : (
    <Badge tone="neutral" label="Not online" />
  );
}
