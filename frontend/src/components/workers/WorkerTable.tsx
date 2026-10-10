import { Link } from "react-router";
import { formatClock, formatGb, shortGpuName } from "../../lib/format";
import { ADMISSION_STATUS } from "../../lib/labels";
import type { Worker } from "../../types/worker";
import { Badge } from "../ui/Badge";
import { WorkerActivityBadge } from "../ui/WorkerActivity";

interface WorkerTableProps {
  workers: Worker[];
  /** The compact variant is used on the dashboard and omits the heartbeat column. */
  compact?: boolean;
}

export function WorkerTable({ workers, compact }: WorkerTableProps) {
  const columns = compact ? "cols-dwk" : "cols-wk";

  return (
    <div className="scroll">
      <div
        className={compact ? "tw s" : "tw"}
        role="table"
        aria-label={compact ? "Worker summary" : "Workers"}
      >
        <div className={`rowh ${columns}`} role="row">
          <div className="c" role="columnheader">Worker</div>
          <div className="c" role="columnheader">GPU</div>
          <div className="c" role="columnheader">VRAM</div>
          <div className="c" role="columnheader">Activity</div>
          <div className="c" role="columnheader">Admission</div>
          {!compact && (
            <div className="c" role="columnheader">Heartbeat</div>
          )}
        </div>

        {workers.map((worker) => (
          <div className={`row ${columns}`} role="row" key={worker.workerId}>
            <div className="c" role="cell">
              <Link className="link mono" to={`/workers/${worker.workerId}`}>
                {worker.workerId}
              </Link>
            </div>
            <div className="c" role="cell" title={worker.profile.gpuName}>
              {shortGpuName(worker.profile.gpuName)}
            </div>
            <div className="c" role="cell">
              {formatGb(worker.profile.vramTotalMb)}
            </div>
            <div className="c" role="cell">
              <WorkerActivityBadge status={worker.status} />
            </div>
            <div className="c" role="cell">
              <Badge info={ADMISSION_STATUS[worker.admissionStatus]} />
            </div>
            {!compact && (
              <div className="c mono mut" role="cell">
                {formatClock(worker.lastHeartbeatAt)}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
