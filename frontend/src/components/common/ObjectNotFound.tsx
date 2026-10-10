import { Link } from "react-router";

interface ObjectNotFoundProps {
  backTo: string;
  backLabel: string;
}

export function ObjectNotFound({ backTo, backLabel }: ObjectNotFoundProps) {
  return (
    <div className="card">
      <div className="empty">
        <b>Object not found</b>
        <span>
          This object does not exist or has been removed from the data
          source.
        </span>
        <span className="acts">
          <Link className="btn pri" to={backTo}>
            {backLabel}
          </Link>
          <Link className="btn" to="/dashboard">
            Back to Dashboard
          </Link>
        </span>
      </div>
    </div>
  );
}
